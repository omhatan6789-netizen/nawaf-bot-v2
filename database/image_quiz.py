"""Async repository for manually added image-quiz pictures."""
from __future__ import annotations

import json
from database.pool import get_pool


async def load_manual_images() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, file_id, answer, alternative_answers
           FROM image_quiz_images ORDER BY id ASC"""
    )
    images = []
    for row in rows:
        file_id = row["file_id"]
        answer = row["answer"]
        if not file_id or not isinstance(answer, str):
            continue
        raw = row["alternative_answers"]
        alternatives = []
        if isinstance(raw, list):
            alternatives = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, list):
                    alternatives = decoded
                elif isinstance(decoded, str):
                    alternatives = [decoded]
            except (TypeError, ValueError):
                alternatives = [line.strip() for line in raw.splitlines() if line.strip()]
        images.append({
            "id": f"manual_{row['id']}",
            "file_id": file_id,
            "answer": answer,
            "alternative_answers": alternatives,
        })
    return images


async def add_manual_image(file_id: str, answer: str) -> bool:
    file_id = str(file_id or "").strip()
    answer = str(answer or "").strip()
    if not file_id or not answer:
        return False
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO image_quiz_images(file_id, answer, alternative_answers)
           VALUES($1, $2, $3)
           ON CONFLICT(file_id) DO NOTHING
           RETURNING id""",
        file_id, answer, "[]",
    )
    return row is not None


async def delete_manual_image(file_id: str) -> bool:
    if not file_id:
        return False
    pool = get_pool()
    row = await pool.fetchrow(
        "DELETE FROM image_quiz_images WHERE file_id=$1 RETURNING id",
        str(file_id),
    )
    return row is not None


async def get_manual_images_count() -> int:
    pool = get_pool()
    value = await pool.fetchval("SELECT COUNT(*) FROM image_quiz_images")
    return int(value or 0)
