import os


# =========================
# Telegram Bot Configuration
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE_URL = os.getenv("TELEGRAM_BASE_URL", "https://api.telegram.org").strip()


# =========================
# Webhook / Flask Configuration
# =========================
APP_URL = os.getenv("APP_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip()
PORT = int(os.getenv("PORT", "10000"))


# =========================
# Database Configuration
# =========================
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.db").strip()


# =========================
# App Settings
# =========================
DEBUG = os.getenv("DEBUG", "false").strip().lower() == "true"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))


# =========================
# Security
# =========================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()


# =========================
# Game Limits
# =========================
MIN_PLAYERS = int(os.getenv("MIN_PLAYERS", "3"))
MAX_PLAYERS = int(os.getenv("MAX_PLAYERS", "20"))


# =========================
# Game Status Constants
# =========================
GAME_STATUS_REGISTERING = "registering"
GAME_STATUS_PLAYING = "playing"
GAME_STATUS_FINISHED = "finished"


# =========================
# Round Status Constants
# =========================
ROUND_STATUS_SPEAKING = "speaking"
ROUND_STATUS_VOTING = "voting"
ROUND_STATUS_FINISHED = "finished"


# =========================
# Role Constants
# =========================
ROLE_CITIZEN = "citizen"
ROLE_SPY = "spy"
ROLE_MISLED = "misled"


def get_webhook_url():
    if not APP_URL:
        return ""
    return f"{APP_URL}{WEBHOOK_PATH}"


def validate_config():
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN تنظیم نشده است.")

    if not BASE_URL:
        errors.append("BASE_URL تنظیم نشده است.")

    if not WEBHOOK_PATH.startswith("/"):
        errors.append("WEBHOOK_PATH باید با / شروع شود.")

    if MIN_PLAYERS < 3:
        errors.append("MIN_PLAYERS نباید کمتر از 3 باشد.")

    if MAX_PLAYERS < MIN_PLAYERS:
        errors.append("MAX_PLAYERS نباید از MIN_PLAYERS کمتر باشد.")

    return errors
