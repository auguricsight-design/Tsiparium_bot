from datetime import datetime

from config import KYIV_TZ
from db import get_db


def get_today_kyiv():
    return datetime.now(KYIV_TZ).date().isoformat()


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
            (chat_id, today),
        ).fetchone()
    return row["report_count"] if row else 0


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
            ON CONFLICT(chat_id, report_date)
            DO UPDATE SET report_count = report_count + 1
            """,
            (chat_id, today),
        )
