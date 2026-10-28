import os

from zoneinfo import ZoneInfo
from openai import AsyncOpenAI


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

MAX_MESSAGES = 1000
MAX_HOURS = 120
MAX_REPORTS_PER_DAY = 10
MESSAGE_RETENTION_DAYS = 5

KYIV_TZ = ZoneInfo("Europe/Kyiv")

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5-mini",
).strip()

OPENAI_IMAGE_MODEL = os.getenv(
    "OPENAI_IMAGE_MODEL",
    "gpt-image-2",
).strip()

OPENAI_IMAGE_SIZE = os.getenv(
    "OPENAI_IMAGE_SIZE",
    "1024x1024",
).strip()

OPENAI_IMAGE_QUALITY = os.getenv(
    "OPENAI_IMAGE_QUALITY",
    "medium",
).strip()

VOLUME_PATH = os.getenv(
    "RAILWAY_VOLUME_MOUNT_PATH",
    "",
).strip()

if VOLUME_PATH:
    DB_PATH = os.path.join(
        VOLUME_PATH,
        "ciparium.db",
    )
else:
    DB_PATH = "ciparium.db"

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
)
