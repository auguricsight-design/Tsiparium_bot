import os
import sqlite3
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from telegram import Update
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

VOLUME_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()

if VOLUME_PATH:
    DB_PATH = os.path.join(VOLUME_PATH, "ciparium.db")
else:
    DB_PATH = "ciparium.db"

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


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
        print("===== OPENAI TOKEN USAGE =====")
        print(f"Input tokens:  {response.usage.input_tokens}")
        print(f"Output tokens: {response.usage.output_tokens}")
        print(f"Total tokens:  {response.usage.total_tokens}")
        print("==============================")
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
# DAILY TOP CHICKEN
# =========================================================

def get_top_chicken(chat_id):
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    with get_db() as db:
        row = db.execute(
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
            LIMIT 1
            """,
            (
                chat_id,
                since.isoformat(),
            ),
        ).fetchone()

    return row


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


async def daily_top_chicken(
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_ids = get_active_chat_ids()

    for chat_id in chat_ids:
        top = get_top_chicken(chat_id)

        if not top:
            continue

        username = top["username"]
        display_name = top["display_name"]

        if username:
            chicken_name = f"@{username}"
        elif display_name:
            chicken_name = display_name
        else:
            continue

        text = (
            "🐔 Ціпаріум доповідає, що найбільше "
            f"сьогодні квохтала {chicken_name}"
        )

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
            )

            print(
                f"Daily top chicken for {chat_id}: "
                f"{chicken_name} "
                f"({top['message_count']} messages)"
            )

        except Exception as e:
            print(
                f"Daily top chicken error "
                f"for chat {chat_id}: {repr(e)}"
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
        print("OpenAI error:", repr(e))

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
        "Telegram error:",
        repr(context.error),
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

    print(f"Database path: {DB_PATH}")

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

    # Щодня о 23:00 за київським часом.
    app.job_queue.run_daily(
        daily_top_chicken,
        time=time(
            hour=23,
            minute=0,
            tzinfo=KYIV_TZ,
        ),
        name="daily_top_chicken",
    )

    print("Ципаріум запущено 🐔")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
