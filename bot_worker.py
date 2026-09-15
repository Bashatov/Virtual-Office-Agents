# -*- coding: utf-8 -*-
"""
Bitta agent uchun to'liq ishchi mantiq:

  - Shaxsiy chatda: har doim javob beradi.
  - Guruh chatida: FAQAT quyidagi hollarda javob beradi:
      1) shu botning o'z topic'ida (topics_config.py orqali) yozilgan bo'lsa
      2) @botusername orqali chaqirilsa
      3) shu botning oldingi xabariga "reply" qilingan bo'lsa
      4) xabar bot nomi bilan boshlansa (masalan "Marketolog, ...")
    ISTISNO: Direktordan boshqa har bir bot, BOSHQA bo'limga tegishli
    topic'da UMUMAN ishlamaydi (hatto chaqirilsa ham) - faqat Direktor
    istalgan topicda ishlay oladi.

  - Matn, fayl (.txt/.docx/.pdf), rasm, video va ovozli xabarlarni
    qabul qiladi va tushunadi (rasm/video - AI vision orqali tahlil
    qilinadi).
  - Javobda [DELEGATE:agent_key] bo'lsa -> AI bo'limga vazifa yaratiladi.
  - Javobda [ADD_EMPLOYEE:key] bo'lsa -> yangi xodim MongoDB'ga saqlanadi.
  - Javobda [MESSAGE_HUMAN:employee_key] bo'lsa -> guruhda xodimga
    @username orqali mention qilib xabar yoziladi va javobi kutiladi.
  - Javobda [CREATE_FILE:pdf yoki docx] bo'lsa -> haqiqiy fayl
    generatsiya qilinib, Telegram orqali yuboriladi.
  - Javobda [CREATE_IMAGE] bo'lsa -> yangi rasm generatsiya qilinadi;
    [EDIT_IMAGE] bo'lsa -> foydalanuvchi oxirgi yuborgan rasm tahrirlanadi.
  - Javobda [SCHEDULE_REMINDER:...] bo'lsa -> belgilangan vaqtda
    xodimga avtomatik eslatma yuborish rejalashtiriladi.
  - Guruhda kimdir yozganda: agar bu username'dan javob kutilayotgan
    bo'lsa, xabar avtomatik asl so'rovchiga (origin_agent boti orqali)
    forward qilinadi.
  - Fon rejimda: shu agentga tegishli 'pending' AI-vazifalarni va
    vaqti kelgan eslatmalarni bajaradi.
"""

import re
import os
import io
import asyncio
import logging
import datetime
from telegram import Update, InputFile
from telegram.error import TimedOut, NetworkError
from telegram.ext import (
    Application, MessageHandler, CommandHandler, ContextTypes, filters,
)

from agents_config import AGENTS, GROUP_CHAT_ID, build_system_prompt
from topics_config import TOPIC_MAP
from llm_client import (
    generate_reply, transcribe_voice, analyze_image, generate_image, edit_image,
)
import file_utils
import web_utils
import video_utils
import db

logger = logging.getLogger(__name__)

# MUHIM: agentning javobida bir nechta teg ketma-ket kelib qolishi
# mumkin (masalan bir necha SCHEDULE_REMINDER). Oddiy "(.+)" (ochko'z)
# naqsh BUTUN qolgan matnni (keyingi teglarni ham, foydalanuvchiga
# mo'ljallangan xulosa gapni ham) bitta tegning "matni" deb yutib
# yuborardi. Shuning uchun har bir teg matni FAQAT keyingi teg
# boshlanishigacha (yoki qator oxirigacha) o'qiladi - "lookahead" orqali.
_NEXT_TAG_BOUNDARY = (
    r"(?=\n\[(?:DELEGATE|MESSAGE_HUMAN|ADD_EMPLOYEE|DELETE_EMPLOYEE|"
    r"CREATE_FILE|SEND_FILE_TO_HUMAN|CREATE_IMAGE|SEND_IMAGE_TO_HUMAN|"
    r"EDIT_IMAGE|SCHEDULE_REMINDER|DOWNLOAD_YOUTUBE|CREATE_REEL)\b|\Z)"
)

DELEGATE_RE = re.compile(
    r"\[DELEGATE:(\w+)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
MESSAGE_HUMAN_RE = re.compile(
    r"\[MESSAGE_HUMAN:(\w+)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
ADD_EMPLOYEE_RE = re.compile(
    r"\[ADD_EMPLOYEE:(\w+)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
DELETE_EMPLOYEE_RE = re.compile(r"\[DELETE_EMPLOYEE:(\w+)\]")
CREATE_FILE_RE = re.compile(
    r"\[CREATE_FILE:(pdf|docx)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
SEND_FILE_TO_HUMAN_RE = re.compile(
    r"\[SEND_FILE_TO_HUMAN:(\w+):(pdf|docx)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY,
    re.DOTALL,
)
CREATE_IMAGE_RE = re.compile(
    r"\[CREATE_IMAGE\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
SEND_IMAGE_TO_HUMAN_RE = re.compile(
    r"\[SEND_IMAGE_TO_HUMAN:(\w+)\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
EDIT_IMAGE_RE = re.compile(
    r"\[EDIT_IMAGE\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)
SCHEDULE_REMINDER_RE = re.compile(
    r"\[SCHEDULE_REMINDER:(\w+):(\w+):(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*(.+?)"
    + _NEXT_TAG_BOUNDARY,
    re.DOTALL,
)
DOWNLOAD_YOUTUBE_RE = re.compile(r"\[DOWNLOAD_YOUTUBE\]\s*(\S+)")
CREATE_REEL_RE = re.compile(
    r"\[CREATE_REEL\]\s*(.+?)" + _NEXT_TAG_BOUNDARY, re.DOTALL
)

GROUP_TYPES = ("group", "supergroup")

# {thread_id: agent_key} -> teskarisini olamiz: {agent_key: thread_id}
REVERSE_TOPIC_MAP = {v: k for k, v in TOPIC_MAP.items()}


def _parse_fields(raw: str) -> dict:
    """'name=Akobir|phone=+998...|sohasi=Video|username=@akobir' -> dict"""
    fields = {}
    for part in raw.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip().lower()] = v.strip()
    return fields


async def _send_with_retry(func, *args, retries: int = 2, **kwargs):
    """
    Telegram'ga katta fayl/rasm yuborishda vaqti-vaqti bilan yuz
    beradigan vaqtinchalik tarmoq uzilishlariga (ConnectTimeout va
    h.k.) chidamli bo'lish uchun - xato bo'lsa, bir necha marta
    qayta urinadi.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return await func(*args, **kwargs)
        except (TimedOut, NetworkError) as e:
            last_exc = e
            logger.warning(
                "Yuborishda vaqtinchalik tarmoq xatosi (urinish %d/%d): %s",
                attempt + 1, retries + 1, e,
            )
            await asyncio.sleep(2)
    raise last_exc


async def send_message_to_employee(bot, agent_key: str, cfg: dict,
                                     employee_key: str, message_text: str,
                                     origin_chat_id: int):
    """
    Xodimga guruhda (yoki uning topicida) @mention orqali xabar yuboradi
    va javobini kuzatish uchun yozuv yaratadi. Bu funksiya HAM oddiy
    MESSAGE_HUMAN oqimida, HAM vaqt bilan rejalashtirilgan eslatmalarda
    (reminder_checker_loop) ishlatiladi - shu bilan ikkala joyda bir xil
    mantiq takrorlanmaydi.

    Qaytaradi: (muvaffaqiyatli_bo'ldimi: bool, xodim_hujjati yoki None)
    """
    employee = db.get_employee(employee_key)
    if not (employee and employee.get("username") and employee["username"] != "-" and GROUP_CHAT_ID):
        return False, None

    target_thread = REVERSE_TOPIC_MAP.get(employee_key)  # ehtiyot uchun (odatda yo'q)
    if target_thread is None:
        target_thread = REVERSE_TOPIC_MAP.get(agent_key)  # o'z bo'limi topici

    mention_text = (
        f"📩 @{employee['username']}, {cfg['display_name']}dan xabar:\n\n"
        f"{message_text}"
    )
    send_kwargs = {"chat_id": int(GROUP_CHAT_ID), "text": mention_text}
    if target_thread is not None:
        send_kwargs["message_thread_id"] = target_thread
    await _send_with_retry(bot.send_message, **send_kwargs)

    db.create_human_task(
        employee_key, employee["username"], int(GROUP_CHAT_ID),
        target_thread, message_text, origin_chat_id, agent_key,
    )
    return True, employee


def build_worker(agent_key: str, bots: dict) -> Application:
    cfg = AGENTS[agent_key]
    token = os.getenv(cfg["token_env"])
    if not token:
        raise RuntimeError(f"{cfg['token_env']} .env faylida topilmadi")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(30)
        .build()
    )

    # ---------- Guruhda "chaqirilganmi" tekshiruvi ----------

    async def is_addressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        chat = update.effective_chat
        if chat.type not in GROUP_TYPES:
            return True  # shaxsiy chatda har doim javob beramiz

        msg = update.message
        text = (msg.text or msg.caption or "").strip()
        thread_id = getattr(msg, "message_thread_id", None)
        topic_owner = TOPIC_MAP.get(thread_id) if thread_id is not None else None

        # ISTISNO: Direktordan boshqa har bir bot, BOSHQA bo'limga tegishli
        # topic'da UMUMAN ishlamaydi (hatto chaqirilsa ham). Direktor esa
        # istalgan topicda ishlashi mumkin.
        if agent_key != "direktor" and topic_owner is not None and topic_owner != agent_key:
            return False

        # 1) shu bot O'ZINING topic'ida yozilganmi - @mention shart emas
        if thread_id is not None and topic_owner == agent_key:
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
        # So'rov qaysi topicdan kelgan bo'lsa, javob (jumladan fayl/rasm)
        # ham o'sha topicga qaytishi uchun thread_id'ni saqlab qo'yamiz.
        origin_thread_id = getattr(update.message, "message_thread_id", None)

        db.save_message(agent_key, chat_id, "user", user_text)
        history = db.get_history(agent_key, chat_id)

        system_prompt = build_system_prompt(agent_key)
        reply = generate_reply(cfg["provider"], cfg["model"], system_prompt, history)

        visible_reply = reply

        # a) AI bo'limga delegatsiya
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

        # b) Yangi xodim qo'shish / tahrirlash
        add_emp_match = ADD_EMPLOYEE_RE.search(reply)
        if add_emp_match:
            emp_key = add_emp_match.group(1).strip().lower()
            fields = _parse_fields(add_emp_match.group(2))
            visible_reply = reply[: add_emp_match.start()].strip()
            db.upsert_employee(emp_key, fields)
            visible_reply += (
                f"\n\n✅ Xodim ma'lumotlari saqlandi: "
                f"{fields.get('name', emp_key)} ({emp_key})."
            )

        # b2) Xodimni o'chirish
        delete_emp_match = DELETE_EMPLOYEE_RE.search(reply)
        if delete_emp_match:
            emp_key = delete_emp_match.group(1).strip().lower()
            visible_reply = reply[: delete_emp_match.start()].strip()
            removed = db.delete_employee(emp_key)
            if removed:
                visible_reply += f"\n\n🗑 Xodim ro'yxatdan o'chirildi: {emp_key}."
            else:
                visible_reply += f"\n\n⚠️ '{emp_key}' nomli xodim topilmadi."

        # b3) Fayl (PDF/Word) yaratish va yuborish
        create_file_match = CREATE_FILE_RE.search(reply)
        if create_file_match:
            file_type = create_file_match.group(1).strip().lower()
            body_raw = create_file_match.group(2).strip()
            visible_reply = reply[: create_file_match.start()].strip()

            parts = body_raw.split("\n", 1)
            title = (parts[0].strip() or "Hujjat")[:60]
            body_text = parts[1].strip() if len(parts) > 1 else ""

            try:
                if file_type == "docx":
                    file_bytes = file_utils.create_docx(title, body_text)
                    filename = f"{title}.docx"
                else:
                    file_bytes = file_utils.create_pdf(title, body_text)
                    filename = f"{title}.pdf"

                await _send_with_retry(
                    context.bot.send_document,
                    chat_id=chat_id,
                    document=InputFile(io.BytesIO(file_bytes), filename=filename),
                    message_thread_id=origin_thread_id,
                )
                visible_reply += f"\n\n📎 Fayl tayyorlandi va yuborildi: {filename}"
            except Exception as e:
                logger.exception("Fayl yaratishda xatolik: %s", e)
                visible_reply += "\n\n⚠️ Faylni yaratishda xatolik yuz berdi."

        # c) Xodimga guruhda @mention orqali xabar yuborish
        human_match = MESSAGE_HUMAN_RE.search(reply)
        if human_match:
            employee_key = human_match.group(1).strip().lower()
            message_text = human_match.group(2).strip()
            visible_reply = reply[: human_match.start()].strip()

            ok, employee = await send_message_to_employee(
                context.bot, agent_key, cfg, employee_key, message_text, chat_id
            )
            if ok:
                visible_reply += (
                    f"\n\n📨 Xabar guruhda @{employee['username']}ga yuborildi. "
                    "Javob kelgach, sizga darhol xabar beraman."
                )
            else:
                visible_reply += (
                    f"\n\n⚠️ '{employee_key}' xodimi topilmadi yoki "
                    "GROUP_CHAT_ID sozlanmagan."
                )

        # c2) Xodimga guruhda fayl (PDF/Word) yuborish
        send_file_match = SEND_FILE_TO_HUMAN_RE.search(reply)
        if send_file_match:
            employee_key = send_file_match.group(1).strip().lower()
            file_type = send_file_match.group(2).strip().lower()
            body_raw = send_file_match.group(3).strip()
            visible_reply = reply[: send_file_match.start()].strip()

            employee = db.get_employee(employee_key)
            if employee and employee.get("username") and employee["username"] != "-" and GROUP_CHAT_ID:
                parts = body_raw.split("\n", 1)
                title = (parts[0].strip() or "Hujjat")[:60]
                body_text = parts[1].strip() if len(parts) > 1 else ""

                try:
                    if file_type == "docx":
                        file_bytes = file_utils.create_docx(title, body_text)
                        filename = f"{title}.docx"
                    else:
                        file_bytes = file_utils.create_pdf(title, body_text)
                        filename = f"{title}.pdf"

                    target_thread = REVERSE_TOPIC_MAP.get(employee_key)
                    if target_thread is None:
                        target_thread = REVERSE_TOPIC_MAP.get(agent_key)

                    send_kwargs = {
                        "chat_id": int(GROUP_CHAT_ID),
                        "document": InputFile(io.BytesIO(file_bytes), filename=filename),
                        "caption": (
                            f"📎 @{employee['username']}, {cfg['display_name']}dan fayl:"
                        ),
                    }
                    if target_thread is not None:
                        send_kwargs["message_thread_id"] = target_thread
                    await _send_with_retry(context.bot.send_document, **send_kwargs)

                    db.create_human_task(
                        employee_key, employee["username"], int(GROUP_CHAT_ID),
                        target_thread, f"[Fayl yuborildi: {filename}]",
                        chat_id, agent_key,
                    )
                    visible_reply += (
                        f"\n\n📎 Fayl guruhda @{employee['username']}ga yuborildi "
                        f"({filename}). Javob kelgach, sizga xabar beraman."
                    )
                except Exception as e:
                    logger.exception("Xodimga fayl yuborishda xatolik: %s", e)
                    visible_reply += "\n\n⚠️ Faylni yuborishda xatolik yuz berdi."
            else:
                visible_reply += (
                    f"\n\n⚠️ '{employee_key}' xodimi topilmadi yoki "
                    "GROUP_CHAT_ID sozlanmagan."
                )

        # d) Haqiqiy rasm generatsiya qilish (foydalanuvchining o'ziga)
        create_image_match = CREATE_IMAGE_RE.search(reply)
        if create_image_match:
            image_prompt = create_image_match.group(1).strip()
            visible_reply = reply[: create_image_match.start()].strip()

            image_bytes = generate_image(image_prompt)
            if image_bytes:
                await _send_with_retry(
                    context.bot.send_photo,
                    chat_id=chat_id,
                    photo=InputFile(io.BytesIO(image_bytes), filename="rasm.png"),
                    message_thread_id=origin_thread_id,
                )
                visible_reply += "\n\n🖼 Rasm tayyorlandi va yuborildi."
            else:
                visible_reply += "\n\n⚠️ Rasmni generatsiya qilishda xatolik yuz berdi."

        # d3) Mavjud (oxirgi yuborilgan) rasmni tahrirlash
        edit_image_match = EDIT_IMAGE_RE.search(reply)
        if edit_image_match:
            edit_prompt = edit_image_match.group(1).strip()
            visible_reply = reply[: edit_image_match.start()].strip()

            last_file_id = db.get_last_photo(agent_key, chat_id)
            if not last_file_id:
                visible_reply += (
                    "\n\n⚠️ Tahrirlanadigan rasm topilmadi - iltimos, "
                    "avval rasmni yuboring."
                )
            else:
                try:
                    tg_file = await context.bot.get_file(last_file_id)
                    original_bytes = bytes(await tg_file.download_as_bytearray())
                    edited_bytes = edit_image(original_bytes, edit_prompt)
                    if edited_bytes:
                        await _send_with_retry(
                            context.bot.send_photo,
                            chat_id=chat_id,
                            photo=InputFile(io.BytesIO(edited_bytes), filename="tahrirlangan.png"),
                            message_thread_id=origin_thread_id,
                        )
                        visible_reply += "\n\n🖼 Tahrirlangan rasm tayyor va yuborildi."
                    else:
                        visible_reply += "\n\n⚠️ Rasmni tahrirlashda xatolik yuz berdi."
                except Exception as e:
                    logger.exception("Rasm tahrirlashda xatolik: %s", e)
                    visible_reply += "\n\n⚠️ Rasmni tahrirlashda xatolik yuz berdi."

        # d2) Xodimga guruhda rasm yuborish
        send_image_match = SEND_IMAGE_TO_HUMAN_RE.search(reply)
        if send_image_match:
            employee_key = send_image_match.group(1).strip().lower()
            image_prompt = send_image_match.group(2).strip()
            visible_reply = reply[: send_image_match.start()].strip()

            employee = db.get_employee(employee_key)
            if employee and employee.get("username") and employee["username"] != "-" and GROUP_CHAT_ID:
                image_bytes = generate_image(image_prompt)
                if image_bytes:
                    target_thread = REVERSE_TOPIC_MAP.get(employee_key)
                    if target_thread is None:
                        target_thread = REVERSE_TOPIC_MAP.get(agent_key)

                    send_kwargs = {
                        "chat_id": int(GROUP_CHAT_ID),
                        "photo": InputFile(io.BytesIO(image_bytes), filename="rasm.png"),
                        "caption": (
                            f"🖼 @{employee['username']}, {cfg['display_name']}dan rasm:"
                        ),
                    }
                    if target_thread is not None:
                        send_kwargs["message_thread_id"] = target_thread
                    await _send_with_retry(context.bot.send_photo, **send_kwargs)

                    db.create_human_task(
                        employee_key, employee["username"], int(GROUP_CHAT_ID),
                        target_thread, "[Rasm yuborildi]", chat_id, agent_key,
                    )
                    visible_reply += (
                        f"\n\n🖼 Rasm guruhda @{employee['username']}ga yuborildi."
                    )
                else:
                    visible_reply += "\n\n⚠️ Rasmni generatsiya qilishda xatolik yuz berdi."
            else:
                visible_reply += (
                    f"\n\n⚠️ '{employee_key}' xodimi topilmadi yoki "
                    "GROUP_CHAT_ID sozlanmagan."
                )

        # e) Vaqt bilan rejalashtirilgan eslatma
        schedule_match = SCHEDULE_REMINDER_RE.search(reply)
        if schedule_match:
            target_agent = schedule_match.group(1).strip().lower()
            employee_key = schedule_match.group(2).strip().lower()
            datetime_str = schedule_match.group(3).strip()
            reminder_text = schedule_match.group(4).strip()
            visible_reply = reply[: schedule_match.start()].strip()

            if target_agent not in AGENTS:
                visible_reply += (
                    f"\n\n⚠️ '{target_agent}' nomli bo'lim mavjud emas. "
                    f"Mavjud bo'limlar: {', '.join(AGENTS.keys())}."
                )
            else:
                try:
                    naive_dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                    run_at_utc = naive_dt - datetime.timedelta(hours=5)  # Toshkent -> UTC
                    db.create_scheduled_reminder(
                        target_agent, employee_key, run_at_utc, reminder_text,
                        agent_key, chat_id,
                    )
                    target_display = AGENTS[target_agent]["display_name"]
                    visible_reply += (
                        f"\n\n⏰ Eslatma rejalashtirildi: {datetime_str} - "
                        f"{target_display} bajaradi. "
                        "Natijasini sizga xabar qilaman."
                    )
                except Exception as e:
                    logger.exception("Eslatma rejalashtirishda xatolik: %s", e)
                    visible_reply += "\n\n⚠️ Eslatmani rejalashtirishda xatolik yuz berdi."

        # f) YouTube'dan video yuklash (faqat Mobilograf)
        yt_match = DOWNLOAD_YOUTUBE_RE.search(reply)
        if yt_match:
            youtube_url = yt_match.group(1).strip()
            visible_reply = reply[: yt_match.start()].strip()

            chat_key = f"{agent_key}_{chat_id}"
            result = await video_utils.download_youtube(youtube_url, chat_key)
            if result.get("error"):
                err = result["error"]
                if "sign in" in err.lower() or "sign-in" in err.lower():
                    visible_reply += (
                        "\n\n⚠️ YouTube bu videoni yuklashdan oldin "
                        "\"tizimga kirish\" tasdig'ini talab qilmoqda "
                        "(bu YouTube'ning bot-himoyasi, xatolik emas). "
                        "Buni tuzatish uchun YOUTUBE_COOKIES sozlamasini "
                        "qo'shish kerak - operatoringizdan so'rang."
                    )
                else:
                    visible_reply += f"\n\n⚠️ Videoni yuklab bo'lmadi: {err}"
            else:
                db.save_last_video(
                    agent_key, chat_id, result["path"],
                    result.get("title", ""), result.get("duration", 0),
                )
                dur_min = int(result.get("duration", 0)) // 60
                dur_sec = int(result.get("duration", 0)) % 60
                visible_reply += (
                    f"\n\n✅ Video yuklandi: \"{result.get('title', '')}\"\n"
                    f"Davomiyligi: {dur_min} daqiqa {dur_sec} soniya.\n"
                    "Endi shundan qiziqarli-kadrlar videosi (reel) "
                    "yaratishimni xohlasangiz, ayting."
                )

        # g) Yuklangan/yuborilgan videodan "reel" yaratish (faqat Mobilograf)
        reel_match = CREATE_REEL_RE.search(reply)
        if reel_match:
            user_hint = reel_match.group(1).strip()[:200]
            visible_reply = reply[: reel_match.start()].strip()

            last_video = db.get_last_video(agent_key, chat_id)
            if not last_video or not os.path.exists(last_video.get("local_path", "")):
                visible_reply += (
                    "\n\n⚠️ Ishlanadigan video topilmadi - avval YouTube "
                    "havolasini yuboring yoki video faylni to'g'ridan-to'g'ri "
                    "yuboring."
                )
            else:
                await update.message.reply_text(
                    "🎬 Video tahlil qilinmoqda va eng mos format/uslub "
                    "tanlanmoqda (1-3 daqiqa vaqt olishi mumkin)..."
                )
                try:
                    src_path = last_video["local_path"]
                    chat_key = f"{agent_key}_{chat_id}"
                    info = video_utils.get_video_info(src_path)
                    duration = info.get("duration", 30)

                    frames = await video_utils.extract_candidate_frames(
                        src_path, os.path.dirname(src_path), count=8
                    )
                    sheet_bytes = video_utils.build_contact_sheet(frames)

                    vision_response = analyze_image(
                        cfg["provider"], cfg["model"], sheet_bytes,
                        "Bu - videodan olingan kadrlar to'plami (chap "
                        "yuqoridan o'ngga, yuqoridan pastga vaqt tartibida). "
                        f"Video davomiyligi: {int(duration)} soniya.\n\n"
                        f"Foydalanuvchi ko'rsatmasi: {user_hint or '(berilmagan - o‘zing hal qil)'}\n\n"
                        "Vazifang: shu video mazmuniga ENG MOS qisqa-metrajli "
                        "kontent uchun KREATIV qaror qabul qilish. O'zing "
                        "hal qil:\n"
                        "1) FORMAT - qaysi biri mos: 9:16 (Reels/TikTok/"
                        "Stories), 1:1 (kvadrat post), 16:9 (YouTube/"
                        "landshaft), 4:5 (Instagram post). Foydalanuvchi "
                        "ko'rsatmasida aniq format bo'lsa, o'shani tanla.\n"
                        "2) USLUB - video kayfiyatiga qarab: bold_badges "
                        "(raqamli belgili, energetik - o'yin/sport/reklama "
                        "uchun), minimal_caption (toza, zamonaviy, pastki "
                        "kichik yozuv - vlog/lifestyle uchun), cinematic_bar "
                        "(nozik letterbox chiziqlar - tabiat/hujjatli uslub).\n"
                        "3) NECHTA LAHZA kerak (2 dan 6 tagacha) - "
                        "videoning boyligiga qarab o'zing tanla.\n"
                        "4) HAR BIR LAHZA uchun: necha soniya davom etishi "
                        "(3-12 oralig'ida), video kayfiyatiga mos rang "
                        "(#RRGGBB), va qisqa o'zbekcha sarlavha (2-3 so'z).\n\n"
                        "Aynan shu formatda javob ber, boshqa izoh yozma:\n"
                        "format: <9:16 yoki 1:1 yoki 16:9 yoki 4:5>\n"
                        "style: <bold_badges yoki minimal_caption yoki cinematic_bar>\n"
                        "title: <umumiy sarlavha, KATTA HARFLAR, qisqa>\n"
                        "MM:SS | davomiylik_soniya | #RRGGBB | Sarlavha\n"
                        "(kerakli sondagi shunday qatorlar, 2-6 ta)",
                    )
                    plan = video_utils.parse_reel_plan(vision_response, duration)

                    output_path = await video_utils.build_highlight_reel(
                        src_path, plan, os.path.dirname(src_path),
                    )

                    await _send_with_retry(
                        context.bot.send_video,
                        chat_id=chat_id,
                        video=InputFile(output_path),
                        message_thread_id=origin_thread_id,
                        caption=f"🎬 {plan['title']}",
                    )
                    segments_list = "\n".join(
                        f"{i}. {s['caption']} ({s['duration']:.0f}s)"
                        for i, s in enumerate(plan["segments"], 1)
                    )
                    visible_reply += (
                        f"\n\n✅ Reel tayyor va yuborildi!\n"
                        f"Format: {plan['format']} | Uslub: {plan['style']}\n"
                        f"Ichidagi lahzalar:\n{segments_list}"
                    )
                    video_utils.cleanup(chat_key)
                except Exception as e:
                    logger.exception("Reel yaratishda xatolik: %s", e)
                    visible_reply += "\n\n⚠️ Reel yaratishda xatolik yuz berdi."

        db.save_message(agent_key, chat_id, "assistant", visible_reply)
        await update.message.reply_text(visible_reply)

    # ---------- Guruhda xodimning javobini aniqlash ----------

    async def try_handle_employee_reply(update: Update) -> bool:
        """True qaytarsa - bu xabar xodim javobi edi va allaqachon forward qilindi."""
        chat = update.effective_chat
        if chat.type not in GROUP_TYPES:
            return False
        user = update.message.from_user
        username = (user.username or "") if user else ""
        if not username:
            return False

        claimed = db.claim_human_task_by_username(chat.id, username, update.message.text or "")
        if not claimed:
            return False

        origin_agent_key = claimed.get("origin_agent", agent_key)
        origin_bot = bots.get(origin_agent_key) or bots.get(agent_key)
        text = f"📩 @{username} javob berdi:\n\n{update.message.text}"
        await _send_with_retry(origin_bot.send_message, chat_id=claimed["origin_chat_id"], text=text)
        # MUHIM: natijani origin_agent (masalan Direktor)ning o'z xotirasiga
        # ham yozamiz - shunda keyinroq so'ralsa, agent buni "eslaydi".
        db.save_message(origin_agent_key, claimed["origin_chat_id"], "assistant", text)
        await update.message.reply_text("✅ Javobingiz uzatildi, rahmat!")
        return True

    # ---------- Matn xabarlari ----------

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if not db.claim_update(agent_key, update.update_id):
            return  # bu xabar allaqachon qayta ishlangan (takror)
        if await try_handle_employee_reply(update):
            return
        if not await is_addressed(update, context):
            return

        user_text = update.message.text
        chat_id = update.effective_chat.id
        urls = web_utils.find_urls(user_text)
        if urls:
            for url in urls[:2]:  # ko'pi bilan 2 ta havola
                # MUHIM: Mobilograf uchun YouTube havolasi kelsa, AI
                # "urinib ko'rish kerakmi" deb o'zi hal qilishiga
                # QOLDIRMAYMIZ (u ba'zan suhbat tarixiga qarab, haqiqiy
                # urinishsiz voz kechishi mumkin edi). Buning o'rniga
                # tizim MAJBURIY ravishda, har safar, haqiqiy yuklash
                # urinishini o'zi amalga oshiradi va NATIJANI (muvaffaqiyat
                # yoki aniq xato) to'g'ridan-to'g'ri AI kontekstiga beradi.
                if agent_key == "mobilograf" and web_utils.is_youtube_url(url):
                    await update.message.reply_text(
                        "🎬 YouTube havolasi aniqlandi, yuklab olishga "
                        "harakat qilyapman..."
                    )
                    chat_key = f"{agent_key}_{chat_id}"
                    result = await video_utils.download_youtube(url, chat_key)
                    if "error" in result:
                        user_text += (
                            f"\n\n[TIZIM: {url} havolasini yuklashga "
                            f"HOZIRGINA haqiqiy urinish qilindi va XATO "
                            f"chiqdi:\n{result['error']}\n"
                            "Bu ANIQ, YANGI natija - eski xotiraga emas, "
                            "shu xato matniga tayanib javob ber.]"
                        )
                    else:
                        db.save_last_video(
                            agent_key, chat_id, result["path"],
                            result.get("title", "Video"),
                        )
                        user_text += (
                            f"\n\n[TIZIM: {url} havolasi HOZIRGINA "
                            f"muvaffaqiyatli yuklandi. Sarlavha: "
                            f"{result.get('title', '-')}, davomiyligi: "
                            f"{int(result.get('duration', 0))} soniya. "
                            "Endi foydalanuvchidan reel formatini/uslubini "
                            "so'rab, CREATE_REEL tegini ishlatishing mumkin.]"
                        )
                    continue

                # Boshqa (YouTube bo'lmagan) havolalar uchun oddiy o'qish:
                page_content = web_utils.fetch_url_text(url)
                user_text += f"\n\n[Havola tarkibi - {url}]:\n{page_content}"

        await process_user_text(update.effective_chat.id, user_text, update, context)

    # ---------- Fayllar (.txt, .docx, .pdf) ----------

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.document:
            return
        if not db.claim_update(agent_key, update.update_id):
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
        if not db.claim_update(agent_key, update.update_id):
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

    # ---------- Rasmlar ----------

    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.photo:
            return
        if not db.claim_update(agent_key, update.update_id):
            return
        if not await is_addressed(update, context):
            return

        await update.message.reply_text("🖼 Rasm qabul qilindi, tahlil qilyapman...")

        photo = update.message.photo[-1]  # eng katta o'lchamdagisi
        tg_file = await photo.get_file()
        photo_bytes = bytes(await tg_file.download_as_bytearray())

        # Keyinchalik "shu rasmni tahrirla" desa foydalanish uchun
        # oxirgi yuborilgan rasmning file_id'sini saqlab qo'yamiz.
        db.save_last_photo(agent_key, update.effective_chat.id, photo.file_id)

        description = analyze_image(
            cfg["provider"], cfg["model"], photo_bytes,
            "Bu rasmda nima ko'rinib turibdi? Batafsil va aniq tasvirlab "
            "ber: obyektlar, muhit, ranglar, matn (agar bo'lsa), umumiy "
            "kayfiyat va uslub.",
        )
        if not description:
            description = "(Rasmni tahlil qilib bo'lmadi.)"

        caption = update.message.caption or "(izoh yozilmagan)"
        user_text = (
            f"[Foydalanuvchi rasm yubordi]\n\n"
            f"Rasm tavsifi (AI ko'rish orqali):\n{description}\n\n"
            f"Foydalanuvchi izohi: {caption}"
        )
        await process_user_text(update.effective_chat.id, user_text, update, context)

    # ---------- Videolar ----------

    async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.video:
            return
        if not db.claim_update(agent_key, update.update_id):
            return
        if not await is_addressed(update, context):
            return

        video = update.message.video
        chat_id = update.effective_chat.id

        if agent_key == "mobilograf":
            # Telegram Bot API cheklovi: botlar faylni faqat 20 MB
            # gacha yuklab olishi mumkin. Avvaldan tekshirib, foydasiz
            # urinishning oldini olamiz va foydalanuvchiga aniq
            # tushuntiramiz.
            MAX_BOT_API_FILE_MB = 20
            size_mb = (video.file_size or 0) / (1024 * 1024)
            if size_mb > MAX_BOT_API_FILE_MB:
                await update.message.reply_text(
                    f"⚠️ Bu video juda katta ({size_mb:.0f} MB). Telegram "
                    f"Bot API orqali botlar faqat {MAX_BOT_API_FILE_MB} MB "
                    "gacha bo'lgan fayllarni qabul qila oladi - bu "
                    "Telegramning o'z cheklovi, tuzatib bo'lmaydi.\n\n"
                    "Iltimos: 1) videoni YouTube'ga joylab, havolasini "
                    "yuboring, YOKI 2) videoni qisqartirib/siqib, "
                    f"{MAX_BOT_API_FILE_MB} MB dan kichik holda qayta "
                    "yuboring."
                )
                return

            # Mobilograf uchun: to'liq videoni yuklab, keyinchalik
            # "reel yarat" so'ralganda ishlatish uchun saqlab qo'yamiz.
            await update.message.reply_text(
                "🎬 Video qabul qilindi va yuklanmoqda..."
            )
            chat_key = f"{agent_key}_{chat_id}"
            dest_dir = os.path.join(video_utils.MEDIA_DIR, chat_key)
            os.makedirs(dest_dir, exist_ok=True)
            local_path = os.path.join(dest_dir, "source.mp4")

            try:
                tg_file = await video.get_file()
                await tg_file.download_to_drive(local_path)
            except Exception as e:
                logger.exception("Video yuklab olishda xatolik: %s", e)
                await update.message.reply_text(
                    "⚠️ Videoni yuklab bo'lmadi (juda katta yoki tarmoq "
                    "xatosi). Iltimos, YouTube havolasi orqali yuboring "
                    "yoki kichikroq video bilan qayta urinib ko'ring."
                )
                return

            db.save_last_video(
                agent_key, chat_id, local_path,
                update.message.caption or "Yuborilgan video",
                video.duration or 0,
            )
            user_text = (
                f"[Foydalanuvchi video fayl yubordi, davomiyligi "
                f"~{video.duration or 0} soniya. Video muvaffaqiyatli "
                f"yuklab olindi va reel yaratishga tayyor.]\n\n"
                f"Foydalanuvchi izohi: {update.message.caption or '(yo`q)'}"
            )
            await process_user_text(chat_id, user_text, update, context)
            return

        # Boshqa agentlar uchun: avvalgidek faqat asosiy kadr tahlili
        await update.message.reply_text(
            "🎬 Video qabul qilindi. Eslatma: hozircha videoning to'liq "
            "davomida emas, faqat asosiy kadridan tahlil qilaman..."
        )

        description = ""
        if video.thumbnail:
            try:
                tg_file = await video.thumbnail.get_file()
                thumb_bytes = bytes(await tg_file.download_as_bytearray())
                description = analyze_image(
                    cfg["provider"], cfg["model"], thumb_bytes,
                    "Bu - video faylning asosiy kadri (thumbnail). Unda nima "
                    "ko'rinib turibdi? Batafsil tasvirlab ber.",
                )
            except Exception as e:
                logger.exception("Video thumbnail tahlilida xatolik: %s", e)
        if not description:
            description = "(Video kadrini tahlil qilib bo'lmadi.)"

        caption = update.message.caption or "(izoh yozilmagan)"
        duration = video.duration or 0
        user_text = (
            f"[Foydalanuvchi video yubordi, davomiyligi ~{duration} soniya]\n\n"
            f"Videoning asosiy kadri tavsifi (AI ko'rish orqali):\n{description}\n\n"
            f"Foydalanuvchi izohi: {caption}\n\n"
            "(Eslatma: bu tahlil faqat videoning bitta asosiy kadriga "
            "asoslangan, to'liq video emas.)"
        )
        await process_user_text(update.effective_chat.id, user_text, update, context)

    # ---------- /topicid - topic ID'ni tezda topish uchun yordamchi buyruq ----------

    async def handle_topicid(update: Update, context: ContextTypes.DEFAULT_TYPE):
        thread_id = getattr(update.message, "message_thread_id", None)
        if thread_id is None:
            await update.message.reply_text(
                "Bu — General (asosiy) mavzu, uning alohida thread_id'si "
                "yo'q. Bu yerga botlar faqat @mention orqali chaqiriladi."
            )
        else:
            await update.message.reply_text(
                f"Bu topic'ning ID raqami: {thread_id}\n\n"
                f"topics_config.py fayliga shunday qo'shing:\n"
                f"{thread_id}: \"<agent_key>\","
            )

    app.add_handler(CommandHandler("topicid", handle_topicid))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    return app


async def task_checker_loop(agent_key: str, bots: dict, interval_sec: int = 20):
    """
    Fon rejimida: shu agentga berilgan yangi AI-vazifalarni tekshirib bajaradi.
    Natija - vazifani KIM SO'RAGAN bo'lsa o'sha bo'lim (from_agent) boti
    orqali, aynan so'ragan chatga (origin_chat_id) qaytariladi.
    """
    cfg = AGENTS[agent_key]
    while True:
        try:
            pending = db.get_pending_tasks(agent_key)
            for task in pending:
                system_prompt = build_system_prompt(agent_key)
                history = [{"role": "user", "content": task["task_text"]}]
                result = generate_reply(cfg["provider"], cfg["model"], system_prompt, history)
                db.mark_task_done(task["_id"], result)

                origin_agent_key = task.get("from_agent", agent_key)
                origin_bot = bots.get(origin_agent_key) or bots.get(agent_key)
                text = f"✅ {cfg['display_name']} bajardi:\n\n{result}"
                await _send_with_retry(origin_bot.send_message, chat_id=task["origin_chat_id"], text=text)
                # MUHIM: natijani origin_agent (masalan Direktor)ning o'z
                # xotirasiga ham yozamiz - shunda keyinroq "o'sha savollarni
                # yubora olasanmi" deb so'ralsa, agent buni eslaydi.
                db.save_message(origin_agent_key, task["origin_chat_id"], "assistant", text)
        except Exception:
            logger.exception("task_checker_loop xatolik (%s)", agent_key)

        await asyncio.sleep(interval_sec)


async def reminder_checker_loop(agent_key: str, bots: dict, interval_sec: int = 60):
    """
    Fon rejimida: shu agentga rejalashtirilgan, vaqti kelgan eslatmalarni
    tekshirib, xodimga guruhda @mention orqali yuboradi. Natija - "kim
    rejalashtirgan bo'lsa o'sha bo'lim (origin_agent) boti orqali",
    aynan so'ragan chatga qaytariladi (xuddi task_checker_loop kabi).
    Xodimning keyingi javobi esa mavjud human_task mexanizmi orqali
    (try_handle_employee_reply) avtomatik forward qilinadi.
    """
    cfg = AGENTS[agent_key]
    bot = bots[agent_key]
    while True:
        try:
            due = db.get_due_reminders(agent_key)
            for reminder in due:
                ok, employee = await send_message_to_employee(
                    bot, agent_key, cfg, reminder["employee_key"],
                    reminder["message_text"], reminder["origin_chat_id"],
                )
                db.mark_reminder_done(reminder["_id"])

                origin_agent_key = reminder.get("origin_agent", agent_key)
                origin_bot = bots.get(origin_agent_key) or bot

                if ok:
                    text = (
                        f"⏰ {cfg['display_name']}: rejalashtirilgan eslatma "
                        f"@{employee['username']}ga yuborildi. Javob kelgach "
                        "sizga xabar beraman."
                    )
                else:
                    text = (
                        f"⚠️ {cfg['display_name']}: rejalashtirilgan eslatmani "
                        f"yuborib bo'lmadi - xodim topilmadi yoki "
                        "GROUP_CHAT_ID sozlanmagan."
                    )
                await _send_with_retry(origin_bot.send_message, chat_id=reminder["origin_chat_id"], text=text)
                db.save_message(origin_agent_key, reminder["origin_chat_id"], "assistant", text)
        except Exception:
            logger.exception("reminder_checker_loop xatolik (%s)", agent_key)

        await asyncio.sleep(interval_sec)
