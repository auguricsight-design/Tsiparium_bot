import base64
import json
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
    PORTRAIT_COOLDOWN_DAYS,
    KYIV_TZ,
)
from commands import (
    human_log_time,
    send_long_message,
)

from datetime import datetime, timedelta

from messages_db import get_messages_by_username
from visuals_db import (
    save_cipa_portrait_visuals,
    get_latest_cipa_portrait_visuals,
    get_recent_cipa_portrait_cooldown,
)
from reports import format_messages_for_ai



def format_portrait_cooldown_time(generated_at):
    dt = datetime.fromisoformat(
        generated_at
    )
    next_allowed = (
        dt
        + timedelta(
            days=PORTRAIT_COOLDOWN_DAYS
        )
    ).astimezone(
        KYIV_TZ
    )
    return next_allowed.strftime(
        "%d.%m.%Y %H:%M"
    )


async def build_cipa_portrait_prompt(
    messages,
    requested_username,
):
    conversation = format_messages_for_ai(
        messages
    )

    instructions = f"""
Ти готуєш дані для персонального Cipa Portrait
за повідомленнями однієї конкретної ціпочки {requested_username}
за останні 5 днів.

Поверни ВАЛІДНИЙ JSON без markdown і без додаткового тексту:

{{
  "prompt": "готовий prompt для генератора зображень",
  "elements": [
    {{
      "element": "коротка назва візуального елемента",
      "reason": "яка тема або повідомлення цієї ціпочки стало причиною його додавання"
    }}
  ]
}}

Завдання:
- проаналізуй ТІЛЬКИ повідомлення цієї ціпочки;
- визнач 4-8 найхарактерніших тем, предметів, занять, покупок,
  їжі, місць, хобі, подій або речей, про які вона писала;
- перетвори ці теми на конкретні візуальні об'єкти та деталі сцени;
- не роби психологічних висновків про людину;
- не вигадуй інтересів, яких у повідомленнях не було;
- не використовуй реалістичний портрет людини.

Вимоги до картинки:
- центральний і найбільш помітний персонаж — симпатична курочка;
- курочка є умовним художнім образом цієї ціпочки;
- навколо курочки розташовані предмети та невеликі сценки,
  що відображають теми її повідомлень за останні 5 днів;
- композиція має бути цілісною, як одна сцена, а не колаж;
- стиль: кольоровий скетч, живий, виразний, милий, з легким гумором;
- без читабельного тексту, написів, логотипів і підписів;
- не додавай маленького привида автоматично: це не Daily Cipa;
- курочка повинна залишатися головним фокусом композиції.

Вимоги до elements:
- включай лише ключові змістовні елементи, які свідомо закладаєш у prompt;
- для кожного елемента коротко поясни, з якої теми повідомлень він походить;
- не вигадуй причин або тем, яких у повідомленнях не було;
- саму курочку не включай як окремий елемент, якщо кури не були темою повідомлень.
"""

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=(
            instructions
            + "\n\n"
            + "ПОВІДОМЛЕННЯ ЦІПОЧКИ:\n\n"
            + conversation
        ),
    )

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
            "Cipa Portrait visual prompt is empty"
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
        f"===== CIPA PORTRAIT VISUAL ELEMENTS | "
        f"{human_log_time()} | "
        f"{requested_username} ====="
    )

    for item in clean_elements:
        print(
            f"• {item['element']} — "
            f"{item['reason']}"
        )

    print(
        "===================================================="
    )
    print("")

    return (
        visual_prompt,
        clean_elements,
    )


async def generate_cipa_portrait(
    messages,
    requested_username,
):
    (
        visual_prompt,
        elements,
    ) = await build_cipa_portrait_prompt(
        messages=messages,
        requested_username=requested_username,
    )

    final_prompt = (
        "Створи цілісну ілюстрацію у стилі кольорового скетчу. "
        "У центрі композиції — симпатична виразна курочка, "
        "яка є головним і найбільш помітним персонажем. "
        "Навколо неї розмісти предмети та невеликі сценки, "
        "що відображають теми повідомлень конкретної ціпочки "
        "за останні 5 днів. "
        "Не малюй людину або реалістичний портрет. "
        "Не додавай текст у зображення. "
        "Композиція має бути однією природною сценою, а не колажем.\n\n"
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
        "cipa_portrait.png"
    )
    image_file.seek(0)

    return (
        image_file,
        visual_prompt,
        elements,
    )


async def portrait(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    if (
        len(context.args) < 2
        or context.args[0].lower() != "cipa"
    ):
        await message.reply_text(
            "🐔 Формат команди:\n"
            "/portrait cipa @nickname"
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

    recent_portrait_generated_at = (
        get_recent_cipa_portrait_cooldown(
            chat_id=message.chat_id,
            username=requested_username,
        )
    )

    if recent_portrait_generated_at:
        next_available = format_portrait_cooldown_time(
            recent_portrait_generated_at
        )
        await message.reply_text(
            "🐔 Портрет для цієї ціпулі вже "
            "генерували протягом останніх "
            f"{PORTRAIT_COOLDOWN_DAYS} днів.\n\n"
            "Спробуйте знову після: "
            f"{next_available}"
        )
        return

    messages = get_messages_by_username(
        chat_id=message.chat_id,
        username=requested_username,
        hours=120,
    )

    if not messages:
        await message.reply_text(
            f"🐔 За останні 5 днів "
            f"не знайшов повідомлень від "
            f"{requested_username}."
        )
        return

    await message.reply_text(
        f"🐣 Ціпаріум малює портрет "
        f"{requested_username}..."
    )

    try:
        (
            image_file,
            visual_prompt,
            elements,
        ) = await generate_cipa_portrait(
            messages=messages,
            requested_username=requested_username,
        )

        await context.bot.send_photo(
            chat_id=message.chat_id,
            photo=image_file,
            caption=(
                f"🐔 Портрет ціпулі "
                f"{requested_username}"
            ),
        )

        save_cipa_portrait_visuals(
            chat_id=message.chat_id,
            username=requested_username,
            visual_prompt=visual_prompt,
            elements=elements,
        )

        print(
            f"[{human_log_time()}] "
            f"Cipa portrait sent for "
            f"{requested_username} "
            f"in chat {message.chat_id}"
        )

    except Exception as e:
        print(
            f"[{human_log_time()}] "
            f"Cipa portrait error for "
            f"{requested_username} "
            f"in chat {message.chat_id}: "
            f"{repr(e)}"
        )

        await message.reply_text(
            "🐔 Не вдалося згенерувати "
            "Cipa Portrait."
        )


async def lastcipawhy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    data = (
        get_latest_cipa_portrait_visuals(
            message.chat_id
        )
    )

    if not data:
        await message.reply_text(
            "🐔 Ще немає збереженого "
            "пояснення для персонального "
            "портрета."
        )
        return

    elements = data["elements"]
    username = data["username"]

    if not elements:
        await message.reply_text(
            "🐔 Для останнього портрета "
            "список візуальних елементів "
            "не збережено."
        )
        return

    lines = [
        f"🐔 Чому портрет ціпулі "
        f"{username} виглядає саме так:",
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
