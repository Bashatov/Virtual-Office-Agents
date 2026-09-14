# -*- coding: utf-8 -*-
"""
Yuborilgan fayllardan (.txt, .docx, .pdf) matn ajratib olish.
Ajratilgan matn keyin agentga oddiy xabar sifatida beriladi -
shunday qilib agent fayl "ichini" tushunib, unga javob beradi.
"""

import io
import logging
from docx import Document as DocxDocument
from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_CHARS = 6000  # juda katta fayllarni qisqartiramiz


def extract_text(file_bytes: bytes, file_name: str) -> str:
    name = (file_name or "").lower()
    try:
        if name.endswith(".txt") or name.endswith(".rtf"):
            text = file_bytes.decode("utf-8", errors="ignore")

        elif name.endswith(".docx"):
            doc = DocxDocument(io.BytesIO(file_bytes))
            text = "\n".join(p.text for p in doc.paragraphs)

        elif name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)

        else:
            return (
                "(Bu fayl turini o'qib bo'lmadi — faqat .txt, .docx, .pdf "
                "fayllarni tushunaman.)"
            )
    except Exception as e:
        logger.exception("Faylni o'qishda xatolik: %s", e)
        return f"(Faylni o'qishda xatolik yuz berdi: {e})"

    text = text.strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...(fayl matni uzun bo'lgani uchun qisqartirildi)"
    return text or "(Fayl bo'sh yoki undan matn topilmadi.)"
