import asyncio
import hashlib
import logging

import httpx
from telegram import InlineQueryResultPhoto, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from ai_assistant import (
    _anime_image_url_candidates,
    _image_url_candidates_from_bing,
    _image_url_candidates_from_duckduckgo,
    _is_anime_image_query,
    _wikipedia_image_candidates,
)
from games.online_mode import _select_games

logger = logging.getLogger(__name__)

_MAX_INLINE_PHOTOS = 10
_IMAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LewadBotImageSearch/1.0)",
    "Accept": "image/jpeg,image/*;q=0.8,*/*;q=0.5",
}


async def _translate_image_query(query: str) -> str:
    # Translate Arabic searches to English so international image indexes
    # can return relevant results; retain the original query as a fallback.
    try:
        async with httpx.AsyncClient(timeout=1.0, follow_redirects=True) as client:
            response = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": query},
            )
            response.raise_for_status()
            data = response.json()
        translated = "".join(
            str(part[0]) for part in (data[0] or [])
            if isinstance(part, list) and part and part[0]
        ).strip()
        return translated if translated and translated.lower() != query.lower() else ""
    except Exception as exc:
        logger.debug("Inline image query translation failed: %s", exc)
        return ""


async def _source_candidates(query: str):
    translated = await _translate_image_query(query)
    queries = list(dict.fromkeys([query, translated] if translated else [query]))
    searchers = []
    for search_query in queries:
        searchers.extend([
            _image_url_candidates_from_duckduckgo(search_query),
            _image_url_candidates_from_bing(search_query),
        ])
        if search_query == query:
            searchers.append(_wikipedia_image_candidates(search_query))
    if _is_anime_image_query(query) or _is_anime_image_query(translated):
        anime_query = translated if translated and _is_anime_image_query(translated) else query
        searchers.insert(0, _anime_image_url_candidates(anime_query))

    batches = await asyncio.gather(
        *(asyncio.wait_for(task, timeout=2.5) for task in searchers),
        return_exceptions=True,
    )
    urls = []
    seen = set()
    for batch in batches:
        if isinstance(batch, Exception):
            logger.debug("Inline image source failed: %s", batch)
            continue
        for raw_url in batch or []:
            url = str(raw_url or "").strip()
            if url.startswith("https://") and url not in seen:
                seen.add(url)
                urls.append(url)
    # Prefer links explicitly ending in JPEG; Telegram rejects WebP/PNG for photo results.
    urls.sort(key=lambda url: 0 if url.split("?", 1)[0].lower().endswith((".jpg", ".jpeg")) else 1)
    return urls


async def _is_telegram_jpeg(client: httpx.AsyncClient, url: str) -> bool:
    try:
        async with client.stream(
            "GET",
            url,
            headers={"Range": "bytes=0-15"},
            timeout=1.8,
        ) as response:
            if response.status_code >= 400:
                return False
            content_type = response.headers.get("content-type", "").lower()
            iterator = response.aiter_bytes()
            first_chunk = await iterator.__anext__()
            return (
                first_chunk.startswith(b"\xff\xd8\xff")
                or "image/jpeg" in content_type
            )
    except (Exception, StopAsyncIteration):
        return False


async def _validated_photo_urls(urls):
    semaphore = asyncio.Semaphore(12)
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=_IMAGE_HEADERS,
        timeout=4,
    ) as client:
        async def check(url):
            async with semaphore:
                return url if await _is_telegram_jpeg(client, url) else None

        checked = await asyncio.gather(*(check(url) for url in urls[:16]))
    return [url for url in checked if url][:_MAX_INLINE_PHOTOS]


async def inline_image_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline = update.inline_query
    if not inline:
        return

    query = (inline.query or "").strip()
    if not query or query.startswith("دعوة كلمة "):
        return

    # Keep the existing game picker in charge of all recognized game queries.
    if _select_games(query):
        return

    try:
        candidates = await asyncio.wait_for(_source_candidates(query), timeout=3.2)
        photo_urls = await asyncio.wait_for(_validated_photo_urls(candidates), timeout=2.2)
        results = [
            InlineQueryResultPhoto(
                id=hashlib.sha1(url.encode("utf-8")).hexdigest()[:32],
                photo_url=url,
                thumbnail_url=url,
                title=query[:128],
                description=f"صورة من نتائج البحث عن {query}"[:255],
            )
            for url in photo_urls
        ]
        await inline.answer(
            results,
            cache_time=0,
            is_personal=True,
        )
    except Exception as exc:
        logger.warning("Inline image search failed for %r: %s", query, exc)
        try:
            await inline.answer([], cache_time=0, is_personal=True)
        except Exception:
            logger.debug("Could not send fallback inline answer for %r", query, exc_info=True)

    # Do not let the game inline handler answer the same query a second time.
    raise ApplicationHandlerStop()
