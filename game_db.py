from datetime import datetime, timezone

from db import get_db


def add_game(
    chat_id,
    name,
    rules,
    start_at,
    finish_at,
    author,
    author_user_id,
    prizes,
    hashtag,
    status,
):
    created_at = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO games (
                chat_id,
                name,
                rules,
                start_at,
                finish_at,
                author,
                author_user_id,
                prizes,
                hashtag,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                name,
                rules,
                start_at,
                finish_at,
                author,
                author_user_id,
                prizes,
                hashtag,
                status,
                created_at,
            ),
        )
        return cursor.lastrowid


def activate_pending_games(now_iso):
    with get_db() as db:
        db.execute(
            """
            UPDATE games
            SET status = 'active'
            WHERE status = 'pending'
              AND start_at IS NOT NULL
              AND start_at <= ?
              AND (finish_at IS NULL OR finish_at > ?)
            """,
            (now_iso, now_iso),
        )


def get_active_games_count(chat_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM games
            WHERE chat_id = ?
              AND status = 'active'
            """,
            (chat_id,),
        ).fetchone()
    return int(row["count"] if row else 0)


def mark_game_completed(chat_id, game_id):
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE games
            SET status = 'completed'
            WHERE chat_id = ?
              AND id = ?
              AND status != 'completed'
            """,
            (chat_id, game_id),
        )
        return cursor.rowcount > 0


def get_game_by_id(chat_id, game_id):
    with get_db() as db:
        return db.execute(
            """
            SELECT *
            FROM games
            WHERE chat_id = ?
              AND id = ?
            """,
            (chat_id, game_id),
        ).fetchone()
