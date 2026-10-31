from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_MESSAGES, MAX_HOURS
from db import get_db


def save_message_to_db(
    chat_id,
    message_id,
    user_id,
    username,
    display_name,
    text,
    timestamp,
    reply_to_message_id=None,
):
    with get_db() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO messages (
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id,
            ),
        )


async def save_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    if not message:
        return
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption
    if not text or text.startswith("/"):
        return

    user = message.from_user
    reply_to_message_id = (
        message.reply_to_message.message_id
        if message.reply_to_message
        else None
    )

    save_message_to_db(
        chat_id=message.chat_id,
        message_id=message.message_id,
        user_id=user.id if user else None,
        username=user.username if user else None,
        display_name=user.full_name if user else None,
        text=text,
        timestamp=message.date.astimezone(timezone.utc).isoformat(),
        reply_to_message_id=reply_to_message_id,
    )


def get_messages_for_period(chat_id, hours=24, message_limit=None):
    hours = min(hours, MAX_HOURS)
    message_limit = (
        MAX_MESSAGES
        if message_limit is None
        else min(max(message_limit, 1), MAX_MESSAGES)
    )
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id
            FROM messages
            WHERE chat_id = ?
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (chat_id, since.isoformat(), message_limit),
        ).fetchall()

    return list(reversed(rows))


def get_messages_by_username(chat_id, username, hours=24):
    username = username.lstrip("@").strip()
    if not username:
        return []

    hours = min(hours, MAX_HOURS)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id
            FROM messages
            WHERE chat_id = ?
              AND timestamp >= ?
              AND LOWER(username) = LOWER(?)
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (chat_id, since.isoformat(), username, MAX_MESSAGES),
        ).fetchall()

    return list(rows)


def get_top_chickens(chat_id, limit=3):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                user_id,
                username,
                display_name,
                COUNT(*) AS message_count
            FROM messages
            WHERE chat_id = ?
              AND timestamp >= ?
              AND user_id IS NOT NULL
            GROUP BY user_id, username, display_name
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (chat_id, since.isoformat(), limit),
        ).fetchall()
    return list(rows)


def get_active_chat_ids():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT chat_id
            FROM messages
            WHERE timestamp >= ?
            """,
            (since.isoformat(),),
        ).fetchall()
    return [row["chat_id"] for row in rows]
