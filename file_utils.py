# -*- coding: utf-8 -*-
"""
1) Yuborilgan fayllardan (.txt, .docx, .pdf) matn ajratib olish -
   shunday qilib agent fayl "ichini" tushunib, unga javob beradi.
2) Agentning javobi asosida yangi fayl (PDF yoki Word) YARATISH -
   shunday qilib agent tayyorlagan matnni haqiqiy fayl qilib yuborish
   mumkin.
"""

import io
import html
import logging
from docx import Document as DocxDocument
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

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


# ---------- Fayl YARATISH (PDF / Word) ----------

def _sanitize_for_pdf(text: str) -> str:
    """
    Reportlab'ning standart shriftlari (Helvetica) faqat Latin-1
    belgilarni qo'llab-quvvatlaydi. LLM ba'zan 'aqlli tirnoq'
    (\u2019, \u201c va h.k.) ishlatishi mumkin - shularni oddiy
    belgilarga almashtiramiz. Shuningdek Paragraph mini-XML formatidagi
    maxsus belgilarni (&, <, >) xavfsiz qilib escape qilamiz.
    """
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return html.escape(text)


def create_pdf(title: str, content: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleUZ", parent=styles["Title"], fontSize=16)
    body_style = ParagraphStyle("BodyUZ", parent=styles["Normal"], fontSize=11, leading=16)

    story = [Paragraph(_sanitize_for_pdf(title), title_style), Spacer(1, 14)]
    for para in content.split("\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(_sanitize_for_pdf(para), body_style))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buf.getvalue()


def create_docx(title: str, content: str) -> bytes:
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    for para in content.split("\n"):
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

