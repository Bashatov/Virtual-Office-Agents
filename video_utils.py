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
import json
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


# ---------- YouTube "cookies" fayli (login talab qiladigan videolar uchun) ----------

_cookies_path_cache = None


def _cookies_json_to_netscape(data) -> str:
    """
    Ba'zi brauzer kengaytmalari cookie'larni Netscape emas, JSON
    formatida eksport qiladi (masalan Cookie-Editor). Shu funksiya
    ikkala keng tarqalgan JSON ko'rinishini ({"cookies":[...]} yoki
    to'g'ridan-to'g'ri [...] ro'yxat) Netscape matn formatiga o'giradi,
    shunda yt-dlp uni to'g'ri o'qiy oladi.
    """
    if isinstance(data, dict) and "cookies" in data:
        cookies = data["cookies"]
    elif isinstance(data, list):
        cookies = data
    else:
        return ""

    lines = ["# Netscape HTTP Cookie File", "# Auto-converted from JSON", ""]
    for c in cookies:
        domain = c.get("domain", "")
        name = c.get("name", "")
        if not domain or not name:
            continue
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiration = int(c.get("expirationDate", 0) or 0)
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}")
    return "\n".join(lines)


def _get_cookies_file():
    """
    YOUTUBE_COOKIES muhit o'zgaruvchisi (Railway Variables) - agar
    berilgan bo'lsa, uni vaqtinchalik faylga yozib, shu faylning
    yo'lini qaytaradi. Bo'lmasa, None qaytaradi (cookiessiz urinadi).
    Ikkala formatni ham qo'llab-quvvatlaydi: Netscape (.txt) va JSON
    (avtomatik Netscape'ga o'giriladi).
    """
    global _cookies_path_cache
    if _cookies_path_cache and os.path.exists(_cookies_path_cache):
        return _cookies_path_cache

    content = os.getenv("YOUTUBE_COOKIES")
    if not content:
        return None

    content_stripped = content.strip()
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        try:
            data = json.loads(content_stripped)
            content = _cookies_json_to_netscape(data)
        except Exception as e:
            logger.exception("YOUTUBE_COOKIES JSON'ni o'girishda xatolik: %s", e)
            return None
        if not content:
            logger.error("YOUTUBE_COOKIES JSON'dan hech qanday cookie topilmadi")
            return None

    path = os.path.join(tempfile.gettempdir(), "youtube_cookies.txt")
    with open(path, "w") as f:
        f.write(content)
    _cookies_path_cache = path
    return path


# ---------- 1) YouTube'dan video yuklash ----------

def _download_youtube_sync(url: str, dest_dir: str) -> dict:
    import yt_dlp

    base_opts = {
        "outtmpl": os.path.join(dest_dir, "source.%(ext)s"),
        # MUHIM: hech qanday o'lcham/kengaytma cheklovi qo'ymaymiz -
        # mavjud bo'lgan ENG YAXSHISINI olamiz, keyin o'zimizning
        # ffmpeg bosqichimiz baribir kerakli formatga moslaydi.
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    cookies_file = _get_cookies_file()

    # YouTube tomonidan qo'yiladigan cheklovlar (bot-himoya, PoToken
    # talabi va h.k.) turli video/hisobda turlicha ishlaydi. Shuning
    # uchun BITTA qattiq usul o'rniga, bir nechta strategiyani ketma-ket
    # sinaymiz - birinchi ishlagani qabul qilinadi.
    strategies = []
    if cookies_file:
        strategies.append(("cookie+barcha-klientlar", {
            "cookiefile": cookies_file,
            "extractor_args": {"youtube": {"player_client": ["android", "ios", "web", "tv"]}},
        }))
        strategies.append(("cookie+faqat-web", {
            "cookiefile": cookies_file,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        }))
        strategies.append(("cookie+mobil-klientlar", {
            "cookiefile": cookies_file,
            "extractor_args": {"youtube": {"player_client": ["android", "ios", "tv"]}},
        }))
    strategies.append(("cookiesiz+mobil-klientlar", {
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "tv"]}},
    }))
    strategies.append(("cookiesiz+standart", {}))

    attempt_errors = []
    for name, extra_opts in strategies:
        opts = dict(base_opts)
        opts.update(extra_opts)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath):
                candidates = glob.glob(os.path.join(dest_dir, "source.*"))
                if candidates:
                    filepath = candidates[0]
            logger.info("YouTube yuklandi (%s strategiyasi orqali)", name)
            return {
                "path": filepath,
                "title": info.get("title", "Video"),
                "duration": info.get("duration", 0),
            }
        except Exception as e:
            short_err = str(e).splitlines()[0][:150]
            logger.warning("YouTube strategiyasi ishlamadi (%s): %s", name, short_err)
            attempt_errors.append(f"- {name}: {short_err}")
            continue

    # Barcha strategiyalar ishlamadi - QANDAY formatlar mavjudligini
    # (agar umuman bo'lsa) ko'rish uchun oxirgi bor "faqat ro'yxat"
    # so'raymiz, shuni xato xabariga qo'shamiz.
    formats_summary = ""
    try:
        probe_opts = dict(base_opts)
        probe_opts.pop("format", None)
        probe_opts["quiet"] = True
        with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
            probe_info = probe_ydl.extract_info(url, download=False)
        fmts = probe_info.get("formats", []) if probe_info else []
        if fmts:
            lines = [
                f"{f.get('format_id')}: {f.get('ext')} {f.get('height') or '-'}p "
                f"v={f.get('vcodec')} a={f.get('acodec')}"
                for f in fmts[:15]
            ]
            formats_summary = "\n".join(lines)
        else:
            formats_summary = "(YouTube hech qanday format qaytarmadi - bu odatda cookie eskirgani yoki hisob qo'shimcha tekshiruv talab qilayotganining belgisi)"
    except Exception as probe_err:
        formats_summary = f"(formatlar ro'yxatini ham olib bo'lmadi: {probe_err})"

    strategies_report = "\n".join(attempt_errors)
    logger.error(
        "Barcha YouTube strategiyalari ishlamadi:\n%s\n\nMavjud formatlar:\n%s",
        strategies_report, formats_summary,
    )
    raise RuntimeError(
        f"Barcha 5 usul sinaldi, hech biri ishlamadi:\n{strategies_report}"
        f"\n\nMavjud formatlar:\n{formats_summary}"
    )


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


# ---------- 4) Yakuniy "reel" videoni yig'ish (moslashuvchan format/uslub) ----------

# Har xil maqsad uchun tayyor o'lcham "pресет"lari - AI shulardan birini
# video mazmuniga qarab tanlaydi (universal, faqat 9:16 bilan cheklanmagan).
FORMAT_PRESETS = {
    "9:16": (1080, 1920),   # Reels / TikTok / Stories
    "1:1": (1080, 1080),    # kvadrat post
    "16:9": (1920, 1080),   # YouTube / landshaft
    "4:5": (1080, 1350),    # Instagram post
}
DEFAULT_FORMAT = "9:16"

# Har biri boshqacha "kayfiyat" beradigan, oldindan sinalgan uslublar -
# AI shulardan birini video mazmuniga (o'yin/tabiat/vlog va h.k.) qarab
# tanlaydi. Bularning ffmpeg filtri QATTIQ yozilgan - AI faqat NOMINI
# tanlaydi, filtr matnini o'zi yozmaydi.
VALID_STYLES = ("bold_badges", "minimal_caption", "cinematic_bar")

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _safe_color(color: str, default: str = "FFD700") -> str:
    if color and _HEX_RE.match(color.strip()):
        return color.strip().lstrip("#").upper()
    return default


def _esc(text: str) -> str:
    """ffmpeg drawtext ichida maxsus belgilarni xavfsiz escape qiladi."""
    return (
        text.replace("\\", "")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )


def _make_segment(src: str, start: float, duration: float, width: int,
                   height: int, style: str, panel_no: str, caption: str,
                   overall_title: str, accent_color: str, out_path: str):
    accent = _safe_color(accent_color)
    caption_safe = _esc(caption)[:40]
    title_safe = _esc(overall_title)[:40]
    scale_crop = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    font_part = f":fontfile='{FONT_FILE}'" if FONT_FILE else ""

    if style == "minimal_caption":
        # Toza/zamonaviy: faqat pastda kichik, shaffof yozuv paneli
        bar_h = int(height * 0.12)
        filters = (
            f"{scale_crop},"
            f"drawbox=x=0:y={height - bar_h}:w={width}:h={bar_h}:"
            f"color=black@0.55:t=fill,"
            f"drawtext=text='{caption_safe}':fontcolor=white:"
            f"fontsize={int(height * 0.032)}:x=(w-text_w)/2:"
            f"y={height - bar_h + int(bar_h * 0.32)}:borderw=1:"
            f"bordercolor=black{font_part}"
        )

    elif style == "cinematic_bar":
        # Hujjatli-film uslubi: yupqa letterbox chiziqlar + markaziy matn
        bar_h = int(height * 0.06)
        filters = (
            f"{scale_crop},"
            f"drawbox=x=0:y=0:w={width}:h={bar_h}:color=black@0.9:t=fill,"
            f"drawbox=x=0:y={height - bar_h}:w={width}:h={bar_h}:"
            f"color=black@0.9:t=fill,"
            f"drawtext=text='{caption_safe}':fontcolor=white:"
            f"fontsize={int(height * 0.026)}:x=(w-text_w)/2:"
            f"y={height - bar_h + int(bar_h * 0.25)}:borderw=1:"
            f"bordercolor=black{font_part}"
        )

    else:  # "bold_badges" - standart, energetik uslub (raqamli belgi)
        bar_h = int(height * 0.115)
        badge_w = int(width * 0.09)
        badge_h = int(height * 0.06)
        badge_x = int(width * 0.045)
        badge_y = bar_h + int(height * 0.01)
        filters = (
            f"{scale_crop},"
            f"drawbox=x=0:y=0:w={width}:h={bar_h}:color=black@0.72:t=fill,"
            f"drawtext=text='{title_safe}':fontcolor=white:"
            f"fontsize={int(height * 0.028)}:x=(w-text_w)/2:"
            f"y={int(bar_h * 0.28)}:borderw=2:bordercolor=black{font_part},"
            f"drawbox=x={badge_x}:y={badge_y}:w={badge_w}:h={badge_h}:"
            f"color=0x{accent}@0.95:t=fill,"
            f"drawtext=text='{panel_no}':fontcolor=black:"
            f"fontsize={int(height * 0.024)}:x={badge_x + 15}:"
            f"y={badge_y + int(badge_h * 0.15)}{font_part},"
            f"drawtext=text='{caption_safe}':fontcolor=white:"
            f"fontsize={int(height * 0.026)}:x={badge_x + badge_w + 20}:"
            f"y={badge_y + int(badge_h * 0.15)}{font_part}"
        )

    _run([
        "ffmpeg", "-ss", str(max(0, start)), "-t", str(duration), "-i", src,
        "-vf", filters,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-r", "30", out_path, "-y", "-loglevel", "error",
    ])


_SEGMENT_LINE_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*\|\s*(\d{1,2}(?:\.\d+)?)\s*\|\s*(#?[0-9A-Fa-f]{6})\s*\|\s*(.+)"
)


def parse_reel_plan(text: str, video_duration: float) -> dict:
    """
    Vision modelning STRUKTURALI javobini (format/style/title/segmentlar)
    ajratib oladi. Har bir qiymat XAVFSIZ chegaralarga qisqartiriladi
    (validatsiya) - noto'g'ri/kutilmagan qiymat kelsa, ishonchli
    standart qiymatga tushadi, hech qachon xato bilan yiqilmaydi.
    """
    plan = {"format": DEFAULT_FORMAT, "style": "bold_badges",
            "title": "HIGHLIGHTS", "segments": []}

    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("format:"):
            val = line.split(":", 1)[1].strip()
            if val in FORMAT_PRESETS:
                plan["format"] = val
        elif low.startswith("style:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in VALID_STYLES:
                plan["style"] = val
        elif low.startswith("title:"):
            plan["title"] = line.split(":", 1)[1].strip()[:40] or plan["title"]
        else:
            m = _SEGMENT_LINE_RE.search(line)
            if m:
                mm, ss, dur, color, caption = m.groups()
                ts = int(mm) * 60 + int(ss)
                ts = max(0.0, min(float(ts), max(video_duration - 3, 0)))
                dur = max(3.0, min(float(dur), 12.0))
                plan["segments"].append({
                    "timestamp": ts,
                    "duration": dur,
                    "accent_color": color,
                    "caption": caption.strip()[:40],
                })

    if len(plan["segments"]) < 2:
        fallback_names = ["Boshlanishi", "O'rta qismi", "Yakuni"]
        plan["segments"] = [
            {"timestamp": video_duration * f, "duration": 5.0,
             "accent_color": "FFD700", "caption": name}
            for f, name in zip((0.15, 0.5, 0.85), fallback_names)
        ]
    plan["segments"] = plan["segments"][:6]
    return plan


def _build_reel_sync(src: str, plan: dict, dest_dir: str) -> str:
    width, height = FORMAT_PRESETS.get(plan["format"], FORMAT_PRESETS[DEFAULT_FORMAT])
    segment_paths = []
    for i, seg in enumerate(plan["segments"], start=1):
        seg_path = os.path.join(dest_dir, f"seg_{i:02d}.mp4")
        _make_segment(
            src, seg["timestamp"], seg["duration"], width, height,
            plan["style"], f"{i:02d}", seg["caption"], plan["title"],
            seg["accent_color"], seg_path,
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


async def build_highlight_reel(src: str, plan: dict, dest_dir: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _build_reel_sync, src, plan, dest_dir)



def cleanup(chat_key: str):
    dest_dir = os.path.join(MEDIA_DIR, chat_key)
    shutil.rmtree(dest_dir, ignore_errors=True)
