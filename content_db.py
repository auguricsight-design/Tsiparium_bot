from datetime import datetime, timezone

from db import get_db


def get_static_content(key):
    with get_db() as db:
        row = db.execute(
            "SELECT content FROM static_content WHERE key = ?",
            (key,),
        ).fetchone()

    if not row:
        return None

    return row["content"]


def append_static_content(key, new_text):
    new_text = (new_text or "").strip()
    if not new_text:
        raise ValueError("Cannot append empty static content")

    now = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        row = db.execute(
            """
            SELECT content
            FROM static_content
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        current = row["content"] if row else ""
        updated = (
            f"{current.rstrip()}\n\n{new_text}"
            if current.strip()
            else new_text
        )

        db.execute(
            """
            INSERT INTO static_content (
                key,
                content,
                updated_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (
                key,
                updated,
                now,
            ),
        )
        db.commit()

    return updated
