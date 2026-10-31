def add_missing_columns(db, table_name, columns):
    existing_columns = {
        row["name"]
        for row in db.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            db.execute(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {column_type}"
            )


def migrate_games_table(db):
    add_missing_columns(
        db,
        "games",
        {
            "start_at": "TEXT",
            "finish_at": "TEXT",
            "author": "TEXT",
            "author_user_id": "INTEGER",
            "prizes": "TEXT",
            "hashtag": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "created_at": "TEXT",
        },
    )


def run_migrations(db):
    migrate_games_table(db)
