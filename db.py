import json
import sqlite3

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from telegram import Update
from telegram.ext import ContextTypes

from config import (
    DB_PATH,
    MAX_MESSAGES,
    MAX_HOURS,
    MESSAGE_RETENTION_DAYS,
    KYIV_TZ,
)
from commands import human_log_time


def get_db():
    connection = sqlite3.connect(
        DB_PATH
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reply_to_message_id INTEGER,
                UNIQUE(chat_id, message_id)
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_report_usage (
                chat_id INTEGER NOT NULL,
                report_date TEXT NOT NULL,
                report_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (
                    chat_id,
                    report_date
                )
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_cipa_visuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                visual_prompt TEXT NOT NULL,
                elements_json TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS cipa_portrait_visuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                visual_prompt TEXT NOT NULL,
                elements_json TEXT NOT NULL
            )
            """
        )


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


def cleanup_old_data():
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            days=MESSAGE_RETENTION_DAYS
        )
    )
    cutoff_iso = cutoff.isoformat()

    with get_db() as db:
        messages_cursor = db.execute(
            """
            DELETE FROM messages
            WHERE timestamp < ?
            """,
            (cutoff_iso,),
        )

        daily_visuals_cursor = db.execute(
            """
            DELETE FROM daily_cipa_visuals
            WHERE generated_at < ?
            """,
            (cutoff_iso,),
        )

        portrait_visuals_cursor = db.execute(
            """
            DELETE FROM cipa_portrait_visuals
            WHERE generated_at < ?
            """,
            (cutoff_iso,),
        )

    deleted_messages = (
        messages_cursor.rowcount
    )
    deleted_daily_visuals = (
        daily_visuals_cursor.rowcount
    )
    deleted_portrait_visuals = (
        portrait_visuals_cursor.rowcount
    )

    if (
        deleted_messages
        or deleted_daily_visuals
        or deleted_portrait_visuals
    ):
        print(
            f"[{human_log_time()}] "
            f"Cleanup older than "
            f"{MESSAGE_RETENTION_DAYS} days: "
            f"messages={deleted_messages}, "
            f"daily_cipa_visuals="
            f"{deleted_daily_visuals}, "
            f"cipa_portrait_visuals="
            f"{deleted_portrait_visuals}"
        )


async def save_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    if (
        message.from_user
        and message.from_user.is_bot
    ):
        return

    text = (
        message.text
        or message.caption
    )

    if not text:
        return

    if text.startswith("/"):
        return

    user = message.from_user

    user_id = (
        user.id
        if user
        else None
    )
    username = (
        user.username
        if user
        else None
    )
    display_name = (
        user.full_name
        if user
        else None
    )

    reply_to_message_id = None

    if message.reply_to_message:
        reply_to_message_id = (
            message.reply_to_message.message_id
        )

    save_message_to_db(
        chat_id=message.chat_id,
        message_id=message.message_id,
        user_id=user_id,
        username=username,
        display_name=display_name,
        text=text,
        timestamp=message.date.astimezone(
            timezone.utc
        ).isoformat(),
        reply_to_message_id=reply_to_message_id,
    )



async def cleanup_old_data_job(context):
    cleanup_old_data()


def get_messages_for_period(
    chat_id,
    hours=24,
    message_limit=None,
):
    hours = min(
        hours,
        MAX_HOURS,
    )

    if message_limit is None:
        message_limit = MAX_MESSAGES
    else:
        message_limit = min(
            max(message_limit, 1),
            MAX_MESSAGES,
        )

    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    )

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
            (
                chat_id,
                since.isoformat(),
                message_limit,
            ),
        ).fetchall()

    return list(
        reversed(rows)
    )


def get_messages_by_username(
    chat_id,
    username,
    hours=24,
):
    username = (
        username
        .lstrip("@")
        .strip()
    )

    if not username:
        return []

    hours = min(
        hours,
        MAX_HOURS,
    )

    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    )

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
            (
                chat_id,
                since.isoformat(),
                username,
                MAX_MESSAGES,
            ),
        ).fetchall()

    return list(rows)


def get_today_kyiv():
    return datetime.now(
        KYIV_TZ
    ).date().isoformat()


def get_daily_report_count(chat_id):
    today = get_today_kyiv()

    with get_db() as db:
        row = db.execute(
            """
            SELECT report_count
            FROM daily_report_usage
            WHERE chat_id = ?
              AND report_date = ?
            """,
            (
                chat_id,
                today,
            ),
        ).fetchone()

    return (
        row["report_count"]
        if row
        else 0
    )


def increment_daily_report_count(chat_id):
    today = get_today_kyiv()

    with get_db() as db:
        db.execute(
            """
            INSERT INTO daily_report_usage (
                chat_id,
                report_date,
                report_count
            )
            VALUES (?, ?, 1)
            ON CONFLICT(
                chat_id,
                report_date
            )
            DO UPDATE SET
                report_count =
                    report_count + 1
            """,
            (
                chat_id,
                today,
            ),
        )


def get_top_chickens(
    chat_id,
    limit=3,
):
    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    )

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
            GROUP BY
                user_id,
                username,
                display_name
            ORDER BY
                message_count DESC
            LIMIT ?
            """,
            (
                chat_id,
                since.isoformat(),
                limit,
            ),
        ).fetchall()

    return list(rows)


def get_active_chat_ids():
    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    )

    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT chat_id
            FROM messages
            WHERE timestamp >= ?
            """,
            (since.isoformat(),),
        ).fetchall()

    return [
        row["chat_id"]
        for row in rows
    ]


def save_daily_cipa_visuals(
    chat_id,
    visual_prompt,
    elements,
):
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
                datetime.now(
                    timezone.utc
                ).isoformat(),
                visual_prompt,
                json.dumps(
                    elements,
                    ensure_ascii=False,
                ),
            ),
        )


def get_latest_daily_cipa_visuals(
    chat_id,
):
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                generated_at,
                visual_prompt,
                elements_json
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
        elements = json.loads(
            row["elements_json"]
        )
    except Exception:
        elements = []

    return {
        "generated_at": row[
            "generated_at"
        ],
        "visual_prompt": row[
            "visual_prompt"
        ],
        "elements": elements,
    }


def save_cipa_portrait_visuals(
    chat_id,
    username,
    visual_prompt,
    elements,
):
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
                datetime.now(
                    timezone.utc
                ).isoformat(),
                visual_prompt,
                json.dumps(
                    elements,
                    ensure_ascii=False,
                ),
            ),
        )


def get_latest_cipa_portrait_visuals(
    chat_id,
):
    with get_db() as db:
        row = db.execute(
            """
            SELECT
                username,
                generated_at,
                visual_prompt,
                elements_json
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
        elements = json.loads(
            row["elements_json"]
        )
    except Exception:
        elements = []

    return {
        "username": row["username"],
        "generated_at": row[
            "generated_at"
        ],
        "visual_prompt": row[
            "visual_prompt"
        ],
        "elements": elements,
    }
