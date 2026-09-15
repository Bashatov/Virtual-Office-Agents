# -*- coding: utf-8 -*-
"""
Barcha agentlarni (botlarni) bir vaqtda ishga tushiradi.
Railway'da bu fayl "worker" sifatida doim fon rejimida ishlab turadi.

MUHIM: barcha botlarning `bot` obyektlari umumiy `bots` lug'atida
saqlanadi va HAR BIR botga qurilish vaqtidayoq beriladi (reference
orqali). Shu tufayli, masalan, SMM vazifani bajargach yoki xodim
javob bergach, natijani Direktor botining o'zi orqali foydalanuvchiga
qaytarish mumkin bo'ladi.
"""

import asyncio
import logging
from dotenv import load_dotenv

from agents_config import AGENTS
from bot_worker import build_worker, task_checker_loop, reminder_checker_loop

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# httpx har bir Telegram so'rovini ("getUpdates" va h.k.) INFO darajasida
# yozib, loglarni "shovqin"ga to'ldiradi - shuni jimlantiramiz, shunda
# faqat haqiqiy xato/ogohlantirishlar ko'rinadi.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("main")


async def main():
    logger.info("AI Jamoa ishga tushmoqda... (%d ta agent)", len(AGENTS))

    bots = {}  # {agent_key: bot} - barcha handlerlar shu obyektga ishora qiladi
    apps = {}

    # 1) Barcha botlarni quramiz va ishga tushiramiz (polling'siz)
    for agent_key in AGENTS:
        app = build_worker(agent_key, bots)
        await app.initialize()
        await app.start()
        apps[agent_key] = app
        bots[agent_key] = app.bot
        logger.info("✅ %s tayyorlandi", AGENTS[agent_key]["display_name"])

    # 2) Endi `bots` to'liq to'lgan - polling'ni boshlaymiz
    for agent_key, app in apps.items():
        await app.updater.start_polling()
        logger.info("✅ %s ishga tushdi", AGENTS[agent_key]["display_name"])

    # 3) Fon-vazifa tekshiruvchilarini ishga tushiramiz
    await asyncio.gather(
        *(task_checker_loop(key, bots) for key in AGENTS),
        *(reminder_checker_loop(key, bots) for key in AGENTS),
    )


if __name__ == "__main__":
    asyncio.run(main())
