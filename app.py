import os
import sys
from flask import Flask, request, jsonify

# ایمپورت تنظیمات و اعتبارسنجی اولیه
from config import (
    BOT_TOKEN, WEBHOOK_PATH, PORT, DEBUG,
    get_webhook_url, validate_config,
    GAME_STATUS_REGISTERING, GAME_STATUS_PLAYING,
    ROLE_CITIZEN, ROLE_SPY, ROLE_MISLED
)

# ایمپورت توابع مدیریت دیتابیس
from db import init_db, get_db

# ایمپورت توابع ارتباط با API تلگرام
from telegram_api import (
    send_message, edit_message_reply_markup,
    answer_callback_query, set_webhook, delete_message
)

# ایمپورت منطق بازی
import game_logic

# اعتبارسنجی فایل کانفیگ قبل از بالا آمدن سرور
config_errors = validate_config()
if config_errors:
    print("خطا در تنظیمات محیطی ربات:")
    for err in config_errors:
        print(f"- {err}")
    sys.exit(1)

# ساخت اپلیکیشن فلاسک
app = Flask(__name__)

# مقداردهی اولیه دیتابیس
init_db()


@app.route("/", methods=["GET"])
def index():
    """تست ساده برای صحت کارکرد سرور در رندر"""
    return jsonify({"status": "ok", "message": "Spy Game Bot is running."}), 200


@app.route("/set_webhook", methods=["GET", "POST"])
def register_webhook():
    """اندپوینت برای تنظیم وب‌هوک تلگرام به صورت خودکار یا دستی"""
    webhook_url = get_webhook_url()
    if not webhook_url:
        return jsonify({"ok": False, "error": "APP_URL در متغیرهای محیطی ست نشده است."}), 400
    
    result = set_webhook(webhook_url)
    return jsonify(result), 200


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """دریافت آپدیت‌های ارسالی از تلگرام"""
    update = request.get_json()
    if not update:
        return "No data", 400

    # بررسی پیام متنی
    if "message" in update:
        handle_message(update["message"])
    
    # بررسی کلیک روی دکمه‌های شیشه‌ای
    elif "callback_query" in update:
        handle_callback_query(update["callback_query"])

    return "ok", 200


def handle_message(message):
    """مدیریت پیام‌های متنی و دستورات متنی"""
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "").strip()
    username = message.get("from", {}).get("username", "")
    first_name = message.get("from", {}).get("first_name", "User")
    display_name = f"@{username}" if username else first_name

    if not chat_id or not text:
        return

    # دستور شروع کار با ربات
    if text.startswith("/start"):
        parts = text.split(" ")
        
        # اگر کاربر از طریق لینک جوین بازی وارد شده باشد (/start game_code)
        if len(parts) > 1:
            game_code = parts[1]
            join_player_to_game(chat_id, user_id, display_name, game_code)
        else:
            send_message(
                chat_id,
                "<b>به ربات بازی جاسوس خوش آمدید! 🕵️‍♂️</b>\n\n"
                "برای ساخت یک بازی جدید در گروه، دستور /newgame را ارسال کنید یا دکمه زیر را فشار دهید.",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "ساخت بازی جدید 🎮", "callback_data": "create_new_game"}]
                    ]
                }
            )

    elif text.startswith("/newgame"):
        # بررسی اینکه آیا چت یک گروه یا سوپرگروه است
        chat_type = message.get("chat", {}).get("type")
        if chat_type not in ["group", "supergroup"]:
            send_message(chat_id, "⚠️ بازی جاسوس را باید در یک گروه شروع کنید!")
            return
        
        create_game_lobby(chat_id)


def create_game_lobby(chat_id):
    """ایجاد لابی بازی جدید در گروه"""
    game_code = f"G{chat_id}".replace("-", "") # یک کد منحصر به فرد بر اساس شناسه چت
    
    with get_db() as db:
        # بررسی اینکه بازی از قبل وجود دارد یا خیر
        existing_game = db.execute("SELECT * FROM games WHERE game_code = ?", (game_code,)).fetchone()
        if existing_game:
            # ریست کردن وضعیت بازی قبلی
            db.execute(
                "UPDATE games SET status = ?, round_number = 0, word_pair_id = NULL, is_round_active = 0 WHERE game_code = ?",
                (GAME_STATUS_REGISTERING, game_code)
            )
            db.execute("DELETE FROM players WHERE game_code = ?", (game_code,))
        else:
            db.execute(
                "INSERT INTO games (game_code, status, round_number, is_round_active) VALUES (?, ?, 0, 0)",
                (game_code, GAME_STATUS_REGISTERING)
            )
            
    bot_username = os.getenv("BOT_USERNAME", "SpyGameBot") # نام کاربری ربات را در انوایرمنت ست کنید
    join_link = f"https://t.me/{bot_username}?start={game_code}"

    keyboard = {
        "inline_keyboard": [
            [{"text": "عضویت در بازی ➕", "url": join_link}],
            [{"text": "شروع بازی 🚀", "callback_data": f"start_game:{game_code}"}],
            [{"text": "نمایش لیست بازیکنان 👥", "callback_data": f"show_players:{game_code}"}]
        ]
    }

    send_message(
        chat_id,
        "🎮 <b>یک بازی جدید ساخته شد!</b>\n\n"
        "بازیکنان لطفاً روی دکمه زیر کلیک کرده و دکمه Start را در پی‌وی ربات بزنند تا وارد بازی شوند.",
        reply_markup=keyboard
    )


def join_player_to_game(user_chat_id, user_id, display_name, game_code):
    """عضو کردن بازیکن در بازی از طریق پی‌وی ربات"""
    game = game_logic.get_game(game_code)
    if not game:
        send_message(user_chat_id, "⚠️ بازی مورد نظر یافت نشد یا منقضی شده است.")
        return

    if game["status"] != GAME_STATUS_REGISTERING:
        send_message(user_chat_id, "⚠️ ثبت‌نام این بازی تمام شده است و امکان عضویت وجود ندارد.")
        return

    with get_db() as db:
        # بررسی اینکه کاربر از قبل عضو بازی هست یا خیر
        player = db.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
            (game_code, user_id)
        ).fetchone()

        if player:
            send_message(user_chat_id, "شما از قبل عضو این بازی هستید! منتظر بمانید تا بازی شروع شود.")
        else:
            db.execute(
                "INSERT INTO players (game_code, user_id, display_name, role, is_alive, score) VALUES (?, ?, ?, NULL, 1, 0)",
                (game_code, user_id, display_name)
            )
            send_message(user_chat_id, "🎉 شما با موفقیت عضو بازی شدید! به گروه برگردید تا بازی شروع شود.")


def handle_callback_query(callback_query):
    """مدیریت رویداد کلیک روی دکمه‌های شیشه‌ای"""
    query_id = callback_query.get("id")
    user_id = callback_query.get("from", {}).get("id")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback_query.get("data", "")

    if not data:
        return

    # شروع بازی توسط ادمین در گروه
    if data.startswith("start_game:"):
        game_code = data.split(":")[1]
        game = game_logic.get_game(game_code)
        
        if not game:
            answer_callback_query(query_id, "بازی پیدا نشد.", show_alert=True)
            return

        if game["status"] != GAME_STATUS_REGISTERING:
            answer_callback_query(query_id, "بازی در حال جریان است یا به اتمام رسیده.", show_alert=True)
            return

        # فراخوانی لاجیک شروع بازی
        result = game_logic.start_game_round(game_code, chat_id)
        if not result.get("ok"):
            answer_callback_query(query_id, result.get("error", "خطا در شروع بازی"), show_alert=True)
        else:
            answer_callback_query(query_id, "بازی با موفقیت شروع شد!")
            # غیرفعال کردن دکمه‌های پنل مدیریت لابی
            edit_message_reply_markup(chat_id, message_id, reply_markup=None)

    # نمایش لیست بازیکنانی که جوین شده‌اند
    elif data.startswith("show_players:"):
        game_code = data.split(":")[1]
        players = game_logic.get_players(game_code)
        if not players:
            answer_callback_query(query_id, "هنوز هیچ بازیکنی عضو نشده است.", show_alert=True)
            return

        player_list = "\n".join([f"- {p['display_name']}" for p in players])
        answer_callback_query(query_id, "لیست بازیکنان ارسال شد.")
        send_message(chat_id, f"👥 <b>بازیکنان ثبت‌نام شده:</b>\n{player_list}")

    # ثبت رای بازیکنان در مرحله رای‌گیری
    elif data.startswith("vote:"):
        # ساختار دیتا: vote:game_code:target_user_id
        parts = data.split(":")
        game_code = parts[1]
        target_id = int(parts[2])

        current_round = game_logic.get_current_round(game_code)
        if not current_round or current_round["status"] != "voting":
            answer_callback_query(query_id, "در حال حاضر مرحله رای‌گیری فعال نیست.", show_alert=True)
            return

        # بررسی زنده بودن رای دهنده
        voter = game_logic.get_player_by_user_id(game_code, user_id)
        if not voter or not voter["is_alive"]:
            answer_callback_query(query_id, "بازیکنان حذف شده نمی‌توانند رای دهند.", show_alert=True)
            return

        # ثبت رای در دیتابیس
        game_logic.save_vote(current_round["id"], user_id, target_id)
        answer_callback_query(query_id, "رای شما با موفقیت ثبت شد.")


# ساختار اجرای برنامه
if __name__ == "__main__":
    # در محیط محلی یا سرور Render پورت بر اساس متغیر محیطی تنظیم می‌شود
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
