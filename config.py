# ────────────────────────────────────────────────────────────
#  Все настройки берутся из файла .env в корне проекта.
#  Никогда не коммить .env в git!
# ────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# PostgreSQL
DB_HOST:     str = os.getenv("DB_HOST",     "localhost")
DB_PORT:     int = int(os.getenv("DB_PORT", "5432"))
DB_NAME:     str = os.getenv("DB_NAME",     "postgres")
DB_USER:     str = os.getenv("DB_USER",     "postgres")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "123")

# Admins — telegram_id через запятую: 123456,789012
ADMIN_IDS: list[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]
