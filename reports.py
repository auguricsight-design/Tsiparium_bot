from telegram import Update
from telegram.ext import ContextTypes

from config import (
    client,
    OPENAI_MODEL,
    MAX_MESSAGES,
    MAX_HOURS,
    MAX_REPORTS_PER_DAY,
)
from commands import (
    human_log_time,
    send_long_message,
)
from db import (
    get_messages_for_period,
    get_messages_by_username,
    get_daily_report_count,
    increment_daily_report_count,
)


def format_messages_for_ai(messages):
    result = []

    for msg in messages:
        username = msg["username"]
        display_name = (
            msg["display_name"]
            or "Без імені"
        )

        author = (
            f"@{username}"
            if username
            else display_name
        )

        line = (
            f'[id={msg["message_id"]}] '
            f'[author="{author}"] '
            f'[display_name="{display_name}"]'
        )

        if msg["reply_to_message_id"]:
            line += (
                f' [reply_to='
                f'{msg["reply_to_message_id"]}]'
            )

        line += f"\n{msg['text']}"
        result.append(line)

    return "\n\n".join(result)


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

Якщо username немає, можна використовувати display name.

Не вигадуй username.
Не треба згадувати автора в кожній темі.
"""


SHORT_PROMPT = COMMON_RULES + """

СТИЛЬ:

Створи короткий тезисний список основних тем.

Один пункт = одна тема.
Кожен пункт — приблизно 1-2 короткі речення.

Не створюй заголовок.
Не вказуй період.
Не вказуй кількість повідомлень.

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
"""


CIPA_PROMPT = """
Ти аналізуєш повідомлення однієї конкретної ціпочки
в Telegram-чаті за останні 24 години.

Завдання:
- коротко підсумуй, про що саме писала ця ціпочка;
- згрупуй повідомлення за темами;
- не переказуй кожне повідомлення окремо;
- ігноруй короткі реакції, привітання, окремі емодзі,
  "так", "ні", "+", "ага", "ок" та інші репліки без
  самостійного змісту;
- не вигадуй фактів;
- якщо одна тема повторювалась, об'єднай її;
- не роби психологічних висновків про людину;
- не оцінюй особистість ціпочки;
- описуй лише зміст її повідомлень.

Формат:
• Тема — короткий підсумок у 1-2 реченнях.

Не створюй заголовок.
Не вказуй кількість повідомлень.
Не вказуй період.
"""


async def create_ai_summary(
    messages,
    detailed=False,
):
    conversation = format_messages_for_ai(
        messages
    )

    instructions = (
        DETAILED_PROMPT
        if detailed
        else SHORT_PROMPT
    )

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
            f"===== OPENAI TOKEN USAGE | "
            f"{human_log_time()} ====="
        )
        print(
            f"Input tokens:  "
            f"{response.usage.input_tokens}"
        )
        print(
            f"Output tokens: "
            f"{response.usage.output_tokens}"
        )
        print(
            f"Total tokens:  "
            f"{response.usage.total_tokens}"
        )
        print(
            "=========================================="
        )
        print("")

    return response.output_text.strip()


async def create_cipa_summary(
    messages,
):
    conversation = format_messages_for_ai(
        messages
    )

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=(
            CIPA_PROMPT
            + "\n\n"
            + "ПОВІДОМЛЕННЯ ЦІПОЧКИ:\n\n"
            + conversation
        ),
    )

    return response.output_text.strip()


def parse_zvit_args(args):
    hours = 24
    message_limit = None
    detailed = False

    for arg in args:
        arg = arg.lower().strip()

        if arg in (
            "detailed",
            "detail",
            "full",
        ):
            detailed = True
            continue

        if arg in (
            "24h",
            "1d",
        ):
            hours = 24
            continue

        if arg in (
            "2d",
            "48h",
        ):
            hours = 48
            continue

        if arg in (
            "3d",
            "72h",
        ):
            hours = 72
            continue

        if arg in (
            "4d",
            "96h",
        ):
            hours = 96
            continue

        if arg in (
            "5d",
            "120h",
        ):
            hours = 120
            continue

        if arg.isdigit():
            count = int(arg)

            if count < 1:
                raise ValueError(
                    "Message count must be positive"
                )

            if count > MAX_MESSAGES:
                raise ValueError(
                    "Too many messages"
                )

            message_limit = count
            hours = MAX_HOURS
            continue

        raise ValueError(
            f"Unknown argument: {arg}"
        )

    return (
        hours,
        message_limit,
        detailed,
    )


def get_period_text(hours):
    if hours == 24:
        return "останні 24 години"
    if hours == 48:
        return "останні 2 дні"
    if hours == 72:
        return "останні 3 дні"
    if hours == 96:
        return "останні 4 дні"
    if hours == 120:
        return "останні 5 днів"

    return f"останні {hours} годин"


def build_report_header(
    hours,
    message_count,
    requested_message_limit=None,
):
    if requested_message_limit is not None:
        period_text = (
            f"останні "
            f"{requested_message_limit} повідомлень "
            f"(не старіше 5 днів)"
        )
    else:
        period_text = get_period_text(
            hours
        )

    return (
        "🐔 Сводки Ципаріума\n"
        f"Період: {period_text}\n"
        f"Опрацьовано: "
        f"{message_count} повідомлень\n\n"
    )


async def zvit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    current_count = (
        get_daily_report_count(
            message.chat_id
        )
    )

    if current_count >= MAX_REPORTS_PER_DAY:
        await message.reply_text(
            "🐔 На сьогодні ліміт "
            "Сводок Ципаріума вичерпано.\n\n"
            "Максимум — 10 звітів на добу."
        )
        return

    # /zvit cipa @nickname
    if (
        context.args
        and context.args[0].lower() == "cipa"
    ):
        if len(context.args) < 2:
            await message.reply_text(
                "🐔 Формат команди:\n"
                "/zvit cipa @nickname"
            )
            return

        requested_username = (
            context.args[1].strip()
        )

        if not requested_username.startswith("@"):
            await message.reply_text(
                "🐔 Вкажи нікнейм "
                "у форматі @nickname."
            )
            return

        messages = get_messages_by_username(
            chat_id=message.chat_id,
            username=requested_username,
            hours=24,
        )

        if not messages:
            await message.reply_text(
                f"🐔 За останні 24 години "
                f"не знайшов повідомлень від "
                f"{requested_username}."
            )
            return

        await message.reply_text(
            f"🐣 Ціпаріум аналізує балачки "
            f"{requested_username}..."
        )

        try:
            summary = await create_cipa_summary(
                messages
            )

            increment_daily_report_count(
                message.chat_id
            )

        except Exception as e:
            print(
                f"[{human_log_time()}] "
                f"Cipa report OpenAI error: "
                f"{repr(e)}"
            )

            await message.reply_text(
                "🐔 Не вдалося створити "
                "звіт по ціпочці."
            )
            return

        header = (
            "Сводки Ципаріума\n"
            f"Ціпочка: "
            f"{requested_username}\n"
            "Період: останні 24 години\n\n"
        )

        await send_long_message(
            message,
            header + summary,
        )
        return

    try:
        (
            hours,
            message_limit,
            detailed,
        ) = parse_zvit_args(
            context.args
        )

    except ValueError as e:
        if str(e) == "Too many messages":
            await message.reply_text(
                "🐔 Ціпаріум може обробити "
                "максимум 1000 повідомлень "
                "за один звіт."
            )
            return

        await message.reply_text(
            "Невідомий формат команди.\n\n"
            "Приклади:\n"
            "/zvit\n"
            "/zvit 2d\n"
            "/zvit 3d\n"
            "/zvit 5d\n"
            "/zvit 500\n"
            "/zvit 1000\n"
            "/zvit detailed\n"
            "/zvit 500 detailed\n"
            "/zvit 2d detailed\n"
            "/zvit 3d detailed\n"
            "/zvit 5d detailed\n"
            "/zvit cipa @nickname"
        )
        return

    messages = get_messages_for_period(
        chat_id=message.chat_id,
        hours=hours,
        message_limit=message_limit,
    )

    if not messages:
        await message.reply_text(
            "За цей період немає "
            "повідомлень для створення "
            "Сводок Ципаріума."
        )
        return

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
            "Подивись Railway Logs — "
            "там буде текст помилки OpenAI."
        )
        return

    header = build_report_header(
        hours=hours,
        message_count=len(messages),
        requested_message_limit=message_limit,
    )

    await send_long_message(
        message,
        header + summary,
    )
