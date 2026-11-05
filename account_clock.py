
import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram.errors import FloodWait

from music_call import get_music_client


ACCOUNT_ID = 6496915877
TIMEZONE = ZoneInfo("Asia/Riyadh")

_clock_task = None

CLOCK_PATTERN = re.compile(
    r"\s+⌁\s+\d{1,2}:\d{2}\s+(?:AM|PM)$"
)


async def _clock_loop():
    client = get_music_client()

    if client is None:
        print("[CLOCK] Music account is not connected.")
        return

    me = await client.get_me()

    if me.id != ACCOUNT_ID:
        print("[CLOCK] Account ID mismatch. Clock disabled.")
        return

    print("[CLOCK] Account verified. Clock started.")

    while True:
        try:
            # قراءة الاسم الحالي من تيليجرام
            me = await client.get_me()

            # إزالة الساعة القديمة إن وجدت
            base_name = CLOCK_PATTERN.sub("", me.first_name).strip()

            now = datetime.now(TIMEZONE)
            clock = now.strftime("%I:%M %p")

            new_name = f"{base_name} ⌁ {clock}"

            if me.first_name != new_name:
                await client.update_profile(
                    first_name=new_name
                )
                print(f"[CLOCK] Name updated: {new_name}")

            now = datetime.now(TIMEZONE)
            seconds = 60 - now.second - now.microsecond / 1_000_000

            await asyncio.sleep(max(1, seconds))

        except FloodWait as exc:
            print(f"[CLOCK] FloodWait: {exc.value}s")
            await asyncio.sleep(exc.value)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(f"[CLOCK] Error: {exc}")
            await asyncio.sleep(60)


async def start_account_clock():
    global _clock_task

    if _clock_task and not _clock_task.done():
        return

    _clock_task = asyncio.create_task(_clock_loop())


async def shutdown_account_clock():
    global _clock_task

    if _clock_task:
        _clock_task.cancel()

        try:
            await _clock_task
        except asyncio.CancelledError:
            pass

        _clock_task = None

    print("[CLOCK] Account clock stopped.")
