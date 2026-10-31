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


async def cipahow(
    update,
    context,
):
    message = update.effective_message

    if not message:
        return

    text = (
        "🐔 Команди Ціпаріума\n\n"
        "Загальнодоступні:\n"
        "• /zvit — короткий звіт за останні 24 години.\n"
        "• /zvit 2d — звіт за 2 дні.\n"
        "• /zvit 3d — звіт за 3 дні.\n"
        "• /zvit 4d — звіт за 4 дні.\n"
        "• /zvit 5d — звіт за 5 днів.\n"
        "• /zvit 24h, /zvit 48h, /zvit 72h, /zvit 96h, /zvit 120h — "
        "ті самі періоди у годинах.\n"
        "• /zvit N — звіт за останні N повідомлень, максимум 1000 "
        "і не старіше 5 днів.\n"
        "• /zvit detailed — детальний звіт за 24 години.\n"
        "• /zvit 2d detailed, /zvit 3d detailed, /zvit 4d detailed, "
        "/zvit 5d detailed — детальний звіт за вибраний період.\n"
        "• /zvit N detailed — детальний звіт за останні N повідомлень.\n"
        "• /zvit cipa @nickname — короткий підсумок повідомлень "
        "конкретної ціпочки за останні 24 години.\n"
        "• /portrait cipa @nickname — персональний портрет-курочка "
        "за темами цієї ціпочки за останні 5 днів.\n"
        "• /lastcipawhy — пояснює ключові елементи останнього "
        "персонального портрета.\n"
        "• /cipahow — показує цей список команд.\n"
        "• /cipainfo — інформація про Ціпаріум (заготовка).\n"
        "• /gameadd — запускає додавання нової гри через приватний діалог із ботом.\n"
        "• /gamestop — завершити активну гру (заготовка).\n"
        "• /cipagamelimit — показує максимальну кількість одночасно "
        "активних ігор у чаті.\n\n"
        "Тільки для адмінів чату:\n"
        "• /dailycipa — вручну запускає Daily Cipa: картинка за темами "
        "останніх 24 годин + топ-3 активних ціпочок у випадковому порядку.\n"
        "• /dailycipawhy — пояснює походження ключових елементів "
        "останньої Daily Cipa-картинки.\n\n"
        "Автоматично щодня о 23:00 за Києвом запускається Daily Cipa."
    )

    await send_long_message(
        message,
        text,
    )


async def welcome_new_members(
    update,
    context,
):
    message = update.effective_message

    if not message or not message.new_chat_members:
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        if member.username:
            member_name = f"@{member.username}"
        else:
            member_name = member.full_name

        welcome_text = (
            f"{member_name}, вітаю в Ціпаріумі!\n\n"
            "У нас тут багато кіпішу й приємна тепла атмосфера. "
            "Щоб вона лишалася такою ж — ознайомся з правилами чату, будь ласка. "
            "Знайти їх можна за командою /ciparules.\n\n"
            "А ще ми постійно граємо в щось цікаве. "
            "Актуальні ігри доступні за командою /cipagames.\n\n"
            "А загалом — шалом та велкам! Показуй котів/собак, їжу чи вишивку — "
            "ми раді всьому :)"
        )

        await message.reply_text(
            welcome_text
        )


async def ciparules(
    update,
    context,
):
    message = update.effective_message

    if not message:
        return

    await message.reply_text(
        "🐔 Правила Ціпаріума скоро з'являться тут."
    )


async def cipagames(
    update,
    context,
):
    message = update.effective_message

    if not message:
        return

    await message.reply_text(
        "🎮 Список актуальних ігор скоро з'явиться тут."
    )


async def cipainfo(
    update,
    context,
):
    message = update.effective_message

    if not message:
        return

    await message.reply_text(
        "🐔 Інформація про Ціпаріум скоро з'явиться тут."
    )
