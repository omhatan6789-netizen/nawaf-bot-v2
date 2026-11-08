"""Download publicly accessible social-media media and credit its source in the Telegram caption."""
import asyncio
import logging
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("nawaf-social-downloader")

SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be", "tiktok.com", "x.com", "twitter.com",
    "instagram.com", "facebook.com", "fb.watch", "reddit.com", "redd.it",
    "vimeo.com", "dailymotion.com", "streamable.com", "snapchat.com",
    "pinterest.com", "threads.net", "likee.video", "bilibili.com",
    "twitch.tv",
)
MAX_UPLOAD_BYTES = 49 * 1024 * 1024
URL_RE = re.compile(r"https?://[^\s<>()]+")


def _clean_url(value: str) -> str:
    return value.rstrip(".,!?;:،。")


def _supported_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme in ("http", "https")
            and not parsed.username
            and not parsed.password
            and any(host == domain or host.endswith("." + domain) for domain in SUPPORTED_DOMAINS)
        )
    except Exception:
        return False


def _download(url: str, directory: str):
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("مكتبة استخراج الفيديو غير مثبتة.") from exc

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(Path(directory) / "media.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 20,
        "max_filesize": MAX_UPLOAD_BYTES,
        "cachedir": False,
        "overwrites": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        files = [
            path for path in Path(directory).iterdir()
            if path.is_file() and not path.name.endswith((".part", ".ytdl"))
        ]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        if not files:
            raise RuntimeError("لم أجد ملف فيديو أو صورة قابلًا للإرسال.")
        media_path = files[0]
        return media_path, info or {}


def _caption(info: dict, original_url: str) -> str:
    author = (
        info.get("uploader")
        or info.get("creator")
        or info.get("channel")
        or info.get("artist")
        or ""
    )
    handle = info.get("uploader_id") or info.get("channel_id") or ""
    if not author and isinstance(handle, str) and re.fullmatch(r"[A-Za-z0-9_]{1,30}", handle):
        author = "@" + handle
    author = re.sub(r"[\r\n]+", " ", str(author)).strip()
    source = str(info.get("webpage_url") or info.get("original_url") or original_url).strip()
    if len(source) > 700:
        source = original_url[:700]
    credit = author or "صاحب المحتوى الأصلي"
    return f"حقوق صاحب المحتوى: {credit}\nالمصدر: {source}"[:1024]


async def handle_social_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    match = URL_RE.search(message.text)
    if not match:
        return
    url = _clean_url(match.group(0))
    if not _supported_url(url):
        return

    status = await message.reply_text("⏳ جاري استخراج المقطع وإعداد حقوق صاحبه في الكابشن...")
    try:
        with tempfile.TemporaryDirectory(prefix="nawaf-media-") as temp_dir:
            media_path, info = await asyncio.to_thread(_download, url, temp_dir)
            size = media_path.stat().st_size
            if size <= 0:
                raise RuntimeError("الملف المستخرج فارغ.")
            if size > MAX_UPLOAD_BYTES:
                await status.edit_text("حجم الملف أكبر من حد الإرسال في تيليجرام (حوالي 49MB). جرّب رابطًا بجودة أو مدة أقل.")
                return

            caption = _caption(info, url)
            suffix = media_path.suffix.lower()
            with media_path.open("rb") as media:
                if suffix in (".mp4", ".m4v", ".mov", ".webm", ".mkv"):
                    await message.reply_video(
                        video=media,
                        caption=caption,
                        supports_streaming=True,
                        read_timeout=60,
                        write_timeout=120,
                        connect_timeout=20,
                        pool_timeout=10,
                    )
                elif suffix in (".jpg", ".jpeg", ".png", ".webp") and size <= 10 * 1024 * 1024:
                    await message.reply_photo(
                        photo=media,
                        caption=caption,
                        read_timeout=60,
                        write_timeout=120,
                        connect_timeout=20,
                        pool_timeout=10,
                    )
                else:
                    await message.reply_document(
                        document=media,
                        caption=caption,
                        read_timeout=60,
                        write_timeout=120,
                        connect_timeout=20,
                        pool_timeout=10,
                    )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as exc:
        logger.info("Social media extraction failed for %s: %s", url, exc)
        try:
            await status.edit_text(
                "تعذر استخراج المقطع من هذا الرابط. تأكد أن المنشور عام وأن الموقع مدعوم، "
                "وأن الرابط لا يتطلب تسجيل دخول أو يتجاوز قيود الموقع."
            )
        except Exception:
            pass
