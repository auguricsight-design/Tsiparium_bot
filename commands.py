import logging
from telegram.error import BadRequest, Forbidden, TelegramError
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime

logger = logging.getLogger(__name__)

from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from config import KYIV_TZ
from content_db import get_static_content, append_static_content



GROUP_ONLY_MESSAGE = (
    "🐔 Цю команду потрібно викликати в групі Ціпаріума."
)


def is_private_chat(update):
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


async def require_group_chat(update):
    if is_private_chat(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                GROUP_ONLY_MESSAGE
            )
        return False
    return True


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


async def send_long_message_to_chat(
    bot,
    chat_id,
    text,
    max_length=3900,
):
    if len(text) <= max_length:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
        )
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
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
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
        "• /portrait cipa @nickname — персональний портрет-курочка "
        "за темами цієї ціпочки за останні 5 днів.\n"
        "• /lastcipawhy — пояснює ключові елементи останнього "
        "персонального портрета.\n"
        "• /cipahow — показує цей список команд.\n"
        "• /cipainfo — корисна інформація Ціпаріуму.\n"
        "• /cipagames — активні ігри, їхні правила та додавання нової гри.\n"
        ""
        "• /cipagamelimit — показує кількість активних ігор і ліміт у чаті.\n\n"
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
            "Також у чаті працює бот для зручності та веселощів. "
            "Усі його команди та корисну інформацію можна переглянути за командою "
            "/cipahow або в закріпленому повідомленні.\n\n"
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
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    rules_text = get_static_content(
        "ciparules"
    )

    if not rules_text:
        await message.reply_text(
            "🐔 Правила Ціпаріума поки недоступні."
        )
        return

    if chat.type == "private":
        await send_long_message(
            message,
            rules_text,
        )
        return

    if await is_chat_admin(
        chat.id,
        user.id,
        context,
    ):
        await send_long_message(
            message,
            rules_text,
        )
        return

    try:
        chunks = []
        current = ""
        for paragraph in rules_text.split("\n\n"):
            candidate = (
                current
                + ("\n\n" if current else "")
                + paragraph
            )
            if len(candidate) <= 3900:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                while len(paragraph) > 3900:
                    chunks.append(paragraph[:3900])
                    paragraph = paragraph[3900:]
                current = paragraph
        if current:
            chunks.append(current)

        for chunk in chunks:
            await context.bot.send_message(
                chat_id=user.id,
                text=chunk,
            )

        await message.reply_text(
            "🐔 Правила вже полетіли тобі в особисті."
        )
    except (Forbidden, BadRequest, TelegramError):
        bot_info = await context.bot.get_me()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📜 Відкрити правила в приваті",
                url=(
                    f"https://t.me/{bot_info.username}"
                    "?start=ciparules"
                ),
            )
        ]])
        await message.reply_text(
            "🐔 Я ще не можу написати тобі в особисті. "
            "Відкрий приватний чат із ботом — там покажу правила.",
            reply_markup=keyboard,
        )



CIPAINFO_ADD_ERROR_MESSAGE = (
    "🐔 Ой-ой, щось пішло не так із додаванням свіженького!\n\n"
    "Напиши @shalkara — нехай-но загляне в курятник 🛠️"
)


async def handle_cipainfo_add_error(
    update,
    section=None,
    submitted_text=None,
):
    user = update.effective_user
    chat = update.effective_chat

    logger.exception(
        "CIPAINFO ADD ERROR | section=%s | user_id=%s | "
        "username=%s | chat_id=%s | text=%r",
        section,
        getattr(user, "id", None),
        getattr(user, "username", None),
        getattr(chat, "id", None),
        submitted_text,
    )

    message = update.effective_message
    if message:
        await message.reply_text(
            CIPAINFO_ADD_ERROR_MESSAGE
        )


CIPAINFO_MENU_CALLBACK = "cipainfo:menu"
CIPAINFO_WISHLIST_CALLBACK = "cipainfo:wishlist"
CIPAINFO_YOUTUBE_CALLBACK = "cipainfo:youtube"
CIPAINFO_THREADS_CALLBACK = "cipainfo:threads"
CIPAINFO_RULES_CALLBACK = "cipainfo:rules"
CIPAINFO_DESIGNERS_CALLBACK = "cipainfo:designers"
CIPAINFO_ADD_FRESH_CALLBACK = "cipainfo:addfresh"
CIPAINFO_ADD_YOUTUBE_CALLBACK = "cipainfo:add:youtube"
CIPAINFO_ADD_THREADS_CALLBACK = "cipainfo:add:threads"
CIPAINFO_ADD_DESIGNERS_CALLBACK = "cipainfo:add:designers"
CIPAINFO_ADD_SECTION_KEYS = {
    CIPAINFO_ADD_YOUTUBE_CALLBACK: "cipainfo_youtube",
    CIPAINFO_ADD_THREADS_CALLBACK: "cipainfo_threads",
    CIPAINFO_ADD_DESIGNERS_CALLBACK: "cipainfo_designers",
}




def cipainfo_menu_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎁 Вішліст чату",
                callback_data=CIPAINFO_WISHLIST_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ YouTube-канали учасників",
                callback_data=CIPAINFO_YOUTUBE_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "🧵 Тематичні гілки чату",
                callback_data=CIPAINFO_THREADS_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 Ціпи-дизайнери",
                callback_data=CIPAINFO_DESIGNERS_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "📜 Правила чату",
                callback_data=CIPAINFO_RULES_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "➕ Додати свіженьке",
                callback_data=CIPAINFO_ADD_FRESH_CALLBACK,
            )
        ],
    ])


def cipainfo_add_fresh_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "▶️ YouTube-канали",
                callback_data=CIPAINFO_ADD_YOUTUBE_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "🧵 Тематичні гілки",
                callback_data=CIPAINFO_ADD_THREADS_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 Ціпи-дизайнери",
                callback_data=CIPAINFO_ADD_DESIGNERS_CALLBACK,
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Назад до меню",
                callback_data=CIPAINFO_MENU_CALLBACK,
            )
        ],
    ])



def cipainfo_add_back_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=CIPAINFO_ADD_FRESH_CALLBACK,
        )
    ]])


def cipainfo_back_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⬅️ Назад до меню",
            callback_data=CIPAINFO_MENU_CALLBACK,
        )
    ]])


async def cipainfo(
    update,
    context,
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type == "private":
        await send_cipainfo_menu(
            context.bot,
            chat.id,
        )
        return

    try:
        await send_cipainfo_menu(
            context.bot,
            user.id,
        )
        await message.reply_text(
            "🐔 Надіслала корисну інформацію в особисті."
        )
    except Exception:
        bot_info = await context.bot.get_me()
        url = f"https://t.me/{bot_info.username}?start=cipainfo"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🐔 Відкрити інформацію в приваті",
                url=url,
            )
        ]])
        await message.reply_text(
            "🐔 Щоб показати інформацію в приваті, спочатку відкрий діалог із ботом.",
            reply_markup=keyboard,
        )

async def send_cipainfo_menu(bot, chat_id):
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🐔 Корисна інформація Ціпаріуму\n\n"
            "Що саме хочеш переглянути?"
        ),
        reply_markup=cipainfo_menu_markup(),
    )


async def cipainfo_callback(update, context):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    if query.data == CIPAINFO_ADD_FRESH_CALLBACK:
        context.user_data.pop("cipainfo_add_section", None)
        context.user_data.pop("cipainfo_add_section_name", None)
        await query.edit_message_text(
            "➕ Що хочеш додати свіженького?",
            reply_markup=cipainfo_add_fresh_markup(),
        )
        return

    if query.data in {
        CIPAINFO_ADD_YOUTUBE_CALLBACK,
        CIPAINFO_ADD_THREADS_CALLBACK,
        CIPAINFO_ADD_DESIGNERS_CALLBACK,
    }:
        section_names = {
            CIPAINFO_ADD_YOUTUBE_CALLBACK: "YouTube-канали",
            CIPAINFO_ADD_THREADS_CALLBACK: "тематичні гілки",
            CIPAINFO_ADD_DESIGNERS_CALLBACK: "ціпи-дизайнери",
        }

        context.user_data["cipainfo_add_section"] = (
            CIPAINFO_ADD_SECTION_KEYS[query.data]
        )
        context.user_data["cipainfo_add_section_name"] = (
            section_names[query.data]
        )

        await query.edit_message_text(
            "➕ Напишіть, що саме ви хочете додати, "
            "у такому ж стилі, як уже наявна інформація "
            f"в розділі «{section_names[query.data]}».\n\n"
            "Будь ласка, вкажіть назву або ім’я, "
            "а також посилання. Якщо потрібно — додайте "
            "короткий опис. Один новий запис краще надсилати "
            "одним повідомленням.",
            reply_markup=cipainfo_add_back_markup(),
        )
        return


    if query.data == CIPAINFO_MENU_CALLBACK:
        context.user_data.pop("cipainfo_add_section", None)
        context.user_data.pop("cipainfo_add_section_name", None)
        await query.edit_message_text(
            "🐔 Корисна інформація Ціпаріуму\n\nЩо саме хочеш переглянути?",
            reply_markup=cipainfo_menu_markup(),
        )
        return

    mapping = {
        CIPAINFO_WISHLIST_CALLBACK: "cipainfo_wishlist",
        CIPAINFO_YOUTUBE_CALLBACK: "cipainfo_youtube",
        CIPAINFO_THREADS_CALLBACK: "cipainfo_threads",
        CIPAINFO_RULES_CALLBACK: "ciparules",
        CIPAINFO_DESIGNERS_CALLBACK: "cipainfo_designers",
    }
    key = mapping.get(query.data)
    if not key:
        return

    content = get_static_content(key) or "🐔 Цей розділ поки порожній."

    if key == "ciparules" and len(content) > 3900:
        await query.edit_message_text(
            "📜 Правила чату"
        )
        await send_long_message(
            query.message,
            content,
        )
        await query.message.reply_text(
            "⬅️ Повернутися до меню:",
            reply_markup=cipainfo_back_markup(),
        )
        return

    await query.edit_message_text(
        content,
        reply_markup=cipainfo_back_markup(),
    )


async def cipainfo_add_message(update, context):
    pending_section = context.user_data.get(
        "cipainfo_add_section"
    )

    if not pending_section:
        return

    message = update.effective_message
    submitted_text = (
        message.text
        if message
        else None
    )

    try:
        if not submitted_text or not submitted_text.strip():
            await message.reply_text(
                "🐔 Тут поки нічого додавати. "
                "Надішли текст нового запису одним повідомленням."
            )
            return

        if not re.search(
            r"https?://\S+",
            submitted_text,
            flags=re.IGNORECASE,
        ):
            await message.reply_text(
                "🐔 Не бачу посилання в цьому записі.\n\n"
                "Додай, будь ласка, назву або ім’я та "
                "повне посилання, що починається з "
                "http:// або https://."
            )
            return

        section_name = context.user_data.get(
            "cipainfo_add_section_name",
            pending_section,
        )

        append_static_content(
            pending_section,
            submitted_text.strip(),
        )

        user = update.effective_user
        logger.info(
            "CIPAINFO ADD SUCCESS | section=%s | "
            "user_id=%s | username=%s | text=%r",
            pending_section,
            getattr(user, "id", None),
            getattr(user, "username", None),
            submitted_text.strip(),
        )

        context.user_data.pop(
            "cipainfo_add_section",
            None,
        )
        context.user_data.pop(
            "cipainfo_add_section_name",
            None,
        )

        await message.reply_text(
            "🐔 Свіженьке додано!\n\n"
            f"Розділ: «{section_name}».",
            reply_markup=cipainfo_menu_markup(),
        )

    except (BadRequest, Forbidden, TelegramError, ValueError):
        await handle_cipainfo_add_error(
            update,
            section=pending_section,
            submitted_text=submitted_text,
        )
