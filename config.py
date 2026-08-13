import os


# =========================
# Helper Functions
# =========================
def get_int_env(name, default):
    """
    دریافت مقدار عددی از Environment Variable
    """
    value = os.getenv(name, str(default)).strip()

    try:
        return int(value)
    except ValueError:
        raise RuntimeError(
            f"مقدار متغیر محیطی {name} باید عدد صحیح باشد."
        )


# =========================
# Telegram Bot Configuration
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# بدون @ ذخیره شود؛ مثلاً MySpyGameBot
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

# آدرس پایه Telegram Bot API
BASE_URL = os.getenv(
    "TELEGRAM_BASE_URL",
    "https://api.telegram.org"
).strip().rstrip("/")


# =========================
# Flask / Webhook Configuration
# =========================
APP_URL = os.getenv(
    "APP_URL",
    ""
).strip().rstrip("/")

WEBHOOK_PATH = os.getenv(
    "WEBHOOK_PATH",
    "/telegram/webhook"
).strip()

# Render معمولاً مقدار PORT را خودش تنظیم می‌کند
PORT = get_int_env("PORT", 10000)

DEBUG = os.getenv(
    "DEBUG",
    "false"
).strip().lower() == "true"

REQUEST_TIMEOUT = get_int_env(
    "REQUEST_TIMEOUT",
    10
)


# =========================
# Webhook Security
# =========================
WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    ""
).strip()


# =========================
# Database Configuration
# =========================
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "bot.db"
).strip()


# =========================
# Game Limits
# =========================
MIN_PLAYERS = get_int_env(
    "MIN_PLAYERS",
    3
)

MAX_PLAYERS = get_int_env(
    "MAX_PLAYERS",
    20
)


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
# Main Role Constants
# =========================
ROLE_CITIZEN = "citizen"
ROLE_SPY = "spy"
ROLE_MISLED = "misled"


# =========================
# Webhook URL
# =========================
def get_webhook_url():
    """
    ساخت آدرس کامل Webhook برای Telegram
    مثال:
    https://example.onrender.com/telegram/webhook
    """
    if not APP_URL or not WEBHOOK_PATH:
        return ""

    return f"{APP_URL}{WEBHOOK_PATH}"


# =========================
# Configuration Validation
# =========================
def validate_config():
    """
    بررسی تنظیمات ضروری پروژه
    خروجی: لیستی از خطاها
    """
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN تنظیم نشده است.")

    if not BOT_USERNAME:
        errors.append("BOT_USERNAME تنظیم نشده است.")

    if not BASE_URL:
        errors.append("TELEGRAM_BASE_URL تنظیم نشده است.")
    elif not BASE_URL.startswith("https://"):
        errors.append(
            "TELEGRAM_BASE_URL باید با https:// شروع شود."
        )

    if not APP_URL:
        errors.append("APP_URL تنظیم نشده است.")
    elif not APP_URL.startswith("https://"):
        errors.append(
            "APP_URL باید آدرس HTTPS سرویس Render باشد."
        )

    if not WEBHOOK_PATH:
        errors.append("WEBHOOK_PATH تنظیم نشده است.")
    elif not WEBHOOK_PATH.startswith("/"):
        errors.append(
            "WEBHOOK_PATH باید با / شروع شود."
        )

    if PORT <= 0 or PORT > 65535:
        errors.append(
            "PORT باید عددی بین 1 تا 65535 باشد."
        )

    if REQUEST_TIMEOUT <= 0:
        errors.append(
            "REQUEST_TIMEOUT باید بزرگ‌تر از صفر باشد."
        )

    if MIN_PLAYERS < 3:
        errors.append(
            "MIN_PLAYERS نباید کمتر از 3 باشد."
        )

    if MAX_PLAYERS < MIN_PLAYERS:
        errors.append(
            "MAX_PLAYERS نباید از MIN_PLAYERS کمتر باشد."
        )

    return errors
