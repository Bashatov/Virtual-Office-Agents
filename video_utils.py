# -*- coding: utf-8 -*-
"""
YouTube'dan video yuklash va undan 9:16 (Instagram Reels/Stories)
formatidagi qiziqarli-kadrlar videosini avtomatik yaratish.

MUHIM XAVFSIZLIK QARORI: bu modul AI'ga erkin terminal/shell buyruq
yozish huquqini BERMAYDI. Aksincha, faqat ikkita QATTIQ BELGILANGAN,
xavfsiz funksiya taqdim etadi (download_youtube, build_highlight_reel) -
AI faqat shu ikkita "tugma"ni bosishi mumkin, o'zi ixtiyoriy buyruq
yoza olmaydi. Bu production (ishlab chiqarish) tizimlar uchun xavfsiz
yondashuv.

Barcha og'ir (video yuklash/montaj) ishlar `run_in_executor` orqali
alohida thread'da bajariladi - shunda bitta video ustida ishlash
boshqa 6 ta botning ishlashiga xalaqit bermaydi (asyncio event loop
band bo'lib qolmaydi).
"""

import os
import re
import glob
import shutil
import logging
import asyncio
import tempfile
import subprocess

logger = logging.getLogger(__name__)

MEDIA_DIR = os.path.join(tempfile.gettempdir(), "ai_jamoa_media")
os.makedirs(MEDIA_DIR, exist_ok=True)

FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# Agar shu font topilmasa (masalan boshqa muhitda), fontconfig o'zi mos
# keladigan shriftni tanlab oladi (chunki ffmpeg libfontconfig bilan
# yig'ilgan bo'lsa).
if not os.path.exists(FONT_FILE):
    FONT_FILE = None


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


# ---------- 1) YouTube'dan video yuklash ----------

def _download_youtube_sync(url: str, dest_dir: str) -> dict:
    import yt_dlp

    ydl_opts = {
        "outtmpl": os.path.join(dest_dir, "source.%(ext)s"),
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        # merge_output_format ba'zan kengaytmani o'zgartiradi
        if not os.path.exists(filepath):
            candidates = glob.glob(os.path.join(dest_dir, "source.*"))
            if candidates:
                filepath = candidates[0]
        return {
            "path": filepath,
            "title": info.get("title", "Video"),
            "duration": info.get("duration", 0),
        }


async def download_youtube(url: str, chat_key: str) -> dict:
    """
    chat_key - shu chat/agent uchun noyob papka nomi (masalan
    'direktor_123456'). Qaytaradi: {"path", "title", "duration"} yoki
    xato bo'lsa {"error": "..."}
    """
    dest_dir = os.path.join(MEDIA_DIR, chat_key)
    shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _download_youtube_sync, url, dest_dir)
        return result
    except Exception as e:
        logger.exception("YouTube yuklashda xatolik: %s", e)
        return {"error": str(e)}


# ---------- 2) Video haqida ma'lumot (ffprobe) ----------

def get_video_info(path: str) -> dict:
    try:
        result = _run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ])
        import json
        data = json.loads(result.stdout)
        duration = float(data["format"].get("duration", 0))
        size_mb = int(data["format"].get("size", 0)) / (1024 * 1024)
        v_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
        return {
            "duration": duration,
            "size_mb": round(size_mb, 1),
            "width": v_stream.get("width"),
            "height": v_stream.get("height"),
            "fps": eval(v_stream.get("r_frame_rate", "0/1")) if v_stream.get("r_frame_rate") else 0,
        }
    except Exception as e:
        logger.exception("Video ma'lumotini olishda xatolik: %s", e)
        return {}


# ---------- 3) Nomzod kadrlarni chiqarish (vision uchun) ----------

def _extract_candidate_frames_sync(path: str, dest_dir: str, count: int = 8) -> list:
    info = get_video_info(path)
    duration = info.get("duration", 0) or 1
    timestamps = [duration * (i + 1) / (count + 1) for i in range(count)]
    frames = []
    for i, ts in enumerate(timestamps):
        out_path = os.path.join(dest_dir, f"cand_{i:02d}.jpg")
        _run([
            "ffmpeg", "-ss", str(ts), "-i", path, "-vframes", "1",
            "-q:v", "3", out_path, "-y", "-loglevel", "error",
        ])
        if os.path.exists(out_path):
            with open(out_path, "rb") as f:
                frames.append({"timestamp": ts, "path": out_path, "bytes": f.read()})
    return frames


async def extract_candidate_frames(path: str, dest_dir: str, count: int = 8) -> list:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _extract_candidate_frames_sync, path, dest_dir, count
    )


def build_contact_sheet(frames: list) -> bytes:
    """Barcha nomzod kadrlarni bitta katta rasmga (grid) birlashtiradi."""
    from PIL import Image
    import io as _io

    thumbs = [Image.open(_io.BytesIO(f["bytes"])) for f in frames]
    if not thumbs:
        return b""
    tw, th = 320, 180
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), "black")
    for idx, im in enumerate(thumbs):
        im = im.resize((tw, th))
        x = (idx % cols) * tw
        y = (idx // cols) * th
        sheet.paste(im, (x, y))
    buf = _io.BytesIO()
    sheet.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------- 4) Yakuniy 9:16 "reel" videoni yig'ish ----------

def _make_segment(src: str, start: float, panel_no: str, badge_text: str,
                   title_text: str, out_path: str, seg_len: float = 5.0):
    def esc(t: str) -> str:
        return t.replace("'", "\u2019").replace(":", "\\:")

    filters = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"drawbox=x=0:y=0:w=1080:h=220:color=black@0.72:t=fill,"
        f"drawtext=text='{esc(title_text)}':fontcolor=white:fontsize=54:"
        f"x=(w-text_w)/2:y=60:borderw=2:bordercolor=black"
    )
    if FONT_FILE:
        filters += f":fontfile='{FONT_FILE}'"
    filters += (
        f",drawbox=x=50:y=250:w=110:h=80:color=yellow@0.95:t=fill,"
        f"drawtext=text='{esc(panel_no)}':fontcolor=black:fontsize=46:"
        f"x=85:y=270"
    )
    if FONT_FILE:
        filters += f":fontfile='{FONT_FILE}'"
    filters += (
        f",drawtext=text='{esc(badge_text)}':fontcolor=white:fontsize=48:"
        f"x=185:y=278"
    )
    if FONT_FILE:
        filters += f":fontfile='{FONT_FILE}'"

    _run([
        "ffmpeg", "-ss", str(max(0, start)), "-t", str(seg_len), "-i", src,
        "-vf", filters,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-r", "30", out_path, "-y", "-loglevel", "error",
    ])


def _build_reel_sync(src: str, highlights: list, overall_title: str,
                      dest_dir: str) -> str:
    segment_paths = []
    for i, h in enumerate(highlights, start=1):
        seg_path = os.path.join(dest_dir, f"seg_{i:02d}.mp4")
        _make_segment(
            src, h["timestamp"], f"{i:02d}", h["caption"], overall_title, seg_path,
        )
        if os.path.exists(seg_path):
            segment_paths.append(seg_path)

    if not segment_paths:
        raise RuntimeError("Hech qanday segment yaratilmadi")

    concat_list = os.path.join(dest_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")

    output_path = os.path.join(dest_dir, "reel_final.mp4")
    _run([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", output_path, "-y", "-loglevel", "error",
    ])
    return output_path


async def build_highlight_reel(src: str, highlights: list, overall_title: str,
                                dest_dir: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _build_reel_sync, src, highlights, overall_title, dest_dir
    )


def parse_highlights_response(text: str, video_duration: float) -> list:
    """
    Vision modelning javobidan "MM:SS | Sarlavha" formatidagi qatorlarni
    ajratib oladi. Hech narsa topilmasa, videoni 3 ga bo'lib standart
    nuqtalarni qaytaradi (zaxira/fallback).
    """
    pattern = re.compile(r"(\d{1,2}):(\d{2})\s*[\|\-–—:]\s*(.+)")
    results = []
    for line in text.splitlines():
        m = pattern.search(line.strip())
        if m:
            minutes, seconds, caption = m.groups()
            ts = int(minutes) * 60 + int(seconds)
            caption = caption.strip().strip("*").strip()[:30]
            if caption:
                results.append({"timestamp": float(ts), "caption": caption})
        if len(results) >= 3:
            break

    if len(results) < 3:
        # Zaxira: videoni tengga bo'lib, umumiy nomlar bilan
        fallback_names = ["Boshlanishi", "O'rta qismi", "Yakuni"]
        results = [
            {"timestamp": video_duration * f, "caption": name}
            for f, name in zip((0.2, 0.5, 0.8), fallback_names)
        ]
    return results[:3]


def cleanup(chat_key: str):
    dest_dir = os.path.join(MEDIA_DIR, chat_key)
    shutil.rmtree(dest_dir, ignore_errors=True)
