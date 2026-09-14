# -*- coding: utf-8 -*-
"""
Claude va GPT-4o uchun yagona chaqiruv interfeysi.
Agent qaysi 'provider' ga ega bo'lsa, shu orqali javob generatsiya qilinadi.
"""

import os
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
        logger.exception("LLM chaqiruvida xatolik: %s", e)
        return (
            "⚠️ Javob generatsiya qilishda xatolik yuz berdi. "
            "API kalitni yoki limitni tekshiring."
        )
