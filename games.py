import traceback
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType

from config import MAX_ACTIVE_GAMES, KYIV_TZ
from commands import is_chat_admin
from game_db import (
    add_game,
    mark_game_completed,
    get_game_by_id,
    activate_pending_games,
    get_active_games_count,
)


GAME_FIELDS = [
    ("name", "🎮 Як називається гра?"),
    ("rules", "📜 Напиши правила гри."),
    ("start_at", "🟢 Коли стартує гра? Вкажи дату й час у форматі ДД.ММ.РРРР ГГ:ХХ за Києвом."),
    ("finish_at", "🏁 Коли фінішує гра? Вкажи дату й час у форматі ДД.ММ.РРРР ГГ:ХХ за Києвом."),
    ("prizes", "🏆 Які призи передбачені? Якщо призів немає — напиши «немає»."),
    ("hashtag", "#️⃣ Вкажи хештег гри, наприклад #моягра."),
]


def parse_game_datetime(value):
    return datetime.strptime(
        value,
        "%d.%m.%Y %H:%M",
    ).replace(tzinfo=KYIV_TZ)


def format_game_datetime(dt):
    return dt.astimezone(KYIV_TZ).strftime(
        "%d.%m.%Y %H:%M"
    )


def get_initial_game_status(start_dt, finish_dt):
    now = datetime.now(KYIV_TZ)
    if now < start_dt:
        return "pending"
    if start_dt <= now < finish_dt:
        return "active"
    return "active"


async def game_status_refresh_job(context):
    now_iso = datetime.now(KYIV_TZ).isoformat()
    activate_pending_games(now_iso)


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

    now_iso = datetime.now(KYIV_TZ).isoformat()
    activate_pending_games(now_iso)
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

    now_iso = datetime.now(KYIV_TZ).isoformat()
    activate_pending_games(now_iso)
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

    if field_name in ("start_at", "finish_at"):
        try:
            parsed_dt = parse_game_datetime(value)
        except ValueError:
            await message.reply_text(
                "Не вдалося прочитати дату. Використай формат "
                "ДД.ММ.РРРР ГГ:ХХ, наприклад 05.11.2026 19:30."
            )
            return

        if field_name == "finish_at":
            start_dt = parse_game_datetime(
                form["data"]["start_at"]
            )
            if parsed_dt <= start_dt:
                await message.reply_text(
                    "Фініш має бути пізніше за старт гри. Спробуй ще раз."
                )
                return
            if parsed_dt <= datetime.now(KYIV_TZ):
                await message.reply_text(
                    "Фініш гри має бути в майбутньому. Спробуй ще раз."
                )
                return

        value = format_game_datetime(parsed_dt)

    form["data"][field_name] = value
    field_index += 1

    if field_index < len(GAME_FIELDS):
        form["field_index"] = field_index
        await message.reply_text(GAME_FIELDS[field_index][1])
        return

    data = form["data"]
    start_dt = parse_game_datetime(data["start_at"])
    finish_dt = parse_game_datetime(data["finish_at"])
    status = get_initial_game_status(
        start_dt,
        finish_dt,
    )

    game_id = add_game(
        chat_id=form["chat_id"],
        name=data["name"],
        rules=data["rules"],
        start_at=start_dt.isoformat(),
        finish_at=finish_dt.isoformat(),
        author=data["author"],
        author_user_id=data["author_user_id"],
        prizes=data["prizes"],
        hashtag=data["hashtag"],
        status=status,
    )

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
        print(
            "===== GAME ANNOUNCEMENT ERROR =====\n"
            f"chat_id: {form['chat_id']}\n"
            f"game_id: {game_id}\n"
            f"game_name: {data['name']}\n"
            f"author: {data['author']}\n"
            f"start_at: {data['start_at']}\n"
            f"finish_at: {data['finish_at']}\n"
            f"hashtag: {data['hashtag']}\n"
            f"exception_type: {type(e).__name__}\n"
            f"exception: {e}\n"
            f"traceback:\n{traceback.format_exc()}"
            "==================================="
        )

    context.user_data.pop("game_form", None)

    private_confirmation = (
        "✅ Гру збережено!\n\n"
        f"ID: {game_id}\n"
        f"Назва: {data['name']}\n"
        f"Старт: {data['start_at']}\n"
        f"Фініш: {data['finish_at']}\n"
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

    now_iso = datetime.now(KYIV_TZ).isoformat()
    activate_pending_games(now_iso)
    active_count = get_active_games_count(
        message.chat_id
    )

    await message.reply_text(
        "🎮 Активні ігри в Ціпаріумі: "
        f"{active_count}/{MAX_ACTIVE_GAMES}."
    )
