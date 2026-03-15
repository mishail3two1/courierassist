from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PUBLIC_WEBAPP_URL = os.getenv("PUBLIC_WEBAPP_URL", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise ValueError(
        "Не найден TELEGRAM_BOT_TOKEN. "
        "Добавь новый токен бота в файл .env"
    )

if not PUBLIC_WEBAPP_URL:
    raise ValueError(
        "Не найден PUBLIC_WEBAPP_URL. "
        "Добавь публичный HTTPS URL Mini App в файл .env"
    )