# -*- coding: utf-8 -*-
"""
Bitta agent uchun to'liq ishchi mantiq:

  - Shaxsiy chatda: har doim javob beradi.
  - Guruh chatida: FAQAT quyidagi hollarda javob beradi (bekorga
    aralashib, xodimlarning o'zaro suhbatiga xalaqit bermaslik uchun):
      1) @botusername orqali chaqirilsa
      2) shu botning oldingi xabariga "reply" qilingan bo'lsa
      3) xabar bot nomi bilan boshlansa (masalan "Marketolog, ...")

  - Matn, fayl (.txt/.docx/.pdf) va ovozli xabarlarni qabul qiladi.
  - Javobda [DELEGATE:agent_key] bo'lsa -> AI bo'limga vazifa yaratiladi.
  - Javobda [MESSAGE_HUMAN:employee_key] bo'lsa -> xodimga to'g'ridan-
    to'g'ri Telegram xabar yuboriladi va javobi kutiladi.
  - Fon rejimda: shu agentga tegishli 'pending' AI-vazifalarni bajaradi.
"""

import re
import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from agents_config import AGENTS, GROUP_CHAT_ID
from employees_config import EMPLOYEES
from topics_config import TOPIC_MAP
from llm_client import generate_reply, transcribe_voice
import file_utils
import db

logger = logging.getLogger(__name__)

DELEGATE_RE = re.compile(r"\[DELEGATE:(\w+)\]\s*(.+)", re.DOTALL)
MESSAGE_HUMAN_RE = re.compile(r"\[MESSAGE_HUMAN:(\w+)\]\s*(.+)", re.DOTALL)

GROUP_TYPES = ("group", "supergroup")


def build_worker(agent_key: str) -> Application:
    cfg = AGENTS[agent_key]
    token = os.getenv(cfg["token_env"])
    if not token:
        raise RuntimeError(f"{cfg['token_env']} .env faylida topilmadi")

    app = Application.builder().token(token).build()

    # ---------- Guruhda "chaqirilganmi" tekshiruvi ----------

    async def is_addressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        chat = update.effective_chat
        if chat.type not in GROUP_TYPES:
            return True  # shaxsiy chatda har doim javob beramiz

        msg = update.message
        text = (msg.text or msg.caption or "").strip()

        # 1) shu bot O'ZINING topic'ida (kabinetida) yozilganmi -
        #    bu yerda @mention shart emas, avtomatik javob beradi
        thread_id = getattr(msg, "message_thread_id", None)
        if thread_id is not None and TOPIC_MAP.get(thread_id) == agent_key:
            return True

        # 2) shu botning oldingi xabariga reply qilinganmi
        if (
            msg.reply_to_message
            and msg.reply_to_message.from_user
            and msg.reply_to_message.from_user.id == context.bot.id
        ):
            return True

        # 3) @username orqali chaqirilganmi
        bot_username = (context.bot.username or "").lower()
        if bot_username and f"@{bot_username}" in text.lower():
            return True

        # 4) bot nomi bilan boshlanganmi (masalan "Marketolog, ...")
        display = cfg["display_name"].lower()
        if text.lower().startswith(display):
            return True

        return False

    # ---------- Asosiy mantiq (matn, fayl, ovoz - hammasi shu yerga keladi) ----------

    async def process_user_text(chat_id: int, user_text: str, update: Update,
                                 context: ContextTypes.DEFAULT_TYPE):
        # 1) Bu xabar - biror xodimdan kutilayotgan javobmi?
        pending_human_task = db.get_waiting_human_task(chat_id)
        if pending_human_task:
            db.mark_human_task_replied(pending_human_task["_id"], user_text)
            employee_name = EMPLOYEES.get(
                pending_human_task["employee_key"], {}
            ).get("display_name", pending_human_task["employee_key"])

            reply_text = f"📩 {employee_name} javob berdi:\n\n{user_text}"
            await context.bot.send_message(
                chat_id=pending_human_task["origin_chat_id"], text=reply_text
            )
            await update.message.reply_text("✅ Javobingiz uzatildi, rahmat!")
            return

        # 2) Oddiy AI-suhbat oqimi
        db.save_message(agent_key, chat_id, "user", user_text)
        history = db.get_history(agent_key, chat_id)

        reply = generate_reply(
            cfg["provider"], cfg["model"], cfg["system_prompt"], history
        )

        visible_reply = reply

        # 2a) AI bo'limga delegatsiya
        delegate_match = DELEGATE_RE.search(reply)
        if delegate_match:
            to_agent = delegate_match.group(1).strip().lower()
            task_text = delegate_match.group(2).strip()
            visible_reply = reply[: delegate_match.start()].strip()
            if to_agent in AGENTS:
                db.create_task(agent_key, to_agent, task_text, chat_id)
                visible_reply += (
                    f"\n\n📋 Vazifa {AGENTS[to_agent]['display_name']}ga berildi."
                )

        # 2b) Haqiqiy xodimga xabar yuborish
        human_match = MESSAGE_HUMAN_RE.search(reply)
        if human_match:
            employee_key = human_match.group(1).strip().lower()
            message_text = human_match.group(2).strip()
            visible_reply = reply[: human_match.start()].strip()

            employee = EMPLOYEES.get(employee_key)
            if employee and employee.get("chat_id"):
                await context.bot.send_message(
                    chat_id=employee["chat_id"],
                    text=f"📩 Yangi xabar ({cfg['display_name']}dan):\n\n{message_text}",
                )
                db.create_human_task(
                    employee_key, employee["chat_id"], message_text,
                    chat_id, agent_key,
                )
                visible_reply += (
                    f"\n\n📨 Xabar {employee['display_name']}ga yuborildi. "
                    "Javob kelgach, sizga darhol xabar beraman."
                )
            else:
                visible_reply += (
                    f"\n\n⚠️ '{employee_key}' xodimi topilmadi yoki "
                    "chat_id sozlanmagan (employees_config.py'ni tekshiring)."
                )

        db.save_message(agent_key, chat_id, "assistant", visible_reply)
        await update.message.reply_text(visible_reply)

    # ---------- Matn xabarlari ----------

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if not await is_addressed(update, context):
            return
        await process_user_text(update.effective_chat.id, update.message.text,
                                 update, context)

    # ---------- Fayllar (.txt, .docx, .pdf) ----------

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.document:
            return
        if not await is_addressed(update, context):
            return

        doc = update.message.document
        await update.message.reply_text(f"📄 {doc.file_name} qabul qilindi, o'qiyapman...")

        tg_file = await doc.get_file()
        file_bytes = bytes(await tg_file.download_as_bytearray())
        extracted = file_utils.extract_text(file_bytes, doc.file_name)

        caption = update.message.caption or "(izoh yozilmagan)"
        user_text = (
            f"[Foydalanuvchi fayl yubordi: {doc.file_name}]\n\n"
            f"Fayl matni:\n{extracted}\n\n"
            f"Foydalanuvchi izohi: {caption}"
        )
        await process_user_text(update.effective_chat.id, user_text, update, context)

    # ---------- Ovozli xabarlar ----------

    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.voice:
            return
        if not await is_addressed(update, context):
            return

        tg_file = await update.message.voice.get_file()
        file_bytes = bytes(await tg_file.download_as_bytearray())
        transcribed = transcribe_voice(file_bytes)

        if not transcribed:
            await update.message.reply_text(
                "⚠️ Ovozli xabarni tushunolmadim, matn bilan yozib ko'ring."
            )
            return

        await update.message.reply_text(f"🎙 Eshitdim: \u201c{transcribed}\u201d")
        await process_user_text(update.effective_chat.id, transcribed, update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    return app


async def task_checker_loop(agent_key: str, bots: dict, interval_sec: int = 20):
    """
    Fon rejimida: shu agentga berilgan yangi AI-vazifalarni tekshirib bajaradi.
    Natija - vazifani KIM SO'RAGAN bo'lsa o'sha bo'lim (from_agent) boti
    orqali, aynan so'ragan chatga (origin_chat_id) qaytariladi. Masalan:
    foydalanuvchi Direktordan SMM'ga vazifa berdirsa, SMM bajargach,
    natija Direktor boti orqali foydalanuvchiga qaytadi - guruhga emas.
    """
    cfg = AGENTS[agent_key]
    while True:
        try:
            pending = db.get_pending_tasks(agent_key)
            for task in pending:
                history = [{"role": "user", "content": task["task_text"]}]
                result = generate_reply(
                    cfg["provider"], cfg["model"], cfg["system_prompt"], history
                )
                db.mark_task_done(task["_id"], result)

                origin_agent_key = task.get("from_agent", agent_key)
                origin_bot = bots.get(origin_agent_key) or bots.get(agent_key)
                text = f"✅ {cfg['display_name']} bajardi:\n\n{result}"
                await origin_bot.send_message(chat_id=task["origin_chat_id"], text=text)
        except Exception:
            logger.exception("task_checker_loop xatolik (%s)", agent_key)

        await asyncio.sleep(interval_sec)
