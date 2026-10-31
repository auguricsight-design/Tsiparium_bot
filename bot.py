from datetime import time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    OPENAI_API_KEY,
    DB_PATH,
    OPENAI_IMAGE_MODEL,
    OPENAI_IMAGE_QUALITY,
    KYIV_TZ,
)
from commands import (
    human_log_time,
    cipahow,
    ciparules,
    cipagames,
    cipainfo,
    welcome_new_members,
)
from db import (
    init_db,
    cleanup_old_data_job,
)
from messages_db import save_message
from reports import zvit
from daily_cipa import (
    dailycipa,
    dailycipawhy,
    daily_chicken_image_job,
)
from portraits import (
    portrait,
    lastcipawhy,
)
from games import (
    gameadd,
    game_private_start,
    game_private_message,
    game_cancel,
    gamestop,
    cipagamelimit,
    game_status_refresh_job,
)


async def error_handler(
    update,
    context,
):
    print(
        f"[{human_log_time()}] "
        f"Telegram error: "
        f"{repr(context.error)}"
    )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set"
        )

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set"
        )

    init_db()

    print(
        f"[{human_log_time()}] "
        f"Database path: {DB_PATH}"
    )
    print(
        f"[{human_log_time()}] "
        f"Image model: {OPENAI_IMAGE_MODEL}"
    )
    print(
        f"[{human_log_time()}] "
        f"Image quality: "
        f"{OPENAI_IMAGE_QUALITY}"
    )

    app = (
        Application
        .builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "zvit",
            zvit,
        )
    )

    app.add_handler(
        CommandHandler(
            "cipahow",
            cipahow,
        )
    )

    app.add_handler(
        CommandHandler(
            "cipainfo",
            cipainfo,
        )
    )

    app.add_handler(
        CommandHandler(
            "ciparules",
            ciparules,
        )
    )

    app.add_handler(
        CommandHandler(
            "cipagames",
            cipagames,
        )
    )


    app.add_handler(
        CommandHandler(
            "start",
            game_private_start,
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            game_cancel,
        )
    )

    app.add_handler(
        CommandHandler(
            "gameadd",
            gameadd,
        )
    )

    app.add_handler(
        CommandHandler(
            "gamestop",
            gamestop,
        )
    )

    app.add_handler(
        CommandHandler(
            "cipagamelimit",
            cipagamelimit,
        )
    )

    app.add_handler(
        CommandHandler(
            "dailycipa",
            dailycipa,
        )
    )

    app.add_handler(
        CommandHandler(
            "dailycipawhy",
            dailycipawhy,
        )
    )

    app.add_handler(
        CommandHandler(
            "portrait",
            portrait,
        )
    )

    app.add_handler(
        CommandHandler(
            "lastcipawhy",
            lastcipawhy,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_members,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND,
            game_private_message,
        )
    )

    app.add_handler(
        MessageHandler(
            ~filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND,
            save_message,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.CAPTION,
            save_message,
        )
    )

    app.add_error_handler(
        error_handler
    )

    app.job_queue.run_repeating(
        game_status_refresh_job,
        interval=60,
        first=10,
        name="game_status_refresh_job",
    )

    app.job_queue.run_daily(
        daily_chicken_image_job,
        time=time(
            hour=23,
            minute=0,
            tzinfo=KYIV_TZ,
        ),
        name="daily_chicken_image_job",
    )

    app.job_queue.run_daily(
        cleanup_old_data_job,
        time=time(
            hour=0,
            minute=10,
            tzinfo=KYIV_TZ,
        ),
        name="daily_cleanup_job",
    )

    print(
        f"[{human_log_time()}] "
        "Ципаріум запущено 🐔"
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
