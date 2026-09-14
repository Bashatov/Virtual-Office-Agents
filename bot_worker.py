# -*- coding: utf-8 -*-
"""
Bitta agent uchun to'liq ishchi mantiq:
  1. Foydalanuvchidan/guruhdan xabar keladi -> LLM javob beradi
  2. Agar javobda [DELEGATE:agent_key] bo'lsa -> boshqa bo'limga vazifa yaratiladi
  3. Fon rejimda: shu agentga tegishli 'pending' vazifalarni tekshirib,
     bajarib, guruhga natijani yozib turadi
"""

import re
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from agents_config import AGENTS, GROUP_CHAT_ID
from llm_client import generate_reply
import db

logger = logging.getLogger(__name__)

DELEGATE_RE = re.compile(r"\[DELEGATE:(\w+)\]\s*(.+)", re.DOTALL)


def build_worker(agent_key: str) -> Application:
    cfg = AGENTS[agent_key]
    token = __import__("os").getenv(cfg["token_env"])
    if not token:
        raise RuntimeError(f"{cfg['token_env']} .env faylida topilmadi")

    app = Application.builder().token(token).build()

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_text = update.message.text
        if not user_text:
            return

        db.save_message(agent_key, chat_id, "user", user_text)
        history = db.get_history(agent_key, chat_id)

        reply = generate_reply(
            cfg["provider"], cfg["model"], cfg["system_prompt"], history
        )

        # Agar Direktor boshqa bo'limga topshiriq bergan bo'lsa, ajratib olamiz
        delegate_match = DELEGATE_RE.search(reply)
        visible_reply = reply
        if delegate_match:
            to_agent = delegate_match.group(1).strip().lower()
            task_text = delegate_match.group(2).strip()
            visible_reply = reply[: delegate_match.start()].strip()
            if to_agent in AGENTS:
                db.create_task(agent_key, to_agent, task_text, chat_id)
                visible_reply += (
                    f"\n\n📋 Vazifa {AGENTS[to_agent]['display_name']}ga berildi."
                )

        db.save_message(agent_key, chat_id, "assistant", visible_reply)
        await update.message.reply_text(visible_reply)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


async def task_checker_loop(agent_key: str, app: Application, interval_sec: int = 20):
    """Fon rejimida: shu agentga berilgan yangi vazifalarni tekshirib bajaradi."""
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
                text = (
                    f"✅ {cfg['display_name']} bajardi:\n\n{result}"
                )
                await bot.send_message(chat_id=target_chat, text=text)
        except Exception:
            logger.exception("task_checker_loop xatolik (%s)", agent_key)

        await asyncio.sleep(interval_sec)
