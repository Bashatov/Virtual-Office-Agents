# -*- coding: utf-8 -*-
"""
Barcha agentlarni (botlarni) bir vaqtda ishga tushiradi.
Railway'da bu fayl "worker" sifatida doim fon rejimida ishlab turadi.

MUHIM: barcha botlarning `bot` obyektlari umumiy `bots` lug'atida
saqlanadi - shunda masalan SMM vazifani bajargach, natijani
Direktor botining o'zi orqali foydalanuvchiga qaytarish mumkin bo'ladi
(chunki foydalanuvchi Direktor bilan gaplashgan, SMM bilan emas).
"""

import asyncio
import logging
from dotenv import load_dotenv

from agents_config import AGENTS
from bot_worker import build_worker, task_checker_loop

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


async def main():
    logger.info("AI Jamoa ishga tushmoqda... (%d ta agent)", len(AGENTS))

    # 1) Avval barcha botlarni quramiz va ishga tushiramiz
    apps = {}
    for agent_key in AGENTS:
        app = build_worker(agent_key)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        apps[agent_key] = app
        logger.info("✅ %s ishga tushdi", AGENTS[agent_key]["display_name"])

    # 2) Barcha bot obyektlarini umumiy lug'atga yig'amiz
    bots = {key: app.bot for key, app in apps.items()}

    # 3) Endi har bir agent uchun fon-vazifa tekshiruvchisini ishga tushiramiz
    await asyncio.gather(
        *(task_checker_loop(key, bots) for key in AGENTS)
    )


if __name__ == "__main__":
    asyncio.run(main())
