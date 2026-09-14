# -*- coding: utf-8 -*-
"""
Foydalanuvchi xabarida havola (URL) bo'lsa, o'sha sahifaning matnini
o'qib, agentga kontekst sifatida beradi.

CHEKLOV: Instagram, Facebook, TikTok, YouTube kabi ijtimoiy tarmoq/video
saytlarini o'qib bo'lmaydi - ular login yoki JavaScript orqali
yuklanadi, oddiy HTTP so'rovi bilan ochilmaydi. Bunday hollarda
foydalanuvchiga fayl/rasm/video yuklab yuborishni tavsiya qilamiz.
"""

import re
import logging
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s]+")

BLOCKED_DOMAINS = [
    "instagram.com", "facebook.com", "fb.com", "tiktok.com",
    "youtube.com", "youtu.be", "twitter.com", "x.com",
]

MAX_CHARS = 4000


def find_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def fetch_url_text(url: str) -> str:
    for domain in BLOCKED_DOMAINS:
        if domain in url:
            return (
                f"(Bu havola '{domain}' saytiga tegishli - bunday ijtimoiy "
                "tarmoq/video saytlarini o'qib bo'lmaydi, chunki ular "
                "login yoki maxsus render talab qiladi. Buning o'rniga "
                "foydalanuvchidan faylni/rasmni/videoni to'g'ridan-to'g'ri "
                "yuklab yuborishini so'ra.)"
            )
    try:
        resp = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        body = "\n".join(lines)

        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS] + "\n...(sahifa matni uzun bo'lgani uchun qisqartirildi)"

        return f"Sahifa sarlavhasi: {title}\n\n{body}" if title else body

    except Exception as e:
        logger.exception("Havolani o'qishda xatolik: %s", e)
        return f"(Havolani o'qishda xatolik yuz berdi: {e})"
