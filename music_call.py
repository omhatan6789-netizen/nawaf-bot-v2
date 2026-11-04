import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from pyrogram.errors import UserNotParticipant, UserAlreadyParticipant
from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls import filters as call_filters


_client = None
_calls = None
_started = False

_tracks = {}
_chat_locks = {}


def _get_lock(chat_id):
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


def _remove_track_file(track):
    if not track:
        return

    path = track.get("path")
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[MUSIC] Could not remove track file: {exc}")


async def _stream_ended_handler(_, update):
    chat_id = int(update.chat_id)
    track = _tracks.pop(chat_id, None)
    _remove_track_file(track)

    if _calls is not None:
        try:
            await _calls.leave_call(chat_id)
        except Exception:
            pass


async def start_music_call():
    """تشغيل حساب تيليجرام الثاني وربطه بـ PyTgCalls."""
    global _client, _calls, _started

    if _started:
        return True

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    session_string = os.getenv("SESSION_STRING")

    if not api_id or not api_hash or not session_string:
        print(
            "[MUSIC] Missing API_ID, API_HASH or SESSION_STRING. "
            "Voice music is disabled."
        )
        return False

    try:
        _client = Client(
            "nawaf_music_account",
            api_id=int(api_id),
            api_hash=api_hash,
            session_string=session_string,
        )

        _calls = PyTgCalls(_client)
        _calls.on_update(call_filters.stream_end())(
            _stream_ended_handler
        )

        await _calls.start()
        _started = True

        print("[MUSIC] Second Telegram account connected successfully.")
        return True

    except Exception:
        print("[MUSIC] Failed to start the second Telegram account.")
        import traceback
        traceback.print_exc()

        _client = None
        _calls = None
        _started = False
        return False


async def play_track(chat_id, source_path, title, duration, requester):
    """تشغيل ملف صوتي داخل مكالمة المجموعة."""
    if not _started or _calls is None:
        raise RuntimeError(
            "حساب تشغيل المكالمات غير متصل. راجع سجلات Render."
        )

    chat_id = int(chat_id)
    lock = _get_lock(chat_id)

    async with lock:
        directory = Path(tempfile.gettempdir()) / "nawaf_music_call"
        directory.mkdir(parents=True, exist_ok=True)

        destination = directory / f"{chat_id}_{uuid.uuid4().hex}.mp3"
        shutil.copy2(source_path, destination)

        old_track = _tracks.pop(chat_id, None)

        if old_track:
            try:
                await _calls.leave_call(chat_id)
            except Exception:
                pass
            _remove_track_file(old_track)

        try:
            await _calls.play(chat_id, str(destination))
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except Exception:
                pass
            raise

        _tracks[chat_id] = {
            "path": str(destination),
            "title": title,
            "duration": duration,
            "requester": requester,
        }

        return True


async def stop_track(chat_id):
    """إيقاف المقطع الحالي وإخراج الحساب الثاني من المكالمة."""
    if not _started or _calls is None:
        return False

    chat_id = int(chat_id)
    lock = _get_lock(chat_id)

    async with lock:
        track = _tracks.pop(chat_id, None)
        if not track:
            return False

        try:
            await _calls.leave_call(chat_id)
        finally:
            _remove_track_file(track)

        return True


def get_track(chat_id):
    return _tracks.get(int(chat_id))


async def shutdown_music_call():
    """إيقاف المكالمات وإغلاق جلسة الحساب الثاني عند إيقاف البوت."""
    global _client, _calls, _started

    if _calls is not None:
        for chat_id in list(_tracks):
            try:
                await _calls.leave_call(chat_id)
            except Exception:
                pass

    for track in list(_tracks.values()):
        _remove_track_file(track)

    _tracks.clear()

    if _client is not None:
        try:
            if _client.is_connected:
                await _client.stop()
        except Exception as exc:
            print(f"[MUSIC] Error while closing the music account: {exc}")

    _client = None
    _calls = None
    _started = False
    print("[MUSIC] Second Telegram account stopped.")


async def is_music_account_member(chat_id):
    if not _started or _client is None:
        raise RuntimeError("حساب الصوت مب متصل.")

    me = await _client.get_me()

    try:
        member = await _client.get_chat_member(
            int(chat_id),
            me.id,
        )
        return member.status not in ("left", "kicked")

    except UserNotParticipant:
        return False


async def ensure_music_account_in_group(
    chat_id,
    invite_link=None,
    public_username=None,
):
    if await is_music_account_member(chat_id):
        return True

    try:
        if public_username:
            await _client.join_chat(public_username)

        elif invite_link:
            await _client.join_chat(invite_link)

        else:
            raise RuntimeError("لا يوجد رابط أو اسم للمجموعة.")

    except UserAlreadyParticipant:
        pass

    return True


async def get_call_participants(chat_id):
    """إرجاع المشاركين الموجودين فعليًا في المكالمة."""
    if not _started or _calls is None:
        raise RuntimeError("حساب التشغيل غير متصل.")

    return await _calls.get_participants(int(chat_id))


async def get_music_account_id():
    """معرّف حساب الموسيقى لاستبعاده من قائمة الأعضاء."""
    if not _started or _client is None:
        return None

    me = await _client.get_me()
    return me.id


def get_music_client():
    """إرجاع اتصال حساب الموسيقى لاستخدامه في الميزات الأخرى."""
    if not _started or _client is None:
        return None

    return _client
