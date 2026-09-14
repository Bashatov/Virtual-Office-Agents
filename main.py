# -*- coding: utf-8 -*-
"""
Barcha agentlarni (botlarni) bir vaqtda ishga tushiradi.
Railway'da bu fayl "worker" sifatida doim fon rejimida ishlab turadi.
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


async def run_agent(agent_key: str):
    app = build_worker(agent_key)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("✅ %s ishga tushdi", AGENTS[agent_key]["display_name"])
    # Fon rejimida vazifalarni tekshirib turadi
    await task_checker_loop(agent_key, app)


async def main():
    logger.info("AI Jamoa ishga tushmoqda... (%d ta agent)", len(AGENTS))
    await asyncio.gather(*(run_agent(key) for key in AGENTS))


if __name__ == "__main__":
    asyncio.run(main())
