from datetime import datetime

from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from config import KYIV_TZ


def human_log_time():
    return datetime.now(
        KYIV_TZ
    ).strftime("%d.%m.%Y %H:%M:%S")


async def is_chat_admin(
    chat_id,
    user_id,
    context: ContextTypes.DEFAULT_TYPE,
):
    member = await context.bot.get_chat_member(
        chat_id=chat_id,
        user_id=user_id,
    )

    return member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )


async def send_long_message(
    telegram_message,
    text,
    max_length=3900,
):
    if len(text) <= max_length:
        await telegram_message.reply_text(text)
        return

    chunks = []
    current = ""

    for paragraph in text.split("\n\n"):
        candidate = (
            current
            + ("\n\n" if current else "")
            + paragraph
        )

        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)

            while len(paragraph) > max_length:
                chunks.append(
                    paragraph[:max_length]
                )
                paragraph = paragraph[
                    max_length:
                ]

            current = paragraph

    if current:
        chunks.append(current)

    for chunk in chunks:
        await telegram_message.reply_text(
            chunk
        )
