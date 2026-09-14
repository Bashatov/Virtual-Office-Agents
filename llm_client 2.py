# -*- coding: utf-8 -*-
"""
Claude va GPT-4o uchun yagona chaqiruv interfeysi + ovozli xabarni
matnga o'girish (OpenAI Whisper).
"""

import os
import io
import base64
import logging
from anthropic import Anthropic
from openai import OpenAI

logger = logging.getLogger(__name__)

_anthropic_client = None
_openai_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def generate_reply(provider: str, model: str, system_prompt: str, history: list[dict]) -> str:
    """
    history: [{"role": "user"/"assistant", "content": "..."}]
    Qaytaradi: agentning matn javobi (string)
    """
    try:
        if provider == "claude":
            client = _get_anthropic()
            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                system=system_prompt,
                messages=history,
            )
            return "".join(
                block.text for block in resp.content if block.type == "text"
            ).strip()

        elif provider == "gpt4o":
            client = _get_openai()
            messages = [{"role": "system", "content": system_prompt}] + history
            resp = client.chat.completions.create(
                model=model,
                max_tokens=1500,
                messages=messages,
            )
            return resp.choices[0].message.content.strip()

        else:
            raise ValueError(f"Noma'lum provider: {provider}")

    except Exception as e:
        logger.exception("LLM chaqiruvida xatolik (provider=%s, model=%s): %s",
                          provider, model, e)
        return (
            "⚠️ Javob generatsiya qilishda xatolik yuz berdi. "
            "API kalitni yoki limitni tekshiring."
        )


def transcribe_voice(file_bytes: bytes) -> str:
    """Ovozli xabar baytlarini (.ogg) matnga o'giradi. Xato bo'lsa bo'sh qaytaradi."""
    try:
        client = _get_openai()
        audio_file = io.BytesIO(file_bytes)
        audio_file.name = "voice.ogg"  # OpenAI SDK format aniqlash uchun nomga muhtoj
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return (resp.text or "").strip()
    except Exception as e:
        logger.exception("Ovozni matnga o'girishda xatolik: %s", e)
        return ""


def analyze_image(provider: str, model: str, image_bytes: bytes, prompt: str) -> str:
    """
    Rasm (yoki video kadri) baytlarini AI orqali tahlil qilib, matnli
    tavsif qaytaradi. Claude va GPT-4o ikkalasi ham vision (ko'rish)
    imkoniyatiga ega - agentning o'z provideri ishlatiladi.
    """
    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        if provider == "claude":
            client = _get_anthropic()
            resp = client.messages.create(
                model=model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": "image/jpeg", "data": b64,
                        }},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return "".join(
                block.text for block in resp.content if block.type == "text"
            ).strip()

        else:  # gpt4o
            client = _get_openai()
            resp = client.chat.completions.create(
                model=model,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                        }},
                    ],
                }],
            )
            return resp.choices[0].message.content.strip()

    except Exception as e:
        logger.exception("Rasmni tahlil qilishda xatolik: %s", e)
        return ""


def generate_image(prompt: str) -> bytes:
    """
    Berilgan tavsif (prompt) asosida DALL-E 3 orqali haqiqiy rasm
    generatsiya qiladi. Xato bo'lsa bo'sh bytes qaytaradi.
    """
    try:
        client = _get_openai()
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        data = resp.data[0]

        # OpenAI ba'zan b64_json, ba'zan faqat url qaytaradi - ikkalasini
        # ham qo'llab-quvvatlaymiz.
        if getattr(data, "b64_json", None):
            return base64.b64decode(data.b64_json)

        if getattr(data, "url", None):
            import httpx
            r = httpx.get(data.url, timeout=30)
            r.raise_for_status()
            return r.content

        return b""
    except Exception as e:
        logger.exception("Rasm generatsiya qilishda xatolik: %s", e)
        return b""
