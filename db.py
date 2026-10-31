import sqlite3
from datetime import datetime, timedelta, timezone

from telegram.ext import ContextTypes

from config import DB_PATH, MESSAGE_RETENTION_DAYS
from commands import human_log_time


def get_db():
    connection = sqlite3.connect(DB_PATH)
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
                PRIMARY KEY (chat_id, report_date)
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
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                rules TEXT NOT NULL,
                start_at TEXT,
                finish_at TEXT,
                author TEXT,
                author_user_id INTEGER,
                prizes TEXT,
                hashtag TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )

        game_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(games)").fetchall()
        }
        migrations = {
            "start_at": "TEXT",
            "finish_at": "TEXT",
            "author": "TEXT",
            "author_user_id": "INTEGER",
            "prizes": "TEXT",
            "hashtag": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "created_at": "TEXT",
        }
        for column, column_type in migrations.items():
            if column not in game_columns:
                db.execute(
                    f"ALTER TABLE games ADD COLUMN {column} {column_type}"
                )


def cleanup_old_data():
    cutoff = datetime.now(timezone.utc) - timedelta(days=MESSAGE_RETENTION_DAYS)
    cutoff_iso = cutoff.isoformat()

    with get_db() as db:
        messages_cursor = db.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff_iso,),
        )
        daily_visuals_cursor = db.execute(
            "DELETE FROM daily_cipa_visuals WHERE generated_at < ?",
            (cutoff_iso,),
        )
        portrait_visuals_cursor = db.execute(
            "DELETE FROM cipa_portrait_visuals WHERE generated_at < ?",
            (cutoff_iso,),
        )

    deleted_messages = messages_cursor.rowcount
    deleted_daily_visuals = daily_visuals_cursor.rowcount
    deleted_portrait_visuals = portrait_visuals_cursor.rowcount

    if deleted_messages or deleted_daily_visuals or deleted_portrait_visuals:
        print(
            f"[{human_log_time()}] Cleanup older than "
            f"{MESSAGE_RETENTION_DAYS} days: "
            f"messages={deleted_messages}, "
            f"daily_cipa_visuals={deleted_daily_visuals}, "
            f"cipa_portrait_visuals={deleted_portrait_visuals}"
        )


async def cleanup_old_data_job(context: ContextTypes.DEFAULT_TYPE):
    cleanup_old_data()
