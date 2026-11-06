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
    get_active_games,
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


CIPAGAMES_MENU_PREFIX = "cipagames:menu:"
CIPAGAMES_GAME_PREFIX = "cipagames:game:"
CIPAGAMES_LIMIT_PREFIX = "cipagames:limit:"
CIPAGAMES_FINISH_PREFIX = "cipagames:finish:"
GAME_FORM_CONFIRM_CALLBACK = "gameform:confirm"
GAME_FORM_CANCEL_CALLBACK = "gameform:cancel"


def _cipagames_markup(
    games_list,
    source_chat_id,
    bot_username,
):
    rows = []

    for game in games_list:
        label = f"🎮 {game['name']}"
        if len(label) > 52:
            label = label[:49] + "..."

        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=(
                    f"{CIPAGAMES_GAME_PREFIX}"
                    f"{source_chat_id}:{game['id']}"
                ),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "📊 Ліміт активних ігор",
            callback_data=(
                f"{CIPAGAMES_LIMIT_PREFIX}"
                f"{source_chat_id}"
            ),
        )
    ])

    if len(games_list) < MAX_ACTIVE_GAMES:
        rows.append([
            InlineKeyboardButton(
                "➕ Додати гру",
                url=(
                    f"https://t.me/{bot_username}"
                    f"?start=gameadd_{source_chat_id}"
                ),
            )
        ])

    return InlineKeyboardMarkup(rows)


def _cipagames_menu_text(games_list):
    active_count = len(games_list)

    if games_list:
        text = (
            "🎮 Активні ігри Ціпаріума\n\n"
            f"Зараз активних ігор: "
            f"{active_count}/{MAX_ACTIVE_GAMES}.\n\n"
            "Обери гру, щоб переглянути деталі та правила."
        )
    else:
        text = (
            "🎮 Активні ігри Ціпаріума\n\n"
            "Зараз активних ігор немає."
        )

    if active_count >= MAX_ACTIVE_GAMES:
        text += (
            "\n\n🐔 Усі щаблі насісту зайняті — "
            "нову гру можна буде додати після завершення "
            "однієї з активних."
        )

    return text


def _format_admin_cipagames_text(games_list):
    if not games_list:
        return (
            "🎮 Активних ігор зараз немає.\n\n"
            "Правила гри можна почитати, викликавши /cipagames."
        )

    blocks = []

    for game in games_list:
        blocks.append(
            f"{game['name']}\n\n"
            f"Організатор: {game['author']}\n"
            f"Хештег: {game['hashtag']}\n"
            f"{game['start_at']}–{game['finish_at']}"
        )

    return (
        "\n\n".join(blocks)
        + "\n\n"
        + "Правила гри можна почитати, викликавши /cipagames."
    )


async def _can_finish_game(
    game,
    user,
    source_chat_id,
    context,
):
    if not user:
        return False

    if await is_chat_admin(
        source_chat_id,
        user.id,
        context,
    ):
        return True

    if game["author_user_id"]:
        return (
            int(game["author_user_id"])
            == user.id
        )

    if user.username and game["author"]:
        return (
            game["author"].strip().lower()
            == f"@{user.username}".lower()
        )

    return False


async def send_cipagames_menu(
    bot,
    target_chat_id,
    source_chat_id,
):
    refresh_game_statuses(source_chat_id)
    games_list = get_active_games(source_chat_id)
    bot_info = await bot.get_me()

    await bot.send_message(
        chat_id=target_chat_id,
        text=_cipagames_menu_text(games_list),
        reply_markup=_cipagames_markup(
            games_list,
            source_chat_id,
            bot_info.username,
        ),
    )


async def cipagames(update, context):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type == ChatType.PRIVATE:
        source_chat_id = context.user_data.get(
            "cipagames_source_chat_id"
        )
        if not source_chat_id:
            await message.reply_text(
                "🐔 Відкрий /cipagames у групі Ціпаріума, "
                "щоб я знала, для якого чату показати ігри."
            )
            return

        await send_cipagames_menu(
            context.bot,
            chat.id,
            source_chat_id,
        )
        return

    if await is_chat_admin(
        chat.id,
        user.id,
        context,
    ):
        refresh_game_statuses(chat.id)
        games_list = get_active_games(
            chat.id
        )

        await message.reply_text(
            _format_admin_cipagames_text(
                games_list
            )
        )
        return

    try:
        context.user_data[
            "cipagames_source_chat_id"
        ] = chat.id

        await send_cipagames_menu(
            context.bot,
            user.id,
            chat.id,
        )

        await message.reply_text(
            "🐔 Активні ігри вже полетіли тобі в особисті."
        )
    except Exception:
        bot_info = await context.bot.get_me()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🎮 Відкрити ігри в приваті",
                url=(
                    f"https://t.me/{bot_info.username}"
                    f"?start=cipagames_{chat.id}"
                ),
            )
        ]])

        await message.reply_text(
            "🐔 Я ще не можу написати тобі в особисті. "
            "Відкрий приватний чат із ботом — "
            "там покажу активні ігри.",
            reply_markup=keyboard,
        )


async def cipagames_callback(update, context):
    query = update.callback_query

    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data.startswith(CIPAGAMES_MENU_PREFIX):
        try:
            source_chat_id = int(
                data.removeprefix(
                    CIPAGAMES_MENU_PREFIX
                )
            )
        except ValueError:
            return

        refresh_game_statuses(source_chat_id)
        games_list = get_active_games(source_chat_id)
        bot_info = await context.bot.get_me()

        await query.edit_message_text(
            text=_cipagames_menu_text(games_list),
            reply_markup=_cipagames_markup(
                games_list,
                source_chat_id,
                bot_info.username,
            ),
        )
        return

    if data.startswith(CIPAGAMES_LIMIT_PREFIX):
        try:
            source_chat_id = int(
                data.removeprefix(
                    CIPAGAMES_LIMIT_PREFIX
                )
            )
        except ValueError:
            return

        refresh_game_statuses(source_chat_id)
        active_count = get_active_games_count(
            source_chat_id
        )

        await query.edit_message_text(
            text=(
                "📊 Ліміт активних ігор\n\n"
                f"Зараз активних ігор: "
                f"{active_count}/{MAX_ACTIVE_GAMES}."
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⬅️ Назад до ігор",
                    callback_data=(
                        f"{CIPAGAMES_MENU_PREFIX}"
                        f"{source_chat_id}"
                    ),
                )
            ]]),
        )
        return

    if data.startswith(CIPAGAMES_FINISH_PREFIX):
        raw = data.removeprefix(
            CIPAGAMES_FINISH_PREFIX
        )

        try:
            chat_id_text, game_id_text = raw.split(
                ":",
                1,
            )
            source_chat_id = int(chat_id_text)
            game_id = int(game_id_text)
        except ValueError:
            return

        game = get_game_by_id(
            source_chat_id,
            game_id,
        )

        if not game:
            await query.edit_message_text(
                "🐔 Не знайшла цю гру."
            )
            return

        if game["status"] == "completed":
            await query.edit_message_text(
                "✅ Ця гра вже завершена.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Назад до ігор",
                        callback_data=(
                            f"{CIPAGAMES_MENU_PREFIX}"
                            f"{source_chat_id}"
                        ),
                    )
                ]]),
            )
            return

        if not await _can_finish_game(
            game,
            update.effective_user,
            source_chat_id,
            context,
        ):
            await query.answer(
                "Цю гру може завершити лише її автор або адмін.",
                show_alert=True,
            )
            return

        if mark_game_completed(
            source_chat_id,
            game_id,
        ):
            await query.edit_message_text(
                (
                    "🏁 Ну все, курочки — "
                    "час розслабити хвостики! 🐔✨\n\n"
                    f"Гру «{game['name']}» завершено. "
                    "Дякую всім за кіпіш 💛"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Назад до ігор",
                        callback_data=(
                            f"{CIPAGAMES_MENU_PREFIX}"
                            f"{source_chat_id}"
                        ),
                    )
                ]]),
            )
        return

    if data.startswith(CIPAGAMES_GAME_PREFIX):
        raw = data.removeprefix(
            CIPAGAMES_GAME_PREFIX
        )

        try:
            chat_id_text, game_id_text = raw.split(
                ":",
                1,
            )
            source_chat_id = int(chat_id_text)
            game_id = int(game_id_text)
        except ValueError:
            return

        game = get_game_by_id(
            source_chat_id,
            game_id,
        )

        back_button = InlineKeyboardButton(
            "⬅️ Назад до ігор",
            callback_data=(
                f"{CIPAGAMES_MENU_PREFIX}"
                f"{source_chat_id}"
            ),
        )

        if not game or game["status"] != "active":
            await query.edit_message_text(
                "🐔 Ця гра вже не активна.",
                reply_markup=InlineKeyboardMarkup([[
                    back_button
                ]]),
            )
            return

        buttons = [[back_button]]

        if await _can_finish_game(
            game,
            update.effective_user,
            source_chat_id,
            context,
        ):
            buttons.insert(
                0,
                [
                    InlineKeyboardButton(
                        "🏁 Завершити гру",
                        callback_data=(
                            f"{CIPAGAMES_FINISH_PREFIX}"
                            f"{source_chat_id}:{game_id}"
                        ),
                    )
                ],
            )

        details = (
            f"🎮 {game['name']}\n\n"
            f"ID: {game['id']}\n"
            f"Автор: {game['author']}\n"
            f"Старт: {game['start_at']}\n"
            f"Фініш: {game['finish_at']}\n"
            f"Призи: {game['prizes']}\n"
            f"Хештег: {game['hashtag']}\n\n"
            f"📜 Правила гри:\n{game['rules']}"
        )

        await query.edit_message_text(
            text=details,
            reply_markup=InlineKeyboardMarkup(
                buttons
            ),
        )


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

    refresh_game_statuses(message.chat_id)
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

    if (
        context.args
        and context.args[0].startswith(
            "cipagames_"
        )
    ):
        try:
            source_chat_id = int(
                context.args[0].removeprefix(
                    "cipagames_"
                )
            )
        except ValueError:
            await message.reply_text(
                "Не вдалося прочитати посилання на ігри."
            )
            return

        try:
            member = await context.bot.get_chat_member(
                chat_id=source_chat_id,
                user_id=user.id,
            )
            if member.status in ("left", "kicked"):
                raise ValueError("not a member")
        except Exception:
            await message.reply_text(
                "Не вдалося підтвердити, що ти є в цьому чаті."
            )
            return

        context.user_data[
            "cipagames_source_chat_id"
        ] = source_chat_id

        await send_cipagames_menu(
            context.bot,
            message.chat_id,
            source_chat_id,
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
            "Привіт! Відкрий /cipagames у групі Ціпаріума, щоб переглянути ігри або додати нову."
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

        if "_" in raw:
            chat_id_text, requester_id_text = raw.rsplit(
                "_",
                1,
            )
            chat_id = int(chat_id_text)
            requester_id = int(requester_id_text)

            if requester_id != user.id:
                await message.reply_text(
                    "Це посилання створене для іншої ціпочки."
                )
                return
        else:
            chat_id = int(raw)
    except (ValueError, TypeError):
        await message.reply_text(
            "Не вдалося прочитати посилання для додавання гри."
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
            "Спробуй ще раз через /cipagames у групі."
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
        "Після заповнення всіх полів зможеш підтвердити або відмінити додавання гри.\n\n"
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

    context.user_data["game_form_pending"] = {
        "chat_id": form["chat_id"],
        "data": dict(data),
    }
    context.user_data.pop(
        "game_form",
        None,
    )

    preview = (
        "🎮 Перевір гру перед додаванням:\n\n"
        f"Назва: {data['name']}\n"
        f"Автор: {data['author']}\n"
        f"Старт: {data['start_at']}\n"
        f"Фініш: {data['finish_at']}\n"
        f"Призи: {data['prizes']}\n"
        f"Хештег: {data['hashtag']}\n\n"
        f"Правила гри:\n{data['rules']}"
    )

    await message.reply_text(
        preview,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Додати",
                    callback_data=GAME_FORM_CONFIRM_CALLBACK,
                ),
                InlineKeyboardButton(
                    "❌ Відмінити",
                    callback_data=GAME_FORM_CANCEL_CALLBACK,
                ),
            ]
        ]),
    )


async def game_form_callback(update, context):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    pending = context.user_data.get(
        "game_form_pending"
    )

    if not pending:
        await query.edit_message_text(
            "🐔 Ця форма вже неактивна."
        )
        return

    if query.data == GAME_FORM_CANCEL_CALLBACK:
        context.user_data.pop(
            "game_form_pending",
            None,
        )
        await query.edit_message_text(
            "❌ Додавання гри відмінено."
        )
        return

    if query.data != GAME_FORM_CONFIRM_CALLBACK:
        return

    data = pending["data"]
    chat_id = pending["chat_id"]

    try:
        game_id, status = add_game_with_limit(
            chat_id=chat_id,
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
        context.user_data.pop(
            "game_form_pending",
            None,
        )
        await query.edit_message_text(
            "🐔 Усі щаблі насісту зайняті :(\n\n"
            "Поки ти заповнювала форму, активних ігор "
            f"стало {exc.active_count}/{MAX_ACTIVE_GAMES}. "
            "Цю гру не активовано й не додано."
        )
        return
    except Exception:
        logger.exception(
            "GAME CREATE ERROR | "
            "chat_id=%s | game_name=%r | author=%r | "
            "start_at=%r | finish_at=%r | hashtag=%r",
            chat_id,
            data["name"],
            data["author"],
            data["start_at"],
            data["finish_at"],
            data["hashtag"],
        )
        await query.edit_message_text(
            "🐔 Ой-ой, щось пішло не так!\n\n"
            "Напиши @shalkara — нехай-но загляне в курятник 🛠️"
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
            chat_id=chat_id,
            text=group_announcement,
        )
    except Exception:
        announcement_sent = False
        logger.exception(
            "GAME ANNOUNCEMENT ERROR | "
            "chat_id=%s | game_id=%s | game_name=%r | "
            "author=%r | start_at=%r | finish_at=%r | hashtag=%r",
            chat_id,
            game_id,
            data["name"],
            data["author"],
            data["start_at"],
            data["finish_at"],
            data["hashtag"],
        )

    context.user_data.pop(
        "game_form_pending",
        None,
    )

    if announcement_sent:
        await query.edit_message_text(
            "✅ Гру додано."
        )
    else:
        await query.edit_message_text(
            "🐔 Ой-ой, щось пішло не так!\n\n"
            "Напиши @shalkara — нехай-но загляне в курятник 🛠️"
        )


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
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "🐔 Ліміт активних ігор можна переглянути "
            "через меню /cipagames."
        )
        return

    if not await is_chat_admin(
        chat.id,
        user.id,
        context,
    ):
        await message.reply_text(
            "🐔 Ця команда доступна лише адмінам. "
            "Ліміт активних ігор можна переглянути "
            "через меню /cipagames у приваті."
        )
        return

    refresh_game_statuses(chat.id)
    active_count = get_active_games_count(
        chat.id
    )

    await message.reply_text(
        "📊 Ліміт активних ігор: "
        f"{active_count}/{MAX_ACTIVE_GAMES}."
    )
