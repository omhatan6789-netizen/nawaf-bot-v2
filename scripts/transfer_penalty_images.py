#!/usr/bin/env python3
"""
Move Telegram photo file_ids from the old bot to the new bot.

Run from the repository root:
  OLD_BOT_TOKEN='...' NEW_BOT_TOKEN='...' python scripts/transfer_penalty_images.py

The new bot must already have been started by the owner (OWNER_ID below).
The script downloads each unique photo using the old bot, uploads it using
the new bot, and replaces the IDs in games/penalties.py.
"""
import os
import re
import sys
import time
from pathlib import Path

import requests

OWNER_ID = 8453977662
FILE = Path("games/penalties.py")
API = "https://api.telegram.org/bot{}/{}"


def call(token, method, data=None, files=None):
    response = requests.post(
        API.format(token, method),
        data=data,
        files=files,
        timeout=90,
    )
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def main():
    old_token = os.environ.get("OLD_BOT_TOKEN")
    new_token = os.environ.get("NEW_BOT_TOKEN")
    if not old_token or not new_token:
        sys.exit("Set OLD_BOT_TOKEN and NEW_BOT_TOKEN as environment variables.")
    if not FILE.exists():
        sys.exit(f"Run this script from the project root; missing {FILE}")

    source = FILE.read_text(encoding="utf-8")
    ids = list(dict.fromkeys(re.findall(r'"(Ag[A-Za-z0-9_-]{20,})"', source)))
    if not ids:
        sys.exit("No Telegram photo file_ids found.")

    replacements = {}
    print(f"Found {len(ids)} unique photo IDs. Starting transfer...")

    for index, old_id in enumerate(ids, 1):
        try:
            file_info = call(old_token, "getFile", {"file_id": old_id})
            file_path = file_info["file_path"]
            download_url = f"https://api.telegram.org/file/bot{old_token}/{file_path}"
            download = requests.get(download_url, timeout=90)
            download.raise_for_status()

            uploaded = call(
                new_token,
                "sendPhoto",
                data={"chat_id": OWNER_ID},
                files={"photo": ("penalty_image.jpg", download.content)},
            )
            photos = uploaded.get("photo") or []
            if not photos:
                raise RuntimeError("Telegram returned no photo sizes")
            replacements[old_id] = photos[-1]["file_id"]
            print(f"[{index}/{len(ids)}] transferred")
            time.sleep(0.4)
        except Exception as exc:
            print(f"[{index}/{len(ids)}] FAILED: {exc}")
            print("Stopped without modifying games/penalties.py.")
            sys.exit(1)

    updated = source
    for old_id, new_id in replacements.items():
        updated = updated.replace(old_id, new_id)

    backup = FILE.with_suffix(".py.before_file_id_transfer")
    backup.write_text(source, encoding="utf-8")
    FILE.write_text(updated, encoding="utf-8")

    print(f"\nDone. Replaced {len(replacements)} IDs in {FILE}.")
    print(f"Backup saved to {backup}.")
    print("Review the diff, then commit and push the updated file.")
    print("The new bot will now use its own photo file_ids.")


if __name__ == "__main__":
    main()
