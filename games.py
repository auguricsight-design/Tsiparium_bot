import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType

from config import MAX_ACTIVE_GAMES, KYIV_TZ
from content_db import get_static_content
from commands import is_chat_admin, send_cipainfo_menu, send_long_message
from game_db import (
    refresh_game_statuses,
    add_game_with_limit,
    ActiveGameLimitReached,
    mark_game_completed,
    get_game_by_id,
    get_active_games_count,
)


GAME_FIELDS = [
    ("name", "🎮 Як називається гра?"),
    ("rules", "📜 Напиши правила гри."),
    ("start_at", "🟢 Коли стартує гра? Вкажи дату у форматі ДД.ММ.РРРР."),
    ("finish_at", "🏁 Коли фінішує гра? Вкажи дату у форматі ДД.ММ.РРРР."),
    ("prizes", "🏆 Які призи передбачені? Якщо призів немає — напиши «немає»."),
    ("hashtag", "#️⃣ Вкажи хештег гри, наприклад #моягра."),
]



logger = logging.getLogger(__name__)

def parse_game_start_date(value):
    return datetime.strptime(
        value,
        "%d.%m.%Y",
    ).date()


def parse_game_datetime(value):
    return datetime.strptime(
        value,
        "%d.%m.%Y %H:%M",
    ).replace(tzinfo=KYIV_TZ)


def format_game_datetime(dt):
    return dt.astimezone(KYIV_TZ).strftime(
        "%d.%m.%Y %H:%M"
    )


async def game_status_refresh_job(context):
    refresh_game_statuses()


async def gameadd(update, context):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if message.chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "Щоб додати гру, виклич /gameadd у групі Ціпаріума."
        )
        return

    refresh_game_statuses(chat_id)
    active_count = get_active_games_count(
        message.chat_id
    )

    if active_count >= MAX_ACTIVE_GAMES:
        await message.reply_text(
            "🎮 У Ціпаріумі вже максимальна кількість "
            f"активних ігор: {active_count}/{MAX_ACTIVE_GAMES}.\n\n"
            "Спочатку завершіть одну з активних ігор через /gamestop."
        )
        return

    bot_info = await context.bot.get_me()
    payload = f"gameadd_{message.chat_id}_{user.id}"
    url = f"https://t.me/{bot_info.username}?start={payload}"

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🎮 Додати гру в приваті",
                url=url,
            )
        ]]
    )

    mention = f"@{user.username}" if user.username else user.full_name
    await message.reply_text(
        f"{mention}, натисни кнопку нижче, щоб додати гру в приватному діалозі з ботом.",
        reply_markup=keyboard,
    )


async def game_private_start(update, context):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or message.chat.type != ChatType.PRIVATE:
        return

    if context.args and context.args[0] == "cipainfo":
        await send_cipainfo_menu(
            context.bot,
            message.chat_id,
        )
        return

    if context.args and context.args[0] == "ciparules":
        rules_text = get_static_content(
            "ciparules"
        )
        if not rules_text:
            await message.reply_text(
                "🐔 Правила Ціпаріума поки недоступні."
            )
            return
        await send_long_message(
            message,
            rules_text,
        )
        return

    if not context.args:
        await message.reply_text(
            "Привіт! Щоб додати гру, спочатку виклич /gameadd у групі Ціпаріума."
        )
        return

    payload = context.args[0]
    if not payload.startswith("gameadd_"):
        await message.reply_text(
            "Це посилання не запускає форму додавання гри."
        )
        return

    try:
        raw = payload.removeprefix("gameadd_")
        chat_id_text, requester_id_text = raw.rsplit("_", 1)
        chat_id = int(chat_id_text)
        requester_id = int(requester_id_text)
    except (ValueError, TypeError):
        await message.reply_text(
            "Не вдалося прочитати посилання для додавання гри."
        )
        return

    if requester_id != user.id:
        await message.reply_text(
            "Це посилання створене для іншої ціпочки. "
            "Виклич /gameadd у групі самостійно."
        )
        return

    try:
        member = await context.bot.get_chat_member(
            chat_id=chat_id,
            user_id=user.id,
        )
        if member.status in ("left", "kicked"):
            raise ValueError("not a member")
    except Exception:
        await message.reply_text(
            "Не вдалося підтвердити, що ти є в цьому чаті. "
            "Спробуй ще раз через /gameadd у групі."
        )
        return

    refresh_game_statuses(chat_id)
    active_count = get_active_games_count(
        chat_id
    )

    if active_count >= MAX_ACTIVE_GAMES:
        await message.reply_text(
            "🎮 Поки ти йшла до курятника, місця закінчилися 😅\n\n"
            f"Зараз активних ігор: {active_count}/{MAX_ACTIVE_GAMES}. "
            "Спочатку потрібно завершити одну з них через /gamestop."
        )
        return

    author = (
        f"@{user.username}"
        if user.username
        else user.full_name
    )

    context.user_data["game_form"] = {
        "chat_id": chat_id,
        "field_index": 0,
        "data": {
            "author": author,
            "author_user_id": user.id,
        },
    }

    await message.reply_text(
        "🎮 Починаємо додавання нової гри.\n\n"
        "Щоб запустити гру, потрібно буде заповнити такі поля:\n"
        "• назва гри;\n"
        "• правила;\n"
        "• старт;\n"
        "• фініш;\n"
        "• призи;\n"
        "• хештег гри.\n\n"
        f"Автор буде вказаний автоматично: {author}.\n\n"
        "Після завершення гри її потрібно буде закрити командою /gamestop.\n"
        "Якщо передумаєш під час заповнення форми — використай /cancel.\n\n"
        f"{GAME_FIELDS[0][1]}"
    )


async def game_private_message(update, context):
    message = update.effective_message
    if not message or message.chat.type != ChatType.PRIVATE:
        return

    form = context.user_data.get("game_form")
    if not form:
        return

    value = (message.text or "").strip()
    if not value:
        await message.reply_text("Поле не може бути порожнім. Спробуй ще раз.")
        return

    field_index = form["field_index"]
    field_name = GAME_FIELDS[field_index][0]

    if field_name == "start_at":
        try:
            parsed_start = parse_game_start_date(
                value
            )
        except ValueError:
            await message.reply_text(
                "Не вдалося прочитати дату старту. "
                "Використай формат ДД.ММ.РРРР, "
                "наприклад 05.11.2026."
            )
            return

        value = parsed_start.strftime(
            "%d.%m.%Y"
        )

    elif field_name == "finish_at":
        try:
            finish_date = parse_game_start_date(
                value
            )
        except ValueError:
            await message.reply_text(
                "Не вдалося прочитати дату фінішу. "
                "Використай формат ДД.ММ.РРРР, "
                "наприклад 05.12.2026."
            )
            return

        start_date = parse_game_start_date(
            form["data"]["start_at"]
        )
        if finish_date < start_date:
            await message.reply_text(
                "Фініш не може бути раніше за старт гри. "
                "Спробуй ще раз."
            )
            return

        if finish_date < datetime.now(KYIV_TZ).date():
            await message.reply_text(
                "Фініш гри не може бути в минулому. "
                "Спробуй ще раз."
            )
            return

        value = finish_date.strftime(
            "%d.%m.%Y"
        )

    form["data"][field_name] = value
    field_index += 1

    if field_index < len(GAME_FIELDS):
        form["field_index"] = field_index
        await message.reply_text(GAME_FIELDS[field_index][1])
        return

    data = form["data"]

    try:
        game_id, status = add_game_with_limit(
            chat_id=form["chat_id"],
            name=data["name"],
            rules=data["rules"],
            start_at=data["start_at"],
            finish_at=data["finish_at"],
            author=data["author"],
            author_user_id=data["author_user_id"],
            prizes=data["prizes"],
            hashtag=data["hashtag"],
        )
    except ActiveGameLimitReached as exc:
        context.user_data.pop("game_form", None)

        await message.reply_text(
            "🐔 Усі щаблі насісту зайняті :(\n\n"
            "Поки ти заповнювала форму, активних ігор "
            f"стало {exc.active_count}/{MAX_ACTIVE_GAMES}. "
            "Цю гру не активовано й не додано. "
            "Подивись активні ігри та спробуй ще раз, "
            "коли звільниться місце."
        )
        return

    group_announcement = (
        "🎮 В Ціпаріумі нова гра!\n\n"
        f"Назва: {data['name']}\n"
        f"Автор: {data['author']}\n"
        f"Старт: {data['start_at']}\n"
        f"Фініш: {data['finish_at']}\n"
        f"Призи: {data['prizes']}\n"
        f"Хештег: {data['hashtag']}\n\n"
        f"Правила гри:\n{data['rules']}"
    )

    announcement_sent = True
    try:
        await context.bot.send_message(
            chat_id=form["chat_id"],
            text=group_announcement,
        )
    except Exception as e:
        announcement_sent = False
        logger.exception(
            "GAME ANNOUNCEMENT ERROR | chat_id=%s | game_id=%s | "
            "game_name=%r | author=%r | start_at=%r | finish_at=%r | "
            "hashtag=%r",
            form["chat_id"],
            game_id,
            data["name"],
            data["author"],
            data["start_at"],
            data["finish_at"],
            data["hashtag"],
        )

    context.user_data.pop("game_form", None)

    private_confirmation = (
        "✅ Гру збережено!\n\n"
        f"ID: {game_id}\n"
        f"Назва: {data['name']}\n"
        f"Старт: {data['start_at']}\n"
        f"Фініш: {data['finish_at']}\n"
        f"Статус: {status}\n"
        f"Автор: {data['author']}\n"
        f"Призи: {data['prizes']}\n"
        f"Хештег: {data['hashtag']}\n\n"
        f"Правила:\n{data['rules']}"
    )

    if announcement_sent:
        private_confirmation += (
            "\n\n📣 Анонс гри вже опубліковано "
            "в Ціпаріумі."
        )
    else:
        private_confirmation = (
            "🐔 Ой-ой, щось пішло не так!\n\n"
            "Напиши @shalkara — нехай-но загляне в курятник 🛠️"
        )

    await message.reply_text(private_confirmation)


async def game_cancel(update, context):
    message = update.effective_message
    if not message:
        return

    if context.user_data.pop("game_form", None):
        await message.reply_text("❌ Додавання гри скасовано.")
    elif message.chat.type == ChatType.PRIVATE:
        await message.reply_text("Зараз немає активної форми додавання гри.")


async def gamestop(update, context):
    message = update.effective_message
    if not message:
        return

    if message.chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "Команду /gamestop потрібно викликати в чаті Ціпаріума."
        )
        return

    if not context.args:
        await message.reply_text(
            "🛑 Щоб завершити гру, вкажи її ID: /gamestop 123"
        )
        return

    try:
        game_id = int(context.args[0])
    except ValueError:
        await message.reply_text(
            "ID гри має бути числом. Наприклад: /gamestop 123"
        )
        return

    game = get_game_by_id(
        message.chat_id,
        game_id,
    )
    if not game:
        await message.reply_text(
            "Не знайшла гру з таким ID у цьому чаті."
        )
        return

    if game["status"] == "completed":
        await message.reply_text(
            "✅ Ця гра вже завершена."
        )
        return

    user = update.effective_user
    if not user:
        return

    is_admin = await is_chat_admin(
        message.chat_id,
        user.id,
        context,
    )

    is_author = False
    if game["author_user_id"]:
        is_author = (
            int(game["author_user_id"])
            == user.id
        )
    elif user.username and game["author"]:
        is_author = (
            game["author"].strip().lower()
            == f"@{user.username}".lower()
        )

    if not (is_admin or is_author):
        await message.reply_text(
            "🐔 Цю гру може завершити лише її автор або адмін чату."
        )
        return

    if mark_game_completed(
        message.chat_id,
        game_id,
    ):
        await message.reply_text(
            "🏁 Ну все, курочки — час розслабити хвостики! 🐔✨\n\n"
            f"Гру «{game['name']}» завершено. Дякую всім за кіпіш 💛"
        )


async def cipagamelimit(update, context):
    message = update.effective_message
    if not message:
        return

    if message.chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "Команду /cipagamelimit потрібно викликати в чаті Ціпаріума."
        )
        return

    refresh_game_statuses(message.chat_id)
    active_count = get_active_games_count(
        message.chat_id
    )

    await message.reply_text(
        "🎮 Активні ігри в Ціпаріумі: "
        f"{active_count}/{MAX_ACTIVE_GAMES}."
    )
