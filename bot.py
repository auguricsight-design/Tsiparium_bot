import logging
from datetime import time

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from logging_config import configure_logging

from config import (
    TELEGRAM_BOT_TOKEN,
    OPENAI_API_KEY,
    DB_PATH,
    OPENAI_IMAGE_MODEL,
    OPENAI_IMAGE_QUALITY,
    KYIV_TZ,
)
from commands import (
    cipainfo_add_message,
    human_log_time,
    cipahow,
    ciparules,
    cipainfo,
    cipainfo_callback,
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
    cipagames,
    cipagames_callback,
    game_private_start,
    game_private_message,
    game_form_callback,
    cipagamelimit,
    game_status_refresh_job,
)



logger = logging.getLogger(__name__)

async def error_handler(
    update,
    context,
):
    error = context.error
    logger.error(
        "[%s] Telegram error: %r",
        human_log_time(),
        error,
        exc_info=(
            type(error),
            error,
            error.__traceback__,
        ) if error else None,
    )


async def private_text_router(update, context):
    if context.user_data.get("cipainfo_add_section"):
        await cipainfo_add_message(
            update,
            context,
        )
        return

    await game_private_message(
        update,
        context,
    )


def main():
    configure_logging()

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set"
        )

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set"
        )

    init_db()

    logger.info(
        f"[{human_log_time()}] "
        f"Database path: {DB_PATH}"
    )
    logger.info(
        f"[{human_log_time()}] "
        f"Image model: {OPENAI_IMAGE_MODEL}"
    )
    logger.info(
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
        CallbackQueryHandler(
            cipainfo_callback,
            pattern=r"^cipainfo:",
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
        CallbackQueryHandler(
            cipagames_callback,
            pattern=r"^cipagames:",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            game_form_callback,
            pattern=r"^gameform:",
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
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND,
            private_text_router,
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

    app.job_queue.run_daily(
        game_status_refresh_job,
        time=time(
            hour=0,
            minute=5,
            tzinfo=KYIV_TZ,
        ),
        name="daily_game_status_job",
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

    logger.info(
        f"[{human_log_time()}] "
        "Ципаріум запущено 🐔"
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
