import json
from datetime import datetime, timedelta, timezone

from config import PORTRAIT_COOLDOWN_DAYS
from db import get_db


def save_daily_cipa_visuals(chat_id, visual_prompt, elements):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO daily_cipa_visuals (
                chat_id,
                generated_at,
                visual_prompt,
                elements_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                chat_id,
                datetime.now(timezone.utc).isoformat(),
                visual_prompt,
                json.dumps(elements, ensure_ascii=False),
            ),
        )


def get_latest_daily_cipa_visuals(chat_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT generated_at, visual_prompt, elements_json
            FROM daily_cipa_visuals
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    try:
        elements = json.loads(row["elements_json"])
    except Exception:
        elements = []
    return {
        "generated_at": row["generated_at"],
        "visual_prompt": row["visual_prompt"],
        "elements": elements,
    }


def save_cipa_portrait_visuals(chat_id, username, visual_prompt, elements):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO cipa_portrait_visuals (
                chat_id,
                username,
                generated_at,
                visual_prompt,
                elements_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                username,
                datetime.now(timezone.utc).isoformat(),
                visual_prompt,
                json.dumps(elements, ensure_ascii=False),
            ),
        )


def get_latest_cipa_portrait_visuals(chat_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT username, generated_at, visual_prompt, elements_json
            FROM cipa_portrait_visuals
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    try:
        elements = json.loads(row["elements_json"])
    except Exception:
        elements = []
    return {
        "username": row["username"],
        "generated_at": row["generated_at"],
        "visual_prompt": row["visual_prompt"],
        "elements": elements,
    }


def get_recent_cipa_portrait_cooldown(chat_id, username):
    normalized_username = username.strip().lower()
    cutoff = datetime.now(timezone.utc) - timedelta(days=PORTRAIT_COOLDOWN_DAYS)
    with get_db() as db:
        row = db.execute(
            """
            SELECT generated_at
            FROM cipa_portrait_visuals
            WHERE chat_id = ?
              AND LOWER(username) = ?
              AND generated_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id, normalized_username, cutoff.isoformat()),
        ).fetchone()
    return row["generated_at"] if row else None
