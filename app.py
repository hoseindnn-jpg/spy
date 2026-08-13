# app.py
import os
import sys
import json
from flask import Flask, request, jsonify
from datetime import datetime

# ─── تنظیمات پروژه ───
try:
    from config import (
        BOT_TOKEN,
        WEBHOOK_PATH,
        PORT,
        DEBUG,
        get_webhook_url,
        validate_config,
        GAME_STATUS_REGISTERING,
        BOT_USERNAME,
    )
except ImportError:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    GAME_STATUS_REGISTERING = "registering"
    BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# ─── هسته بازی و دیتابیس ───
import db
import game_logic
from telegram_api import (
    send_message,
    edit_message_reply_markup,
    answer_callback_query,
    set_webhook,
)

# ─── بررسی و مقداردهی اولیه ───
config_errors = validate_config() if hasattr(validate_config, '__call__') else []
if config_errors:
    print("خطا در تنظیمات محیطی ربات:")
    for err in config_errors:
        print(f"- {err}")
    sys.exit(1)

app = Flask(__name__)
db.init_db()

# ───────────────────────────
# ‌راه‌اندازی و مستقیماً وب‌هوک
# ───────────────────────────
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "message": "Spy Game Bot is running."})

@app.route("/set_webhook", methods=["GET", "POST"])
def register_webhook():
    webhook_url = get_webhook_url()
    if not webhook_url:
        return jsonify({"ok": False, "error": "APP_URL متغیر محیطی ست نشده است."}), 400
    result = set_webhook(webhook_url)
    return jsonify(result)

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True)
    if not update:
        return "No data", 400
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback_query(update["callback_query"])
    except Exception as exc:
        print(f"Webhook error: {exc}")
    return "ok", 200

# ───────────────────────────
# پردازش پیام‌های متنی
# ───────────────────────────
def handle_message(message):
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not user_id or not text:
        return

    # بررسی state های ذخیره شده برای کاربر
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT state, data FROM user_states WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if row:
        state = row["state"]
        data = row["data"]  # رشته‌ای: game_code

        if state == "awaiting_name":
            # جلوگیری از دستورات در هنگام دریافت نام
            if text.startswith("/"):
                send_message(chat_id, "❌ لطفاً فقط نام مستعار را بفرستید، نه دستور.")
                return
            process_name_submission(chat_id, user_id, text, data)
            return

        elif state == "awaiting_spy_guess":
            # حدس کلمه توسط جاسوس حذف‌شده
            try:
                game_logic.handle_spy_guess(data, user_id, text)
            except ValueError as e:
                send_message(chat_id, f"⚠️ {str(e)}")
            else:
                with db.get_db() as conn:
                    conn.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
            return

        elif state == "awaiting_bomber_target":
            # اگر بمب‌گذار بخواهد هدف را با متن وارد کند (اختیاری)
            try:
                target = db.get_player(data, int(text))  # انتظار user_id نداری، پس این‌جا فقط عدد را پردازش نمی‌کنیم
                # برای سادگی می‌توانیم به دکمه‌ها اکتفا کنیم
                send_message(chat_id, "❌ لطفاً از دکمه‌های زیر استفاده کنید.")
            except:
                send_message(chat_id, "❌ فرمت نامعتبر است.")
            return

    # ─── دستورات اصلی ───
    if text.startswith("/start"):
        parts = text.split(" ", 1)
        if len(parts) > 1 and parts[1].strip():
            join_player_to_game(chat_id, user_id, parts[1].strip())
            return
        send_menu(chat_id)
        return

    if text == "/newgame":
        create_game_lobby(chat_id)
        return

    # پیام ناشناخته
    if chat_id == user_id:
        send_message(chat_id, "برای شروع: /start یا /newgame")

# ───────────────────────────
# پردازش Callback Query ها
# ───────────────────────────
def handle_callback_query(callback_query):
    query_id = callback_query.get("id")
    user_id = callback_query.get("from", {}).get("id")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback_query.get("data", "")

    if not data:
        answer_callback_query(query_id, "درخواست نامعتبر است.", show_alert=True)
        return

    # ─── ساخت بازی جدید ───
    if data == "create_new_game":
        create_game_lobby(chat_id)
        answer_callback_query(query_id, "بازی جدید ساخته شد.")
        return

    # ─── نمایش بازیکنان ───
    if data.startswith("show_players:"):
        game_code = data.split(":", 1)[1]
        players = game_logic.get_players(game_code)
        if not players:
            answer_callback_query(query_id, "هنوز بازیکنی عضو نشده.", show_alert=True)
            return
        lines = "\n".join([f"- {p['display_name']}" for p in players])
        send_message(chat_id, f"👥 بازیکنان:\n{lines}")
        answer_callback_query(query_id, "لیست ارسال شد.")
        return

    # ─── شروع بازی / راند اول ───
    if data.startswith("start_game:"):
        game_code = data.split(":", 1)[1]
        game = game_logic.get_game(game_code)
        if not game:
            answer_callback_query(query_id, "بازی پیدا نشد.", show_alert=True)
            return
        if game["status"] != GAME_STATUS_REGISTERING:
            answer_callback_query(query_id, "بازی قبلاً شروع شده است.", show_alert=True)
            return

        # بررسی تعداد بازیکنان
        if len(game_logic.get_players(game_code)) < 3:
            answer_callback_query(query_id, "حداقل ۳ بازیکن لازم است.", show_alert=True)
            return

        try:
            result = game_logic.start_game_round(game_code)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        # پیام راهنما به مدیر برای شروع رأی‌گیری
        send_message(
            chat_id,
            "🗣 راند اول شروع شد! نقش‌ها ارسال شد.\n"
            "پس از پایان گفتگو، روی دکمه شروع رأی‌گیری بزنید.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🗳 شروع رای‌گیری", "callback_data": f"start_voting:{game_code}"}]
                ]
            }
        )
        if message_id:
            edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "بازی آغاز شد.")
        return

    # ─── شروع رأی‌گیری ───
    if data.startswith("start_voting:"):
        game_code = data.split(":", 1)[1]
        try:
            voting_info = game_logic.start_voting(game_code)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        # ارسال دکمه رأی به هر رأی‌دهنده (زنده + روح)
        voters = voting_info["voters"]
        targets = voting_info["targets"]

        for voter in voters:
            buttons = []
            for target in targets:
                if target["user_id"] != voter["user_id"]:  # نمی‌تواند به خودش رأی دهد
                    buttons.append([{
                        "text": f"🗳 رأی به {target['display_name']}",
                        "callback_data": f"vote:{game_code}:{target['user_id']}"
                    }])
            if buttons:
                send_message(
                    voter["user_id"],
                    "🗳 لطفاً به یک بازیکن رأی دهید:",
                    reply_markup={"inline_keyboard": buttons}
                )

        # پیام به گروه / چت مدیر
        send_message(
            chat_id,
            "🗳 رأی‌گیری آغاز شد. هر بازیکن باید در پیوی رأی خود را ثبت کند.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🏁 پایان رأی‌گیری (مدیر)", "callback_data": f"finish_vote:{game_code}"}]
                ]
            }
        )
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "رأی‌گیری آغاز شد.")
        return

    # ─── ثبت رأی ───
    if data.startswith("vote:"):
        parts = data.split(":")
        if len(parts) < 3:
            answer_callback_query(query_id, "داده نامعتبر.", show_alert=True)
            return
        game_code = parts[1]
        try:
            target_id = int(parts[2])
        except ValueError:
            answer_callback_query(query_id, "شناسه نامعتبر.", show_alert=True)
            return

        try:
            game_logic.cast_vote(game_code, user_id, target_id)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        answer_callback_query(query_id, "✅ رأی شما ثبت شد.")

        # بررسی اینکه آیا همه رأی داده‌اند؟
        current_round = game_logic.get_current_round(game_code)
        if current_round:
            eligible_voters = game_logic.get_eligible_voters(game_code)
            all_voted = all(
                game_logic.get_vote(current_round["id"], v["user_id"]) is not None
                for v in eligible_voters
            )
            if all_voted:
                # به مدیر اطلاع بده تا رأی‌گیری را ببندد یا خودکار ببندیم
                send_message(
                    chat_id,  # اینجا chat_id ممکن است همان گروه مدیر باشد ولی بهتر است به مدیر خصوصی ارسال شود
                    "✅ همه بازیکنان رأی دادند. مدیر می‌تواند رأی‌گیری را پایان دهد.",
                    reply_markup={
                        "inline_keyboard": [
                            [{"text": "🏁 پایان رأی‌گیری", "callback_data": f"finish_vote:{game_code}"}]
                        ]
                    }
                )
        return

    # ─── پایان رأی‌گیری توسط مدیر ───
    if data.startswith("finish_vote:"):
        game_code = data.split(":", 1)[1]
        game = game_logic.get_game(game_code)
        if not game or user_id != game["admin_id"]:
            answer_callback_query(query_id, "فقط مدیر می‌تواند.", show_alert=True)
            return

        current_round = game_logic.get_current_round(game_code)
        if not current_round:
            answer_callback_query(query_id, "راند فعال نیست.", show_alert=True)
            return

        # بررسی رأی‌ندادگان
        eligible_voters = game_logic.get_eligible_voters(game_code)
        non_voters = [v for v in eligible_voters if game_logic.get_vote(current_round["id"], v["user_id"]) is None]
        if non_voters:
            names = "\n".join([v["display_name"] for v in non_voters])
            answer_callback_query(
                query_id,
                f"⚠️ هنوز رأی ندادند:\n{names}",
                show_alert=True
            )
            return

        # پایان رأی‌گیری و پردازش زنجیره حذف
        try:
            result = game_logic.finish_voting(game_code)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        # اگر تساوی => نیاز به رأی‌گیری مجدد (دوباره دکمه‌ها فرستاده شود)
        if result.get("tie"):
            # نمایش گزینه‌ها برای رأی مجدد
            send_message(
                chat_id,
                "⚖️ رأی‌گیری مساوی شد. بین نامزدهای زیر دوباره رأی بگیرید.",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🗳 شروع رأی‌گیری مجدد بین تساوی‌ها",
                          "callback_data": f"start_tie_vote:{game_code}"}]
                    ]
                }
            )
        else:
            # ممکن است مرحله حدس جاسوس یا بمب‌گذار فعال شده باشد
            if result.get("action_required"):
                if result.get("pending_spy"):
                    send_message(
                        result["pending_spy"],
                        "🕵️ شما حذف شدید. یک حدس بزنید (کلمه شهروند):",
                    )
                elif result.get("pending_bomber"):
                    # ارسال دکمه‌های انتخاب هدف برای بمب‌گذار
                    bomber_id = result["pending_bomber"]
                    alive_players = game_logic.get_alive_players(game_code)
                    buttons = []
                    for p in alive_players:
                        if p["user_id"] != bomber_id:
                            buttons.append([{
                                "text": f"💣 انفجار {p['display_name']}",
                                "callback_data": f"bomber_select:{game_code}:{p['user_id']}"
                            }])
                    send_message(
                        bomber_id,
                        "💣 انتخاب کنید چه کسی را منفجر کنید:",
                        reply_markup={"inline_keyboard": buttons}
                    )
            else:
                # راند تمام شده و پیام نتیجه ارسال شده است (در game_logic)
                pass

        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "رأی‌گیری پایان یافت.")
        return

    # ─── رأی‌گیری مجدد بین تساوی‌ها ───
    if data.startswith("start_tie_vote:"):
        game_code = data.split(":", 1)[1]
        current_round = game_logic.get_current_round(game_code)
        if not current_round:
            answer_callback_query(query_id, "راندی موجود نیست.", show_alert=True)
            return

        tied_users = game_logic.get_round_tie_targets(current_round["id"])
        try:
            game_logic.start_tie_voting_round(game_code, tied_users)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        # ارسال دکمه‌ها دوباره
        tie_targets = game_logic.get_eligible_vote_targets(game_code, tied_users)
        voters = game_logic.get_eligible_voters(game_code)
        for voter in voters:
            buttons = []
            for target in tie_targets:
                if target["user_id"] != voter["user_id"]:
                    buttons.append([{
                        "text": f"🗳 رأی به {target['display_name']}",
                        "callback_data": f"vote:{game_code}:{target['user_id']}"
                    }])
            if buttons:
                send_message(voter["user_id"], "⚖️ رأی‌گیری مجدد:", reply_markup={"inline_keyboard": buttons})

        send_message(chat_id, "⚖️ رأی‌گیری مجدد شروع شد.")
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "رأی‌گیری مجدد فعال شد.")
        return

    # ─── انتخاب هدف بمب‌گذار ───
    if data.startswith("bomber_select:"):
        parts = data.split(":")
        game_code = parts[1]
        try:
            target_id = int(parts[2])
        except ValueError:
            answer_callback_query(query_id, "شناسه نامعتبر.", show_alert=True)
            return

        try:
            game_logic.handle_bomber_action(game_code, user_id, target_id)
        except ValueError as e:
            answer_callback_query(query_id, str(e), show_alert=True)
            return

        answer_callback_query(query_id, "انفجار انجام شد.")
        return

    answer_callback_query(query_id, "دکمه ناشناخته.", show_alert=True)

# ───────────────────────────
# توابع کمکی
# ───────────────────────────
def send_menu(chat_id):
    send_message(
        chat_id,
        "<b>به ربات بازی جاسوس خوش آمدید! 🕵️‍♂️</b>\n\n"
        "برای ساخت بازی جدید روی دکمه زیر بزنید:",
        reply_markup={
            "inline_keyboard": [
                [{"text": "شروع بازی جدید 🎮", "callback_data": "create_new_game"}]
            ]
        }
    )

def create_game_lobby(chat_id):
    # کد بازی بر اساس چت آیدی (بدون خط تیره)
    game_code = f"G{chat_id}".replace("-", "")

    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM games WHERE game_code = ?", (game_code,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE games SET status = ?, round_number = 0, word_pair_id = NULL,
                is_round_active = 0, first_elimination_done = 0, winner_team = NULL
                WHERE game_code = ?
                """,
                (GAME_STATUS_REGISTERING, game_code)
            )
            conn.execute("DELETE FROM players WHERE game_code = ?", (game_code,))
        else:
            conn.execute(
                """
                INSERT INTO games (game_code, admin_id, status, created_at, round_number, is_round_active)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (game_code, chat_id, GAME_STATUS_REGISTERING, datetime.now().isoformat())
            )

    if not BOT_USERNAME:
        send_message(chat_id, "⚠️ BOT_USERNAME تنظیم نشده است.")
        return

    join_link = f"https://t.me/{BOT_USERNAME}?start={game_code}"
    send_message(
        chat_id,
        "🎮 <b>بازی جدید ساخته شد!</b>\n"
        f"کد: <code>{game_code}</code>\n\n"
        f"لینک دعوت:\n{join_link}",
        reply_markup={
            "inline_keyboard": [
                [{"text": "شروع بازی 🚀", "callback_data": f"start_game:{game_code}"}],
                [{"text": "نمایش بازیکنان 👥", "callback_data": f"show_players:{game_code}"}]
            ]
        }
    )

def join_player_to_game(chat_id, user_id, game_code):
    game = game_logic.get_game(game_code)
    if not game:
        send_message(chat_id, "⚠️ بازی پیدا نشد.")
        return
    if game["status"] != GAME_STATUS_REGISTERING:
        send_message(chat_id, "⚠️ ثبت‌نام بسته شده است.")
        return

    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
            (game_code, user_id)
        ).fetchone()
        if existing:
            send_message(chat_id, "✅ شما قبلاً عضو هستید.")
            return

        # درخواست نام
        conn.execute(
            "INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, 'awaiting_name', ?)",
            (user_id, game_code)
        )

    send_message(
        chat_id,
        "🕵️‍♂️ لطفاً نام مستعار خود را ارسال کنید (۲ تا ۱۵ کاراکتر):"
    )

def process_name_submission(chat_id, user_id, name, game_code):
    name = name.strip()
    if len(name) < 2 or len(name) > 15:
        send_message(chat_id, "❌ نام باید بین ۲ تا ۱۵ کاراکتر باشد. دوباره بفرستید:")
        return

    with db.get_db() as conn:
        duplicate = conn.execute(
            "SELECT 1 FROM players WHERE game_code = ? AND display_name = ?",
            (game_code, name)
        ).fetchone()
        if duplicate:
            send_message(chat_id, f"❌ نام '{name}' تکراری است. نام دیگری بفرستید:")
            return

        # ثبت بازیکن
        conn.execute(
            """
            INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
            VALUES (?, ?, ?, NULL, 1, 0, ?)
            """,
            (game_code, user_id, name, datetime.now().isoformat())
        )
        conn.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))

    # اطلاع به مدیر (اگر خود مدیر نباشد)
    game = game_logic.get_game(game_code)
    if game and game["admin_id"] != user_id:
        send_message(game["admin_id"], f"👤 بازیکن <b>{name}</b> عضو شد.")

    send_message(chat_id, f"✅ عالیه {name}! عضویت شما ثبت شد.")

# ───────────────────────────
# اجرا
# ───────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
