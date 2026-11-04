"""Async-backed inline keyboard color customization."""
from __future__ import annotations

import unicodedata
from telegram import InlineKeyboardButton
from database.pool import get_pool

COLOR_STYLES = {"احمر": "danger", "ازرق": "primary", "اخضر": "success", "شفاف": None}
_known_buttons: set[str] = set()
_color_cache: dict[str, str] = {}
_cache_loaded = False
_patch_done = False


def normalize_button_name(text):
    if not text:
        return ""
    value = unicodedata.normalize("NFC", str(text))
    value = value.replace("\ufe0e", "").replace("\ufe0f", "")
    return " ".join(value.strip().split())


async def load_button_color_cache():
    global _cache_loaded
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT button_text,color FROM button_colors WHERE button_text IS NOT NULL"
    )
    _known_buttons.clear()
    _color_cache.clear()
    for row in rows:
        name = normalize_button_name(row["button_text"])
        if not name:
            continue
        color = row["color"]
        _known_buttons.add(name)
        _color_cache[name] = color if color in COLOR_STYLES else "شفاف"
    _cache_loaded = True


def register_button_memory(button_text):
    name = normalize_button_name(button_text)
    if not name:
        return
    _known_buttons.add(name)
    _color_cache.setdefault(name, "شفاف")


async def register_button(button_text):
    name = normalize_button_name(button_text)
    if not name:
        return
    pool = get_pool()
    await pool.execute(
        """INSERT INTO button_colors(button_text,color) VALUES($1,'شفاف')
           ON CONFLICT(button_text) DO NOTHING""",
        name,
    )
    register_button_memory(name)


def get_button_color(button_text):
    return _color_cache.get(normalize_button_name(button_text), "شفاف")


def button_exists(button_text):
    return bool(normalize_button_name(button_text))


async def set_button_color(button_text, color):
    name = normalize_button_name(button_text)
    if not name or color not in COLOR_STYLES:
        return False
    try:
        pool = get_pool()
        await pool.execute(
            """INSERT INTO button_colors(button_text,color) VALUES($1,$2)
               ON CONFLICT(button_text) DO UPDATE SET color=EXCLUDED.color""",
            name, color,
        )
    except Exception:
        return False
    _known_buttons.add(name)
    _color_cache[name] = color
    return True


async def register_existing_panel_buttons():
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT button_text FROM panel_buttons WHERE button_text IS NOT NULL"
    )
    for row in rows:
        register_button_memory(row["button_text"])


def patch_inline_keyboard_buttons():
    global _patch_done
    if _patch_done:
        return
    _patch_done = True
    original_init = InlineKeyboardButton.__init__

    def new_init(self, *args, **kwargs):
        text = kwargs.get("text")
        if text is None and args:
            text = args[0]
        if text:
            name = normalize_button_name(text)
            register_button_memory(name)
            style = COLOR_STYLES.get(_color_cache.get(name, "شفاف"))
            if style is not None:
                kwargs["style"] = style
            else:
                kwargs.pop("style", None)
        original_init(self, *args, **kwargs)

    InlineKeyboardButton.__init__ = new_init
