import os
import sqlite3
import base64
import random
import json
import re

from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from io import BytesIO

from openai import AsyncOpenAI
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

MAX_MESSAGES = 1000
MAX_HOURS = 72
MAX_REPORTS_PER_DAY = 10

KYIV_TZ = ZoneInfo("Europe/Kyiv")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip()
OPENAI_IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024").strip()
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium").strip()

VOLUME_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()

if VOLUME_PATH:
    DB_PATH = os.path.join(VOLUME_PATH, "ciparium.db")
else:
    DB_PATH = "ciparium.db"

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# =========================================================
# HELPERS
# =========================================================

def human_log_time():
    return datetime.now(KYIV_TZ).strftime("%d.%m.%Y %H:%M:%S")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                display_name TEXT,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reply_to_message_id INTEGER,
                UNIQUE(chat_id, message_id)
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_report_usage (
                chat_id INTEGER NOT NULL,
                report_date TEXT NOT NULL,
                report_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, report_date)
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_cipa_visuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                visual_prompt TEXT NOT NULL,
                elements_json TEXT NOT NULL
            )
            """
        )


def save_message_to_db(
    chat_id,
    message_id,
    user_id,
    username,
    display_name,
    text,
    timestamp,
    reply_to_message_id=None,
):
    with get_db() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO messages (
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id,
            ),
        )



def save_daily_cipa_visuals(chat_id, visual_prompt, elements):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO daily_cipa_visuals (
                chat_id,
                generated_at,
                visual_prompt,
                elements_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                chat_id,
                datetime.now(timezone.utc).isoformat(),
                visual_prompt,
                json.dumps(elements, ensure_ascii=False),
            ),
        )


def get_latest_daily_cipa_visuals(chat_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT generated_at, visual_prompt, elements_json
            FROM daily_cipa_visuals
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()

    if not row:
        return None

    try:
        elements = json.loads(row["elements_json"])
    except Exception:
        elements = []

    return {
        "generated_at": row["generated_at"],
        "visual_prompt": row["visual_prompt"],
        "elements": elements,
    }


# =========================================================
# DAILY REPORT LIMIT
# =========================================================

def get_today_kyiv():
    return datetime.now(KYIV_TZ).date().isoformat()


def get_daily_report_count(chat_id):
    today = get_today_kyiv()

    with get_db() as db:
        row = db.execute(
            """
            SELECT report_count
            FROM daily_report_usage
            WHERE chat_id = ?
              AND report_date = ?
            """,
            (chat_id, today),
        ).fetchone()

    return row["report_count"] if row else 0


def increment_daily_report_count(chat_id):
    today = get_today_kyiv()

    with get_db() as db:
        db.execute(
            """
            INSERT INTO daily_report_usage (
                chat_id,
                report_date,
                report_count
            )
            VALUES (?, ?, 1)
            ON CONFLICT(chat_id, report_date)
            DO UPDATE SET
                report_count = report_count + 1
            """,
            (chat_id, today),
        )


# =========================================================
# MESSAGE COLLECTION
# =========================================================

async def save_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption

    if not text:
        return

    if text.startswith("/"):
        return

    user = message.from_user

    user_id = user.id if user else None
    username = user.username if user else None
    display_name = user.full_name if user else None

    reply_to_message_id = None

    if message.reply_to_message:
        reply_to_message_id = message.reply_to_message.message_id

    save_message_to_db(
        chat_id=message.chat_id,
        message_id=message.message_id,
        user_id=user_id,
        username=username,
        display_name=display_name,
        text=text,
        timestamp=message.date.astimezone(timezone.utc).isoformat(),
        reply_to_message_id=reply_to_message_id,
    )


# =========================================================
# GET MESSAGES
# =========================================================

def get_messages_for_period(
    chat_id,
    hours=24,
    message_limit=None,
):
    hours = min(hours, MAX_HOURS)

    if message_limit is None:
        message_limit = MAX_MESSAGES
    else:
        message_limit = min(max(message_limit, 1), MAX_MESSAGES)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                chat_id,
                message_id,
                user_id,
                username,
                display_name,
                text,
                timestamp,
                reply_to_message_id
            FROM messages
            WHERE chat_id = ?
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (
                chat_id,
                since.isoformat(),
                message_limit,
            ),
        ).fetchall()

    return list(reversed(rows))


# =========================================================
# FORMAT MESSAGES FOR AI
# =========================================================

def format_messages_for_ai(messages):
    result = []

    for msg in messages:
        username = msg["username"]
        display_name = msg["display_name"] or "Без імені"

        author = f"@{username}" if username else display_name

        line = (
            f'[id={msg["message_id"]}] '
            f'[author="{author}"] '
            f'[display_name="{display_name}"]'
        )

        if msg["reply_to_message_id"]:
            line += f' [reply_to={msg["reply_to_message_id"]}]'

        line += f"\n{msg['text']}"
        result.append(line)

    return "\n\n".join(result)


# =========================================================
# AI PROMPTS
# =========================================================

COMMON_RULES = """
Ти аналізуєш історію Telegram-чату.

Твоє завдання — визначити основні реальні змістовні теми,
які обговорювалися в чаті.

ЗВ'ЯЗКИ МІЖ ПОВІДОМЛЕННЯМИ:

Кожне повідомлення має id.

Якщо повідомлення містить:
reply_to=123

це означає, що воно є відповіддю на повідомлення id=123.

Обов'язково використовуй reply-зв'язки для відновлення
контексту розмови.

Reply-ланцюжок може бути однією дискусією.
Не розбивай його автоматично на багато окремих тем.

Одна тема також може мати кілька паралельних reply-гілок.

ПРАВИЛА АНАЛІЗУ:

- об'єднуй повідомлення, що стосуються одного предмета;
- якщо до однієї теми повертались кілька разів,
  об'єднай це в одну тему;
- не вважай кожну репліку окремою темою;
- ігноруй привітання;
- ігноруй реакції;
- ігноруй окремі емодзі;
- ігноруй "так", "ні", "+", "ага", "ок" та схожі
  повідомлення без самостійного змісту;
- ігноруй випадкові короткі жарти, якщо вони не стали
  окремою темою;
- не вигадуй фактів;
- не вигадуй висновків, яких не було в чаті;
- не приписуй людині те, чого вона не писала.

ПРАВИЛА ПРО УЧАСНИКІВ:

Учасника чату називай словом "ціпочка".

Не використовуй щодо учасників слова:
- користувач;
- юзер;
- учасник;
- автор повідомлення.

Якщо є username у форматі @nickname,
при згадуванні використовуй саме @nickname.

Наприклад:
"Ціпочка @forestwitch показала свій урожай грибів."

Якщо username немає, можна використовувати display name:
"Ціпочка Марія..."

Не вигадуй username.

Не треба згадувати автора в кожній темі.
Згадуй ціпочку тільки тоді, коли її внесок важливий
для змісту теми.

Якщо тему обговорювало багато людей,
не потрібно перераховувати всіх.
"""


SHORT_PROMPT = COMMON_RULES + """

СТИЛЬ:

Створи короткий тезисний список основних тем.

Один пункт = одна тема.

Кожен пункт — приблизно 1-2 короткі речення.

Не створюй заголовок.
Не вказуй період.
Не вказуй кількість повідомлень.

Бот додасть це сам.

Формат:

• Перша тема.
• Друга тема.
• Третя тема.
"""


DETAILED_PROMPT = COMMON_RULES + """

СТИЛЬ:

Створи детальний, але компактний звіт.

Для кожної основної теми:

1. Дай коротку назву.
2. У 2-4 реченнях поясни, про що йшла розмова.
3. Збережи важливі конкретні деталі.
4. Якщо був конкретний результат або висновок,
   коротко його зазнач.
5. Якщо авторство важливе,
   використовуй формат "ціпочка @nickname".

Не переказуй повідомлення одне за одним.

Не створюй заголовок всього звіту.
Не вказуй період.
Не вказуй кількість повідомлень.

Формат:

1. Назва теми
   Короткий опис.

2. Назва теми
   Короткий опис.
"""


# =========================================================
# OPENAI SUMMARY
# =========================================================

async def create_ai_summary(
    messages,
    detailed=False,
):
    conversation = format_messages_for_ai(messages)

    instructions = DETAILED_PROMPT if detailed else SHORT_PROMPT

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=(
            instructions
            + "\n\n"
            + "ІСТОРІЯ ЧАТУ:\n\n"
            + conversation
        ),
    )

    if response.usage:
        print("")
        print(
            f"===== OPENAI TOKEN USAGE | "
            f"{human_log_time()} ====="
        )
        print(f"Input tokens:  {response.usage.input_tokens}")
        print(f"Output tokens: {response.usage.output_tokens}")
        print(f"Total tokens:  {response.usage.total_tokens}")
        print("==========================================")
        print("")

    return response.output_text.strip()


# =========================================================
# /zvit ARGUMENT PARSER
# =========================================================

def parse_zvit_args(args):
    hours = 24
    message_limit = None
    detailed = False

    for arg in args:
        arg = arg.lower().strip()

        if arg in ("detailed", "detail", "full"):
            detailed = True
            continue

        if arg in ("24h", "1d"):
            hours = 24
            continue

        if arg in ("2d", "48h"):
            hours = 48
            continue

        if arg in ("3d", "72h"):
            hours = 72
            continue

        if arg.isdigit():
            count = int(arg)

            if count < 1:
                raise ValueError("Message count must be positive")

            if count > MAX_MESSAGES:
                raise ValueError("Too many messages")

            message_limit = count
            hours = MAX_HOURS
            continue

        raise ValueError(f"Unknown argument: {arg}")

    return hours, message_limit, detailed


# =========================================================
# REPORT HEADER
# =========================================================

def get_period_text(hours):
    if hours == 24:
        return "останні 24 години"
    if hours == 48:
        return "останні 2 дні"
    if hours == 72:
        return "останні 3 дні"
    return f"останні {hours} годин"


def build_report_header(
    hours,
    message_count,
    requested_message_limit=None,
):
    if requested_message_limit is not None:
        period_text = (
            f"останні {requested_message_limit} повідомлень "
            f"(не старіше 3 днів)"
        )
    else:
        period_text = get_period_text(hours)

    return (
        "🐔 Сводки Ципаріума\n"
        f"Період: {period_text}\n"
        f"Опрацьовано: {message_count} повідомлень\n\n"
    )


# =========================================================
# TELEGRAM LONG MESSAGE
# =========================================================

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
        candidate = current + ("\n\n" if current else "") + paragraph

        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)

            while len(paragraph) > max_length:
                chunks.append(paragraph[:max_length])
                paragraph = paragraph[max_length:]

            current = paragraph

    if current:
        chunks.append(current)

    for chunk in chunks:
        await telegram_message.reply_text(chunk)


# =========================================================
# DAILY TOP CHICKENS
# =========================================================

def get_top_chickens(chat_id, limit=3):
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    with get_db() as db:
        rows = db.execute(
            """
            SELECT
                user_id,
                username,
                display_name,
                COUNT(*) AS message_count
            FROM messages
            WHERE chat_id = ?
              AND timestamp >= ?
              AND user_id IS NOT NULL
            GROUP BY
                user_id,
                username,
                display_name
            ORDER BY
                message_count DESC
            LIMIT ?
            """,
            (
                chat_id,
                since.isoformat(),
                limit,
            ),
        ).fetchall()

    return list(rows)


def get_active_chat_ids():
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT chat_id
            FROM messages
            WHERE timestamp >= ?
            """,
            (since.isoformat(),),
        ).fetchall()

    return [row["chat_id"] for row in rows]


def format_chicken_name(chicken):
    if chicken["username"]:
        return f"@{chicken['username']}"

    if chicken["display_name"]:
        return chicken["display_name"]

    return "невідома ціпочка"


def format_chicken_names_for_caption(chickens):
    names = [
        format_chicken_name(chicken)
        for chicken in chickens
    ]

    if not names:
        return None

    if len(names) == 1:
        return names[0]

    if len(names) == 2:
        return f"{names[0]} та {names[1]}"

    return f"{names[0]}, {names[1]} та {names[2]}"


# =========================================================
# DAILY CHICKEN IMAGE
# =========================================================

async def build_daily_image_prompt(messages):
    conversation = format_messages_for_ai(messages)

    instructions = """
Ти готуєш дані для генерації Daily Cipa — ілюстрації за мотивами
Telegram-чату за останні 24 години.

Поверни ВАЛІДНИЙ JSON без markdown у форматі:

{
  "prompt": "готовий prompt для генератора зображень",
  "elements": [
    {
      "element": "коротка назва візуального елемента",
      "reason": "яка тема чату стала причиною його додавання"
    }
  ]
}

Вимоги до prompt:
- головний персонаж: курка;
- стиль: кольоровий скетч, живий, виразний, милий, з легким гумором;
- 4-8 ключових тем чату мають бути представлені предметами,
  символами або дрібними сценками;
- не малюй реалістичних портретів;
- не додавай читабельного тексту;
- композиція цілісна, не сітка і не колаж.

Вимоги до elements:
- включай лише ключові елементи, які свідомо закладаєш у prompt;
- для кожного коротко поясни, з якої теми чату він походить;
- не вигадуй тем;
- не включай саму курку, якщо курка не була темою чату.
"""

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=(
            instructions
            + "\n\nІСТОРІЯ ЧАТУ:\n\n"
            + conversation
        ),
    )

    if response.usage:
        print("")
        print(
            f"===== DAILY IMAGE PROMPT TOKEN USAGE | "
            f"{human_log_time()} ====="
        )
        print(f"Input tokens:  {response.usage.input_tokens}")
        print(f"Output tokens: {response.usage.output_tokens}")
        print(f"Total tokens:  {response.usage.total_tokens}")
        print("======================================================")
        print("")

    raw = response.output_text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)

    visual_prompt = str(data.get("prompt", "")).strip()
    elements = data.get("elements", [])

    if not visual_prompt:
        raise ValueError("Daily Cipa visual prompt is empty")

    clean_elements = []

    if isinstance(elements, list):
        for item in elements:
            if not isinstance(item, dict):
                continue

            element = str(item.get("element", "")).strip()
            reason = str(item.get("reason", "")).strip()

            if element and reason:
                clean_elements.append(
                    {
                        "element": element,
                        "reason": reason,
                    }
                )

    print("")
    print(
        f"===== DAILY CIPA VISUAL ELEMENTS | "
        f"{human_log_time()} ====="
    )

    for item in clean_elements:
        print(f"• {item['element']} — {item['reason']}")

    print("==============================================")
    print("")

    return visual_prompt, clean_elements


async def generate_daily_chicken_image(messages):
    visual_prompt, elements = await build_daily_image_prompt(
        messages
    )

    final_prompt = (
        "Створи ілюстрацію у стилі кольорового скетчу. "
        "Головний персонаж — виразна симпатична курка. "
        "Курка має бути оточена об'єктами та дрібними візуальними сценками, "
        "що відображають теми чату за останні 24 години. "
        "Не додавай текст у зображення.\n\n"
        f"{visual_prompt}"
    )

    result = await client.images.generate(
        model=OPENAI_IMAGE_MODEL,
        prompt=final_prompt,
        size=OPENAI_IMAGE_SIZE,
        quality=OPENAI_IMAGE_QUALITY,
    )

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    image_file = BytesIO(image_bytes)
    image_file.name = "ciparium_daily_chicken.png"
    image_file.seek(0)

    return image_file, visual_prompt, elements


# =========================================================
# DAILY CIPA CORE
# =========================================================

async def send_daily_cipa(
    chat_id,
    context: ContextTypes.DEFAULT_TYPE,
):
    messages = get_messages_for_period(
        chat_id=chat_id,
        hours=24,
        message_limit=MAX_MESSAGES,
    )

    if not messages:
        return False

    top_chickens = get_top_chickens(
        chat_id=chat_id,
        limit=3,
    )

    if not top_chickens:
        return False

    print("")
    print(
        f"===== DAILY TOP CHICKENS | "
        f"{human_log_time()} | "
        f"CHAT {chat_id} ====="
    )

    for index, chicken in enumerate(
        top_chickens,
        start=1,
    ):
        print(
            f"{index}. "
            f"{format_chicken_name(chicken)} — "
            f"{chicken['message_count']} повідомлень"
        )

    print("============================================================")
    print("")

    shuffled_chickens = top_chickens.copy()
    random.shuffle(shuffled_chickens)

    chicken_names = format_chicken_names_for_caption(
        shuffled_chickens
    )

    image_file, visual_prompt, elements = await generate_daily_chicken_image(
        messages
    )

    caption = (
        "🐔 Ціпаріум сьогодні виглядає так, "
        "а кіпішу наводили "
        f"{chicken_names}\n\n"
        "#dailycipa"
    )

    await context.bot.send_photo(
        chat_id=chat_id,
        photo=image_file,
        caption=caption,
    )

    save_daily_cipa_visuals(
        chat_id=chat_id,
        visual_prompt=visual_prompt,
        elements=elements,
    )

    print(
        f"[{human_log_time()}] "
        f"Daily Ciparium post sent to chat {chat_id}"
    )

    return True


async def daily_chicken_image_job(
    context: ContextTypes.DEFAULT_TYPE,
):
    for chat_id in get_active_chat_ids():
        try:
            await send_daily_cipa(
                chat_id=chat_id,
                context=context,
            )

        except Exception as e:
            print(
                f"[{human_log_time()}] "
                f"Daily Ciparium error "
                f"for chat {chat_id}: {repr(e)}"
            )


# =========================================================
# ADMIN CHECK + /dailycipa
# =========================================================

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


async def dailycipa(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    try:
        admin = await is_chat_admin(
            chat_id=message.chat_id,
            user_id=user.id,
            context=context,
        )

    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"Admin check error "
            f"for chat {message.chat_id}: {repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося перевірити права адміністратора."
        )
        return

    if not admin:
        await message.reply_text(
            "🐔 Команда /dailycipa доступна "
            "тільки адміністраторам чату."
        )
        return

    try:
        sent = await send_daily_cipa(
            chat_id=message.chat_id,
            context=context,
        )

        if not sent:
            await message.reply_text(
                "🐔 За останні 24 години недостатньо "
                "повідомлень для Daily Cipa."
            )

    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"/dailycipa error "
            f"for chat {message.chat_id}: {repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося згенерувати Daily Cipa."
        )


async def dailycipawhy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    try:
        admin = await is_chat_admin(
            chat_id=message.chat_id,
            user_id=user.id,
            context=context,
        )
    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"Admin check error "
            f"for chat {message.chat_id}: {repr(e)}"
        )
        await message.reply_text(
            "🐔 Не вдалося перевірити права адміністратора."
        )
        return

    if not admin:
        await message.reply_text(
            "🐔 Команда /dailycipawhy доступна "
            "тільки адміністраторам чату."
        )
        return

    data = get_latest_daily_cipa_visuals(
        message.chat_id
    )

    if not data:
        await message.reply_text(
            "🐔 Ще немає збереженого пояснення "
            "для Daily Cipa."
        )
        return

    elements = data["elements"]

    if not elements:
        await message.reply_text(
            "🐔 Для останньої Daily Cipa "
            "список візуальних елементів не збережено."
        )
        return

    lines = [
        "🐔 Чому Daily Cipa виглядає саме так:",
        "",
    ]

    for item in elements:
        lines.append(
            f"• {item['element']} — {item['reason']}"
        )

    await send_long_message(
        message,
        "\n".join(lines),
    )


# =========================================================
# /zvit COMMAND
# =========================================================

async def zvit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    current_count = get_daily_report_count(message.chat_id)

    if current_count >= MAX_REPORTS_PER_DAY:
        await message.reply_text(
            "🐔 На сьогодні ліміт Сводок Ципаріума "
            "вичерпано.\n\n"
            "Максимум — 10 звітів на добу."
        )
        return

    try:
        hours, message_limit, detailed = parse_zvit_args(
            context.args
        )

    except ValueError as e:
        if str(e) == "Too many messages":
            await message.reply_text(
                "🐔 Ціпаріум може обробити максимум "
                "1000 повідомлень за один звіт."
            )
            return

        await message.reply_text(
            "Невідомий формат команди.\n\n"
            "Приклади:\n"
            "/zvit\n"
            "/zvit 2d\n"
            "/zvit 3d\n"
            "/zvit 500\n"
            "/zvit 1000\n"
            "/zvit detailed\n"
            "/zvit 500 detailed\n"
            "/zvit 2d detailed\n"
            "/zvit 3d detailed"
        )
        return

    messages = get_messages_for_period(
        chat_id=message.chat_id,
        hours=hours,
        message_limit=message_limit,
    )

    if not messages:
        await message.reply_text(
            "За цей період немає повідомлень "
            "для створення Сводок Ципаріума."
        )
        return

    message_count = len(messages)

    await message.reply_text(
        "🐣 Ціпаріум аналізує балачки..."
    )

    try:
        summary = await create_ai_summary(
            messages=messages,
            detailed=detailed,
        )

        increment_daily_report_count(
            message.chat_id
        )

    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"OpenAI error: {repr(e)}"
        )

        await message.reply_text(
            "Не вдалося створити "
            "Сводки Ципаріума.\n\n"
            "Подивись Railway Logs — там буде "
            "текст помилки OpenAI."
        )
        return

    header = build_report_header(
        hours=hours,
        message_count=message_count,
        requested_message_limit=message_limit,
    )

    result = header + summary

    await send_long_message(
        message,
        result,
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context,
):
    print(
        f"[{human_log_time()}] "
        f"Telegram error: {repr(context.error)}"
    )


# =========================================================
# MAIN
# =========================================================

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
        f"Image quality: {OPENAI_IMAGE_QUALITY}"
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
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
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
        daily_chicken_image_job,
        time=time(
            hour=23,
            minute=0,
            tzinfo=KYIV_TZ,
        ),
        name="daily_chicken_image_job",
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
