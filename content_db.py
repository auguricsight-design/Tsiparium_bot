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
