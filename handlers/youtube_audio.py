"""Async YouTube search and audio delivery."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
SEARCH_RESULT_COUNT = 4
MAX_AUDIO_BYTES = 49 * 1024 * 1024
SAMPLECUT_API = "https://api.samplecut.app/v1/downloads"
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=20.0)


def _get_youtube_api_keys():
    keys = []
    primary = os.getenv("YOUTUBE_API_KEY")
    if primary:
        keys.append(primary)
    index = 2
    while True:
        key = os.getenv(f"YOUTUBE_API_KEY_{index}")
        if not key:
            break
        keys.append(key)
        index += 1
    return keys


def _parse_youtube_duration(value):
    """Convert YouTube ISO-8601 durations (for example PT4M13S) to seconds."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


async def _search_youtube(query):
    keys = _get_youtube_api_keys()
    logger.info("YouTube API keys configured: %s", len(keys))
    if not keys:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    last_error = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        for index, api_key in enumerate(keys, 1):
            params = {
                "part": "snippet", "q": query, "type": "video",
                "maxResults": SEARCH_RESULT_COUNT, "regionCode": "SA",
                "relevanceLanguage": "ar", "key": api_key,
            }
            try:
                response = await client.get(
                    "https://www.googleapis.com/youtube/v3/search", params=params
                )
                data = response.json()
                if response.is_error:
                    error = data.get("error", {})
                    reasons = {
                        item.get("reason") for item in error.get("errors", [])
                        if item.get("reason")
                    }
                    last_error = RuntimeError(
                        f"YouTube API HTTP {response.status_code}: "
                        f"{', '.join(sorted(reasons)) or error.get('message', response.text)}"
                    )
                    if reasons & {"quotaExceeded", "dailyLimitExceeded"}:
                        logger.warning("YouTube API key #%s quota exhausted", index)
                        continue
                    raise last_error
                results = []
                for item in data.get("items", []):
                    video_id = item.get("id", {}).get("videoId")
                    if not video_id:
                        continue
                    snippet = item.get("snippet", {})
                    results.append({
                        "id": video_id,
                        "title": snippet.get("title") or "مقطع بدون عنوان",
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "duration": None,
                    })
                # Fetch durations in one lightweight videos.list request.
                # Duration lookup is optional: search results should still work if it fails.
                if results:
                    try:
                        details_response = await client.get(
                            "https://www.googleapis.com/youtube/v3/videos",
                            params={
                                "part": "contentDetails",
                                "id": ",".join(item["id"] for item in results),
                                "key": api_key,
                            },
                        )
                        details_response.raise_for_status()
                        durations = {
                            item.get("id"): _parse_youtube_duration(
                                item.get("contentDetails", {}).get("duration")
                            )
                            for item in details_response.json().get("items", [])
                        }
                        for item in results:
                            item["duration"] = durations.get(item["id"])
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        logger.warning("YouTube duration lookup failed: %s", exc)
                return results
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("YouTube search key #%s request failed: %s", index, exc)
    raise RuntimeError("All YouTube API keys failed") from last_error


async def _download_audio(video_url, folder):
    """Download MP3 bytes directly from Samplecut in one API request."""
    started = time.perf_counter()
    payload = {"url": video_url, "format": "mp3", "response": "file"}
    file_path = Path(folder) / "audio.mp3"
    total = 0

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        async with client.stream(
            "POST",
            SAMPLECUT_API,
            json=payload,
            headers={
                "X-Client-Name": "NawafTelegramBot",
                "Accept": "audio/mpeg, application/json",
            },
        ) as response:
            if response.is_error:
                try:
                    error_data = await response.aread()
                    details = json.loads(error_data.decode("utf-8"))
                    api_error = details.get("error", {})
                    message = api_error.get("message") or api_error.get("code") or response.text
                except Exception:
                    message = f"HTTP {response.status_code}"
                raise RuntimeError(f"Samplecut {response.status_code}: {message}")

            content_type = response.headers.get("Content-Type", "").lower()
            if "audio/" not in content_type:
                preview = (await response.aread())[:300].decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Samplecut لم يُرجع ملفًا صوتيًا (Content-Type: {content_type}; {preview})"
                )

            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_AUDIO_BYTES:
                raise RuntimeError("حجم الصوت أكبر من الحد المسموح لإرساله.")

            with file_path.open("wb") as audio_file:
                async for chunk in response.aiter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > MAX_AUDIO_BYTES:
                        raise RuntimeError("حجم الصوت أكبر من الحد المسموح لإرساله.")
                    audio_file.write(chunk)

            encoded_title = response.headers.get("X-Samplecut-Title")
            title = unquote(encoded_title) if encoded_title else "صوت من يوتيوب"

    if not file_path.is_file() or file_path.stat().st_size == 0:
        raise RuntimeError("Samplecut أعاد ملفًا فارغًا أو لم يكتمل تحميله.")

    logger.info(
        "Samplecut direct audio ready in %.2fs (%s bytes)",
        time.perf_counter() - started,
        file_path.stat().st_size,
    )
    return str(file_path), {"title": title, "duration": None}


def _format_duration(seconds):
    if seconds is None:
        return ""
    seconds = int(float(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


async def _complete_youtube_search(message, context, search_text, status):
    try:
        started = time.perf_counter()
        results = await _search_youtube(search_text)
        logger.info("YouTube search completed in %.2fs", time.perf_counter() - started)
        if not results:
            await status.edit_text("❌ لم يتم العثور على نتائج.")
            return
        search_id = uuid.uuid4().hex[:10]
        searches = context.chat_data.setdefault("youtube_searches", {})
        searches[search_id] = results
        keyboard = []
        for index, result in enumerate(results):
            title = result["title"]
            if len(title) > 55:
                title = title[:52] + "..."
            duration = _format_duration(result.get("duration"))
            label = f"{index + 1}. {title}" + (f" [{duration}]" if duration else "")
            keyboard.append([InlineKeyboardButton(label, callback_data=f"ytpick:{search_id}:{index}")])
        await status.edit_text(
            f"🎵 نتائج البحث عن: {search_text}\n\nاختر المقطع:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception:
        logger.exception("فشل البحث في يوتيوب")
        try:
            await status.edit_text("❌ تعذّر البحث في يوتيوب.\nراجع سجلات Render لمعرفة السبب.")
        except Exception:
            logger.exception("تعذر تحديث رسالة حالة البحث")


async def youtube_audio_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return
    match = re.match(r"^(?:بحث|يوت)\s+(.+?)\s*$", message.text)
    if not match:
        return
    search_text = match.group(1).strip()
    if not search_text:
        await message.reply_text("❌ اكتب اسم المقطع بعد كلمة بحث.")
        return
    status = await message.reply_text("🔎 ثواني قاعد ابحث...")
    # Search runs outside the serial update processor so the group stays responsive.
    context.application.create_task(
        _complete_youtube_search(message, context, search_text, status),
        update=update,
    )


async def _download_and_send_youtube_audio(context, chat_id, video, status, search_id, searches):
    try:
        with tempfile.TemporaryDirectory(prefix="yt_audio_") as folder:
            file_path, info = await _download_audio(video["url"], folder)
            title = info.get("title") or video["title"]
            duration_value = info.get("duration") or video.get("duration") or 0
            caption = "• Nawaf"
            duration = _format_duration(duration_value)
            if duration:
                caption += f" . ↠ {duration}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🌷", url=f"https://t.me/{(await context.bot.get_me()).username}")
            ]])
            with open(file_path, "rb") as audio_file:
                await context.bot.send_audio(
                    chat_id=chat_id, audio=audio_file, title=title[:64],
                    performer="Nawaf", duration=int(float(duration_value or 0)),
                    caption=caption, reply_markup=keyboard,
                    read_timeout=120, write_timeout=120, connect_timeout=30, pool_timeout=30,
                )
        await status.delete()
    except Exception:
        logger.exception("فشل تحميل أو إرسال مقطع يوتيوب عبر Samplecut: %s", video.get("url"))
        try:
            await status.edit_text("❌ تعذّر تحميل هذا المقطع أو إرساله.\nجرّب اختيار نتيجة ثانية أو راجع سجلات Render.")
        except Exception:
            logger.exception("تعذر تحديث رسالة حالة التحميل")
    finally:
        searches.pop(search_id, None)


async def youtube_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    match = re.fullmatch(r"ytpick:([a-f0-9]+):(\d+)", query.data)
    if not match:
        await query.answer()
        return
    search_id, index = match.group(1), int(match.group(2))
    searches = context.chat_data.get("youtube_searches", {})
    results = searches.get(search_id, [])
    if index >= len(results):
        await query.answer("انتهت صلاحية النتائج، ابحث مرة ثانية.", show_alert=True)
        return
    await query.answer()
    video = results[index]
    chat_id = query.message.chat_id
    try:
        await query.message.delete()
    except Exception:
        pass
    status = await context.bot.send_message(chat_id=chat_id, text="⏳ قاعد ابحث، انتظر...")
    # Downloading and sending runs as a background task; it no longer blocks
    # other messages or callbacks in this group.
    context.application.create_task(
        _download_and_send_youtube_audio(context, chat_id, video, status, search_id, searches),
        update=update,
    )
