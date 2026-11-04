from config import KYIV_TZ, MAX_ACTIVE_GAMES
from datetime import datetime, timezone

from db import get_db


class ActiveGameLimitReached(Exception):
    def __init__(self, active_count):
        self.active_count = active_count
        super().__init__(
            f"Active game limit reached: {active_count}/{MAX_ACTIVE_GAMES}"
        )


def _parse_game_start_date(value):
    if not value:
        return None

    value = str(value).strip()

    # Current format: date only.
    try:
        return datetime.strptime(
            value,
            "%d.%m.%Y",
        ).date()
    except ValueError:
        pass

    # Backward compatibility for older records with time.
    try:
        return datetime.strptime(
            value,
            "%d.%m.%Y %H:%M",
        ).date()
    except ValueError:
        pass

    # Backward compatibility for ISO datetime/date records.
    try:
        dt = datetime.fromisoformat(value)
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KYIV_TZ)
            return dt.astimezone(KYIV_TZ).date()
    except (TypeError, ValueError):
        pass

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def _status_from_start(start_date, today):
    if start_date <= today:
        return "active"
    return "pending"


def _refresh_game_statuses_in_db(db, chat_id=None, now=None):
    today = (now or datetime.now(KYIV_TZ)).date()

    if chat_id is None:
        rows = db.execute(
            """
            SELECT id, start_at, status
            FROM games
            WHERE status IN ('pending', 'active')
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT id, start_at, status
            FROM games
            WHERE chat_id = ?
              AND status IN ('pending', 'active')
            """,
            (chat_id,),
        ).fetchall()

    for row in rows:
        try:
            start_date = _parse_game_start_date(
                row["start_at"]
            )
        except (TypeError, ValueError):
            continue

        if not start_date:
            continue

        new_status = _status_from_start(
            start_date,
            today,
        )

        if new_status != row["status"]:
            db.execute(
                """
                UPDATE games
                SET status = ?
                WHERE id = ?
                  AND status != 'completed'
                """,
                (new_status, row["id"]),
            )


def refresh_game_statuses(chat_id=None):
    """Synchronize time-derived statuses before critical checks.

    completed is terminal. Games with a start date in the past or
    on the current Kyiv calendar day are active. Future dates are
    pending. finish_at never auto-completes a game.
    """
    with get_db() as db:
        _refresh_game_statuses_in_db(
            db,
            chat_id=chat_id,
        )
        db.commit()


def add_game_with_limit(
    chat_id,
    name,
    rules,
    start_at,
    finish_at,
    author,
    author_user_id,
    prizes,
    hashtag,
):
    """Create a game and atomically enforce the active-game limit.

    If the start date is today or in the past, the game is created
    as active only when the chat has a free active slot. Future
    games are created as pending and do not consume an active slot.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    now = datetime.now(KYIV_TZ)
    parsed_start = _parse_game_start_date(start_at)
    if not parsed_start:
        raise ValueError("Invalid start_at date")
    status = _status_from_start(parsed_start, now.date())

    with get_db() as db:
        # Serialize the refresh/count/insert sequence to avoid two
        # simultaneous forms both claiming the final active slot.
        db.execute("BEGIN IMMEDIATE")
        _refresh_game_statuses_in_db(
            db,
            chat_id=chat_id,
            now=now,
        )

        active_count = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM games
            WHERE chat_id = ?
              AND status = 'active'
            """,
            (chat_id,),
        ).fetchone()["count"]

        if (
            status == "active"
            and active_count >= MAX_ACTIVE_GAMES
        ):
            db.rollback()
            raise ActiveGameLimitReached(
                int(active_count)
            )

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
        db.commit()

    return cursor.lastrowid, status


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



def get_active_games_count(chat_id):
    refresh_game_statuses(chat_id)
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
    refresh_game_statuses(chat_id)
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
