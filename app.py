import os
import sys
from flask import Flask, request, jsonify
from datetime import datetime

from config import (
    BOT_TOKEN,
    WEBHOOK_PATH,
    PORT,
    DEBUG,
    get_webhook_url,
    validate_config,
    GAME_STATUS_REGISTERING,
)

from db import init_db, get_db

from telegram_api import (
    send_message,
    edit_message_reply_markup,
    answer_callback_query,
    set_webhook,
)

import game_logic

# بررسی پیکربندی متغیرهای محیطی
config_errors = validate_config()
if config_errors:
    print("خطا در تنظیمات محیطی ربات:")
    for err in config_errors:
        print(f"- {err}")
    sys.exit(1)

app = Flask(__name__)
init_db()


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "Spy Game Bot is running."
    }), 200


@app.route("/set_webhook", methods=["GET", "POST"])
def register_webhook():
    webhook_url = get_webhook_url()
    if not webhook_url:
        return jsonify({
            "ok": False,
            "error": "APP_URL در متغیرهای محیطی ست نشده است."
        }), 400

    result = set_webhook(webhook_url)
    return jsonify(result), 200


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


def handle_message(message):
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not user_id or not text:
        return

    # ۱) بررسی وضعیت ذخیره شده کاربر (نظیر انتظار برای دریافت نام یا حدس جاسوس)
    with get_db() as db:
        state_row = db.execute(
            "SELECT state, data FROM user_states WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if state_row:
        state, data = state_row["state"], state_row["data"]

        # الف) دریافت نام مستعار
        if state == "awaiting_name":
            if text.startswith("/"):
                send_message(
                    chat_id,
                    "❌ لطفاً فقط نام مستعار خود را ارسال کنید، نه دستور.\n"
                    "مثال: علی"
                )
                return
            process_name_submission(chat_id, user_id, text, data)
            return

        # ب) دریافت حدس کلمه از جاسوس در پی‌وی
        elif state == "awaiting_spy_guess":
            game_code = data
            # پردازش حدس کلمه جاسوس با استفاده از منطق اصلی بازی
            res = game_logic.process_spy_guess(game_code, chat_id, user_id, text)
            if res.get("ok"):
                with get_db() as db:
                    db.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
            return

    # ۲) دستور /start
    if text.startswith("/start"):
        parts = text.split(" ", 1)

        # اگر /start همراه با پارامتر (کد لابی) ارسال شده باشد
        if len(parts) > 1 and parts[1].strip():
            game_code = parts[1].strip()
            join_player_to_game(chat_id, user_id, game_code)
            return

        # اگر دستور استارت ساده و بدون پارامتر باشد
        send_message(
            chat_id,
            "<b>به ربات بازی جاسوس خوش آمدید! 🕵️‍♂️</b>\n\n"
            "برای ساخت بازی جدید روی دکمه زیر بزنید یا دستور /newgame را ارسال کنید.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "شروع بازی جدید 🎮", "callback_data": "create_new_game"}]
                ]
            }
        )
        return

    # ۳) دستور /newgame برای ساخت بازی جدید
    if text.startswith("/newgame"):
        create_game_lobby(chat_id)
        return

    # ۴) پیام پیش‌فرض برای متون ناشناخته
    # پیام پیش‌فرض فقط در چت خصوصی ارسال می‌شود تا در گروه‌ها اسپم ایجاد نشود
    if chat_id == user_id:
        send_message(
            chat_id,
            "برای شروع، یکی از این کارها را انجام بده:\n"
            "• /start برای باز کردن منو\n"
            "• /newgame برای ساخت بازی جدید"
        )


def create_game_lobby(chat_id):
    game_code = f"G{chat_id}".replace("-", "")

    with get_db() as db:
        existing_game = db.execute(
            "SELECT * FROM games WHERE game_code = ?",
            (game_code,)
        ).fetchone()

        if existing_game:
            db.execute(
                """
                UPDATE games
                SET status = ?, round_number = 0, word_pair_id = NULL, is_round_active = 0
                WHERE game_code = ?
                """,
                (GAME_STATUS_REGISTERING, game_code)
            )
            db.execute(
                "DELETE FROM players WHERE game_code = ?",
                (game_code,)
            )
        else:
            db.execute(
                """
                INSERT INTO games (
                    game_code,
                    admin_id,
                    status,
                    created_at,
                    round_number,
                    is_round_active
                )
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (
                    game_code,
                    chat_id,
                    GAME_STATUS_REGISTERING,
                    datetime.now().isoformat()
                )
            )

    bot_username = os.getenv("BOT_USERNAME", "").strip()
    if not bot_username:
        send_message(
            chat_id,
            "⚠️ متغیر محیطی BOT_USERNAME در تنظیمات سرور ثبت نشده است."
        )
        return

    join_link = f"https://t.me/{bot_username}?start={game_code}"

    send_message(
        chat_id,
        "🎮 <b>بازی جدید ساخته شد!</b>\n\n"
        f"کد بازی: <code>{game_code}</code>\n\n"
        "لینک زیر را برای بازیکن‌ها بفرستید تا عضو شوند:\n"
        f"{join_link}\n\n"
        "بعد از اینکه همه بازیکنان عضو شدند، روی شروع کلیک کنید.",
        reply_markup={
            "inline_keyboard": [
                [{"text": "شروع بازی 🚀", "callback_data": f"start_game:{game_code}"}],
                [{"text": "نمایش بازیکنان 👥", "callback_data": f"show_players:{game_code}"}]
            ]
        }
    )


def join_player_to_game(user_chat_id, user_id, game_code):
    game = game_logic.get_game(game_code)

    if not game:
        send_message(
            user_chat_id,
            "⚠️ بازی مورد نظر پیدا نشد یا منقضی شده است."
        )
        return

    if game["status"] != GAME_STATUS_REGISTERING:
        send_message(user_chat_id, "⚠️ ثبت‌نام این بازی در حال حاضر بسته شده است.")
        return

    with get_db() as db:
        existing_player = db.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
            (game_code, user_id)
        ).fetchone()

        if existing_player:
            send_message(
                user_chat_id,
                "✅ شما از قبل عضو این بازی هستید."
            )
            return

        # هدایت کاربر به وارد کردن نام مستعار
        db.execute(
            """
            INSERT OR REPLACE INTO user_states (user_id, state, data)
            VALUES (?, ?, ?)
            """,
            (user_id, "awaiting_name", game_code)
        )

    send_message(
        user_chat_id,
        "🕵️‍♂️ لطفاً نام مستعار خود را ارسال کنید:\n\n"
        "• بین ۲ تا ۱۵ کاراکتر باشد.\n"
        "• نام تکراری در بازی نباشد."
    )


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

    # ۱) دکمه عمومی ساخت بازی جدید
    if data == "create_new_game":
        create_game_lobby(chat_id)
        answer_callback_query(query_id, "بازی جدید ساخته شد.")
        return

    # ۲) نمایش بازیکنان لابی
    elif data.startswith("show_players:"):
        game_code = data.split(":", 1)[1]
        players = game_logic.get_players(game_code)

        if not players:
            answer_callback_query(query_id, "هنوز هیچ بازیکنی عضو نشده است.", show_alert=True)
            return

        player_list = "\n".join([f"- {player['display_name']}" for player in players])
        send_message(chat_id, f"👥 <b>بازیکنان ثبت‌نام‌شده:</b>\n{player_list}")
        answer_callback_query(query_id, "لیست بازیکنان ارسال شد.")
        return

    # ۳) شروع روند بازی توسط دکمه مدیر
    elif data.startswith("start_game:"):
        game_code = data.split(":", 1)[1]
        game = game_logic.get_game(game_code)

        if not game:
            answer_callback_query(query_id, "بازی پیدا نشد.", show_alert=True)
            return

        if game["status"] != GAME_STATUS_REGISTERING:
            answer_callback_query(query_id, "بازی قبلاً شروع شده است یا در این وضعیت قابل شروع نیست.", show_alert=True)
            return

        result = game_logic.start_game_round(game_code, chat_id)
        if not result.get("ok"):
            answer_callback_query(query_id, result.get("error", "خطا در شروع بازی"), show_alert=True)
            return

        # پس از توزیع نقش‌ها، دکمه شروع رأی‌گیری برای مدیر گروه ارسال می‌شود
        send_message(
            chat_id,
            "💬 گفتگو کنید و به سوالات پاسخ دهید.\n"
            "هنگامی که آماده رأی‌گیری بودید، مدیر دکمه زیر را لمس کند:",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🗳 شروع رای‌گیری عمومی", "callback_data": f"start_voting:{game_code}"}]
                ]
            }
        )
        answer_callback_query(query_id, "بازی آغاز شد و نقش‌ها توزیع گردید.")
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        return

    # ۴) شروع فاز رای‌گیری توسط مدیر (اصلاح: ارسال دکمه‌ها به تک‌تک بازیکنان زنده در پی‌وی)
    elif data.startswith("start_voting:"):
        game_code = data.split(":", 1)[1]
        res = game_logic.start_voting_round(game_code, chat_id)
        if not res.get("ok"):
            answer_callback_query(query_id, res.get("error", "امکان شروع رای‌گیری وجود ندارد."), show_alert=True)
            return

        # دریافت لیست همه بازیکنان زنده
        alive_players = game_logic.get_alive_players(game_code)

        # ارسال پنل رأی برای هر بازیکن زنده به صورت خصوصی
        for p in alive_players:
            buttons = []
            for target in alive_players:
                # بازیکن نمی‌تواند به خودش رأی بدهد
                if target["user_id"] != p["user_id"]:
                    buttons.append([
                        {
                            "text": f"🗳 رای به {target['display_name']}",
                            "callback_data": f"vote:{game_code}:{target['user_id']}"
                        }
                    ])

            send_message(
                p["user_id"],
                "🗳 <b>رأی‌گیری آغاز شد!</b>\n"
                "بازیکن زنده مورد نظر خود را برای حذف انتخاب کنید:",
                reply_markup={"inline_keyboard": buttons}
            )

        # پیام اعلان در گروه + دکمه اتمام رأی‌گیری برای مدیر
        send_message(
            chat_id,
            "🗳 <b>رأی‌گیری آغاز شد!</b>\n"
            "دکمه‌های رأی‌گیری به صورت خصوصی برای هر بازیکن ارسال شد.\n"
            "همه بازیکنان زنده باید رأی خود را ثبت کنند.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🏁 پایان رأی‌گیری (توسط مدیر)", "callback_data": f"force_finish_vote:{game_code}"}]
                ]
            }
        )
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "رأی‌گیری آغاز شد.")
        return

    # ۵) فرآیند ثبت رأی کاربران
    elif data.startswith("vote:"):
        parts = data.split(":")
        if len(parts) < 3:
            answer_callback_query(query_id, "داده رای نامعتبر است.", show_alert=True)
            return

        game_code = parts[1]
        try:
            target_id = int(parts[2])
        except ValueError:
            answer_callback_query(query_id, "شناسه رای نامعتبر است.", show_alert=True)
            return

        current_round = game_logic.get_current_round(game_code)
        # پشتیبانی از هر دو وضعیت رای‌گیری عادی و رأی‌گیری مجدد در صورت تساوی
        if not current_round or current_round["status"] not in ["voting", "tie_voting"]:
            answer_callback_query(query_id, "در حال حاضر مرحله رای‌گیری فعال نیست.", show_alert=True)
            return

        voter = game_logic.get_player_by_user_id(game_code, user_id)
        if not voter or not voter["is_alive"]:
            answer_callback_query(query_id, "فقط بازیکنان زنده می‌توانند رای دهند.", show_alert=True)
            return

        game_logic.save_vote(current_round["id"], user_id, target_id)
        answer_callback_query(query_id, "رای شما با موفقیت ثبت شد.")

        # بررسی اینکه آیا همه بازیکنان زنده رای خود را ثبت کرده‌اند
        if game_logic.have_all_alive_players_voted(game_code):
            game_logic.finish_voting_round(game_code, chat_id)
            edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        return

    # ۶) پایان دادن دستی به رأی‌گیری توسط مدیر (اصلاح: فقط مدیر + بررسی رأی‌ندادگان)
    elif data.startswith("force_finish_vote:"):
        game_code = data.split(":", 1)[1]
        game = game_logic.get_game(game_code)

        # فقط مدیر بازی اجازه دارد رأی‌گیری را به پایان برساند
        if not game or user_id != game["admin_id"]:
            answer_callback_query(
                query_id,
                "فقط مدیر بازی می‌تواند رأی‌گیری را به پایان برساند.",
                show_alert=True
            )
            return

        # اگر هنوز همه رأی نداده‌اند، هشدار بده و لیست رأی‌ندادگان را نمایش بده
        non_voters = game_logic.get_non_voters(game_code)
        if non_voters:
            names = "\n".join([f"- {player['display_name']}" for player in non_voters])
            answer_callback_query(
                query_id,
                f"⚠️ هنوز برخی از بازیکنان رأی نداده‌اند:\n{names}",
                show_alert=True
            )
            return

        # اجرای اتمام رای‌گیری و هدایت به شمارش آرا
        game_logic.finish_voting_round(game_code, chat_id)
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "رأی‌گیری خاتمه یافت.")
        return

    # ۷) انتخاب کاربر هدف جهت حذف در تساوی مرحله دوم توسط مدیر
    elif data.startswith("admin_kill:"):
        parts = data.split(":")
        game_code = parts[1]
        try:
            target_id = int(parts[2])
        except ValueError:
            return

        res = game_logic.admin_select_tie_loser(game_code, chat_id, target_id)
        if res.get("ok"):
            buttons = [
                [{"text": "✅ بله، مطمئنم", "callback_data": f"confirm_kill:{game_code}"}],
                [{"text": "❌ خیر، تغییر انتخاب", "callback_data": f"start_voting:{game_code}"}]
            ]
            send_message(
                chat_id,
                f"🛡 <b>تأییدیه نهایی حذف:</b>\n"
                f"آیا مطمئن هستید که می‌خواهید بازیکن <b>{res['display_name']}</b> را از بازی حذف کنید؟",
                reply_markup={"inline_keyboard": buttons}
            )
            edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        else:
            answer_callback_query(query_id, res.get("error", "خطا رخ داد."), show_alert=True)
        return

    # ۸) تایید نهایی حذف بازیکن انتخابی توسط مدیر
    elif data.startswith("confirm_kill:"):
        game_code = data.split(":", 1)[1]
        game_logic.confirm_admin_selected_tie_loser(game_code, chat_id)
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        answer_callback_query(query_id, "تایید حذف اعمال شد.")
        return

    answer_callback_query(query_id, "دکمه ناشناخته است.", show_alert=True)


def process_name_submission(chat_id, user_id, name, game_code):
    if len(name) < 2 or len(name) > 15:
        send_message(chat_id, "❌ نام باید بین ۲ تا ۱۵ کاراکتر باشد. مجدداً ارسال کنید:")
        return

    with get_db() as db:
        duplicate = db.execute(
            "SELECT 1 FROM players WHERE game_code = ? AND display_name = ?",
            (game_code, name)
        ).fetchone()

        if duplicate:
            send_message(
                chat_id,
                f"❌ نام '{name}' قبلاً توسط بازیکن دیگری انتخاب شده است. نام دیگری بفرستید:"
            )
            return

        db.execute(
            """
            INSERT INTO players (
                game_code, user_id, display_name,
                role, is_alive, score, joined_at
            )
            VALUES (?, ?, ?, NULL, 1, 0, ?)
            """,
            (game_code, user_id, name, datetime.now().isoformat())
        )

        db.execute(
            "DELETE FROM user_states WHERE user_id = ?",
            (user_id,)
        )

    # دریافت اطلاعات بازی برای پیدا کردن مدیر
    game = game_logic.get_game(game_code)

    # اعلان به مدیر؛ اگر خود مدیر عضو شده باشد، پیام تکراری نفرست
    if game and game["admin_id"] != user_id:
        send_message(
            game["admin_id"],
        f"👤 بازیکن <b>{name}</b> عضو بازی شد."
        )
    # تأیید عضویت برای بازیکن
    send_message(
        chat_id,
        f"✅ عالیه {name}! شما با موفقیت عضو بازی <code>{game_code}</code> شدید."
    )



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
