# -*- coding: utf-8 -*-
"""
YouTube 2024-2025 yillarda kiritgan "PoToken" (Proof-of-Origin Token)
talabini yengish uchun kerak bo'ladigan yordamchi server.

Bu - yt-dlp'ning o'zi EMAS, balki uning YONIDA fon rejimida ishlaydigan
alohida Node.js xizmati (bgutil-ytdlp-pot-provider). yt-dlp Python
tomonidagi plagin (requirements.txt'da) orqali shu serverga so'rov
yuborib, YouTube uchun kerakli "tasdiqlovchi token"ni oladi - shu orqali
"Sign in to confirm you're not a bot" xatosi (bulut-server IP'laridan
kelayotgan so'rovlar uchun) chetlab o'tiladi.

Manba: https://github.com/Brainicism/bgutil-ytdlp-pot-provider
"""

import os
import time
import shutil
import logging
import subprocess

logger = logging.getLogger(__name__)

POT_SERVER_DIR = "/tmp/bgutil-ytdlp-pot-provider"
POT_SERVER_PORT = 4416
_REPO_URL = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"


def _run(cmd, cwd=None, timeout=180):
    logger.info("PoToken sozlash: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        logger.error(
            "Buyruq muvaffaqiyatsiz (%s): %s\nSTDOUT: %s\nSTDERR: %s",
            " ".join(cmd), result.returncode, result.stdout[-2000:], result.stderr[-2000:],
        )
        raise RuntimeError(f"'{' '.join(cmd)}' xato bilan tugadi: {result.stderr[-500:]}")
    return result


def ensure_pot_provider_running() -> bool:
    """
    PoToken serverini (agar hali qurilmagan bo'lsa) klonlab-qurib,
    fon rejimida ishga tushiradi. Bu funksiya dastur ishga tushganda
    BIR MARTA chaqiriladi (har bir konteyner qayta ishga tushganda
    qayta bajariladi, chunki Railway konteyneri har safar "toza"
    boshlanadi).

    Muvaffaqiyatli bo'lsa True, xato bo'lsa False qaytaradi - xato
    bo'lsa ham dastur davom etaveradi (PoToken'siz, eski usul bilan
    urinishda davom etadi).
    """
    try:
        if shutil.which("node") is None:
            logger.warning(
                "Node.js topilmadi - PoToken serverini o'rnatib bo'lmaydi "
                "(nixpacks.toml'ni tekshiring)."
            )
            return False

        use_yarn = shutil.which("yarn") is not None

        if not os.path.isdir(POT_SERVER_DIR):
            logger.info("PoToken provider repo'sini yuklab olyapmiz...")
            _run(["git", "clone", "--depth", "1", _REPO_URL, POT_SERVER_DIR], timeout=60)

        server_dir = os.path.join(POT_SERVER_DIR, "server")
        build_marker = os.path.join(server_dir, "build", "main.js")

        if not os.path.exists(build_marker):
            logger.info("PoToken provider serverini qurmoqdamiz (bir martalik, biroz vaqt oladi)...")
            if use_yarn:
                _run(["yarn", "install", "--frozen-lockfile"], cwd=server_dir, timeout=180)
            else:
                logger.warning("yarn topilmadi, npm bilan urinilyapti (zaxira yo'l)...")
                _run(["npm", "install"], cwd=server_dir, timeout=180)
            _run(["npx", "tsc"], cwd=server_dir, timeout=120)

        logger.info("PoToken provider serverini fon rejimida ishga tushiryapmiz...")
        subprocess.Popen(
            ["node", "build/main.js"],
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(2)  # server portni ochishi uchun ozgina kutamiz
        logger.info(
            "✅ PoToken provider server ishga tushdi (port %d).", POT_SERVER_PORT
        )
        return True

    except Exception as e:
        logger.exception(
            "PoToken provider serverini ishga tushirishda xatolik (video "
            "yuklash baribir eski usul bilan davom etadi): %s", e,
        )
        return False
