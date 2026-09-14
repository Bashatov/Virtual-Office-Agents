# -*- coding: utf-8 -*-
"""
Bitta agent uchun to'liq ishchi mantiq:
  1. Foydalanuvchidan/guruhdan xabar keladi
     -> Agar bu xabar biror xodimdan kutilayotgan javob bo'lsa,
        to'g'ridan-to'g'ri asl so'rovchiga forward qilinadi (LLM ishlamaydi)
     -> Aks holda LLM javob beradi
  2. Agar javobda [DELEGATE:agent_key] bo'lsa -> AI bo'limga vazifa yaratiladi
  3. Agar javobda [MESSAGE_HUMAN:employee_key] bo'lsa -> xodimga to'g'ridan-
     to'g'ri Telegram xabar yuboriladi va javobi kutiladi
  4. Fon rejimda: shu agentga tegishli 'pending' AI-vazifalarni tekshirib,
     bajarib, guruhga natijani yozib turadi
"""

import re
import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from agents_config import AGENTS, GROUP_CHAT_ID
from employees_config import EMPLOYEES
from llm_client import generate_reply
import db

logger = logging.getLogger(__name__)

DELEGATE_RE = re.compile(r"\[DELEGATE:(\w+)\]\s*(.+)", re.DOTALL)
MESSAGE_HUMAN_RE = re.compile(r"\[MESSAGE_HUMAN:(\w+)\]\s*(.+)", re.DOTALL)


def build_worker(agent_key: str) -> Application:
    cfg = AGENTS[agent_key]
    token = os.getenv(cfg["token_env"])
    if not token:
        raise RuntimeError(f"{cfg['token_env']} .env faylida topilmadi")

    app = Application.builder().token(token).build()

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_text = update.message.text
        if not user_text:
            return

        # 1) Bu xabar - biror xodimdan kutilayotgan javobmi?
        pending_human_task = db.get_waiting_human_task(chat_id)
        if pending_human_task:
            db.mark_human_task_replied(pending_human_task["_id"], user_text)
            employee_name = EMPLOYEES.get(
                pending_human_task["employee_key"], {}
            ).get("display_name", pending_human_task["employee_key"])

            reply_text = (
                f"📩 {employee_name} javob berdi:\n\n{user_text}"
            )
            await context.bot.send_message(
                chat_id=pending_human_task["origin_chat_id"], text=reply_text
            )
            # Xodimning o'ziga ham tasdiq beramiz
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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


async def task_checker_loop(agent_key: str, app: Application, interval_sec: int = 20):
    """Fon rejimida: shu agentga berilgan yangi AI-vazifalarni tekshirib bajaradi."""
    cfg = AGENTS[agent_key]
    bot = app.bot
    while True:
        try:
            pending = db.get_pending_tasks(agent_key)
            for task in pending:
                history = [{"role": "user", "content": task["task_text"]}]
                result = generate_reply(
                    cfg["provider"], cfg["model"], cfg["system_prompt"], history
                )
                db.mark_task_done(task["_id"], result)

                target_chat = GROUP_CHAT_ID or task["origin_chat_id"]
                text = f"✅ {cfg['display_name']} bajardi:\n\n{result}"
                await bot.send_message(chat_id=target_chat, text=text)
        except Exception:
            logger.exception("task_checker_loop xatolik (%s)", agent_key)

        await asyncio.sleep(interval_sec)
