import base64
import json
import random
import re

from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

from config import (
    client,
    OPENAI_MODEL,
    OPENAI_IMAGE_MODEL,
    OPENAI_IMAGE_SIZE,
    OPENAI_IMAGE_QUALITY,
    MAX_MESSAGES,
)
from commands import (
    human_log_time,
    is_chat_admin,
    send_long_message,
)
from db import (
    get_messages_for_period,
    get_top_chickens,
    get_active_chat_ids,
    save_daily_cipa_visuals,
    get_latest_daily_cipa_visuals,
)
from reports import format_messages_for_ai


def format_chicken_name(chicken):
    if chicken["username"]:
        return f"@{chicken['username']}"

    if chicken["display_name"]:
        return chicken["display_name"]

    return "невідома ціпочка"


def format_chicken_names_for_caption(
    chickens,
):
    names = [
        format_chicken_name(chicken)
        for chicken in chickens
    ]

    if not names:
        return None

    if len(names) == 1:
        return names[0]

    if len(names) == 2:
        return (
            f"{names[0]} та {names[1]}"
        )

    return (
        f"{names[0]}, "
        f"{names[1]} та "
        f"{names[2]}"
    )


async def build_daily_image_prompt(
    messages,
):
    conversation = format_messages_for_ai(
        messages
    )

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
- головний і центральний персонаж ілюстрації — курка;
- курка завжди має бути найбільш помітним персонажем композиції;
- поруч із куркою обов'язково має бути невеличкий милий привид;
- привид є постійним другорядним персонажем Daily Cipa і не повинен
  перетягувати увагу з курки;
- стиль: кольоровий скетч, живий, виразний, милий, з легким гумором;
- курка і маленький привид знаходяться в одному цілісному середовищі;
- навколо них розташований антураж із предметів, символів, їжі,
  деталей і невеликих сценок, пов'язаних із тим, про що говорили
  в чаті за останні 24 години;
- обирай приблизно 4-8 найхарактерніших або найважливіших тем;
- перетворюй теми розмови на конкретні візуальні об'єкти,
  а не на абстрактні написи;
- не малюй реалістичних портретів учасників чату;
- не додавай читабельного тексту, написів, логотипів або підписів;
- композиція має виглядати як одна сцена, а не як колаж або сітка;
- курка і привид мають природно взаємодіяти з навколишніми предметами;
- фон і атмосфера можуть змінюватись залежно від тем чату,
  але курка та маленький привид повинні бути присутні завжди.

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
            "======================================================"
        )
        print("")

    raw = response.output_text.strip()

    if raw.startswith("```"):
        raw = re.sub(
            r"^```(?:json)?\s*",
            "",
            raw,
        )
        raw = re.sub(
            r"\s*```$",
            "",
            raw,
        )

    data = json.loads(raw)

    visual_prompt = str(
        data.get(
            "prompt",
            "",
        )
    ).strip()

    elements = data.get(
        "elements",
        [],
    )

    if not visual_prompt:
        raise ValueError(
            "Daily Cipa visual prompt is empty"
        )

    clean_elements = []

    if isinstance(
        elements,
        list,
    ):
        for item in elements:
            if not isinstance(
                item,
                dict,
            ):
                continue

            element = str(
                item.get(
                    "element",
                    "",
                )
            ).strip()

            reason = str(
                item.get(
                    "reason",
                    "",
                )
            ).strip()

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
        print(
            f"• {item['element']} — "
            f"{item['reason']}"
        )

    print(
        "=============================================="
    )
    print("")

    return (
        visual_prompt,
        clean_elements,
    )


async def generate_daily_chicken_image(
    messages,
):
    (
        visual_prompt,
        elements,
    ) = await build_daily_image_prompt(
        messages
    )

    final_prompt = (
        "Створи цілісну ілюстрацію у стилі кольорового скетчу. "
        "У центрі композиції обов'язково має бути виразна симпатична курка — "
        "це головний персонаж і найбільш помітний об'єкт сцени. "
        "Поруч із нею обов'язково намалюй маленького милого привида "
        "як постійного другорядного персонажа. "
        "Курка і привид мають бути оточені предметами та невеликими сценками, "
        "що відображають теми розмов у чаті за останні 24 години. "
        "Усі елементи повинні утворювати одну природну сцену, а не колаж. "
        "Не додавай текст у зображення.\n\n"
        f"{visual_prompt}"
    )

    result = await client.images.generate(
        model=OPENAI_IMAGE_MODEL,
        prompt=final_prompt,
        size=OPENAI_IMAGE_SIZE,
        quality=OPENAI_IMAGE_QUALITY,
    )

    image_base64 = (
        result.data[0].b64_json
    )
    image_bytes = base64.b64decode(
        image_base64
    )

    image_file = BytesIO(
        image_bytes
    )
    image_file.name = (
        "ciparium_daily_chicken.png"
    )
    image_file.seek(0)

    return (
        image_file,
        visual_prompt,
        elements,
    )


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

    for (
        index,
        chicken,
    ) in enumerate(
        top_chickens,
        start=1,
    ):
        print(
            f"{index}. "
            f"{format_chicken_name(chicken)} — "
            f"{chicken['message_count']} повідомлень"
        )

    print(
        "============================================================"
    )
    print("")

    shuffled_chickens = (
        top_chickens.copy()
    )
    random.shuffle(
        shuffled_chickens
    )

    chicken_names = (
        format_chicken_names_for_caption(
            shuffled_chickens
        )
    )

    (
        image_file,
        visual_prompt,
        elements,
    ) = await generate_daily_chicken_image(
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
        f"Daily Ciparium post sent "
        f"to chat {chat_id}"
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
                f"for chat {chat_id}: "
                f"{repr(e)}"
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
            f"for chat {message.chat_id}: "
            f"{repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося перевірити "
            "права адміністратора."
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
                "🐔 За останні 24 години "
                "недостатньо повідомлень "
                "для Daily Cipa."
            )

    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"/dailycipa error "
            f"for chat {message.chat_id}: "
            f"{repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося згенерувати "
            "Daily Cipa."
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
            f"for chat {message.chat_id}: "
            f"{repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося перевірити "
            "права адміністратора."
        )
        return

    if not admin:
        await message.reply_text(
            "🐔 Команда /dailycipawhy "
            "доступна тільки "
            "адміністраторам чату."
        )
        return

    data = (
        get_latest_daily_cipa_visuals(
            message.chat_id
        )
    )

    if not data:
        await message.reply_text(
            "🐔 Ще немає збереженого "
            "пояснення для Daily Cipa."
        )
        return

    elements = data["elements"]

    if not elements:
        await message.reply_text(
            "🐔 Для останньої Daily Cipa "
            "список візуальних елементів "
            "не збережено."
        )
        return

    lines = [
        "🐔 Чому Daily Cipa "
        "виглядає саме так:",
        "",
    ]

    for item in elements:
        lines.append(
            f"• {item['element']} — "
            f"{item['reason']}"
        )

    await send_long_message(
        message,
        "\n".join(lines),
    )
