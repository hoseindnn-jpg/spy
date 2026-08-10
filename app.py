import os
import sys
from flask import Flask, request, jsonify

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
    text = message.get("text", "").strip()
    username = message.get("from", {}).get("username", "")
    first_name = message.get("from", {}).get("first_name", "User")
    display_name = f"@{username}" if username else first_name

    if not chat_id or not user_id or not text:
        return

    if text.startswith("/start"):
        parts = text.split(" ", 1)

        if len(parts) > 1 and parts[1].strip():
            game_code = parts[1].strip()
            join_player_to_game(chat_id, user_id, display_name, game_code)
            return

        send_message(
            chat_id,
            "<b>به ربات بازی جاسوس خوش آمدید! 🕵️‍♂️</b>\n\n"
            "برای ساخت بازی جدید روی دکمه زیر بزنید.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "شروع بازی جدید 🎮", "callback_data": "create_new_game"}]
                ]
            }
        )
        return

    if text.startswith("/newgame"):
        create_game_lobby(chat_id)
        return


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
                INSERT INTO games (game_code, status, round_number, is_round_active)
                VALUES (?, ?, 0, 0)
                """,
                (game_code, GAME_STATUS_REGISTERING)
            )

    bot_username = os.getenv("BOT_USERNAME", "").strip()
    if not bot_username:
        send_message(
            chat_id,
            "⚠️ متغیر محیطی <code>BOT_USERNAME</code> تنظیم نشده است."
        )
        return

    join_link = f"https://t.me/{bot_username}?start={game_code}"

    send_message(
        chat_id,
        "🎮 <b>بازی جدید ساخته شد!</b>\n\n"
        f"کد بازی: <code>{game_code}</code>\n\n"
        "لینک زیر را برای بازیکن‌ها بفرست تا یکی‌یکی عضو بازی شوند:\n"
        f"{join_link}\n\n"
        "بعد از اینکه همه عضو شدند، دکمه شروع بازی را بزن.",
        reply_markup={
            "inline_keyboard": [
                [{"text": "شروع بازی 🚀", "callback_data": f"start_game:{game_code}"}],
                [{"text": "نمایش لیست بازیکنان 👥", "callback_data": f"show_players:{game_code}"}]
            ]
        }
    )


def join_player_to_game(user_chat_id, user_id, display_name, game_code):
    game = game_logic.get_game(game_code)
    if not game:
        send_message(
            user_chat_id,
            "⚠️ بازی مورد نظر پیدا نشد یا منقضی شده است."
        )
        return

    if game["status"] != GAME_STATUS_REGISTERING:
        send_message(
            user_chat_id,
            "⚠️ ثبت‌نام این بازی بسته شده است."
        )
        return

    with get_db() as db:
        existing_player = db.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
            (game_code, user_id)
        ).fetchone()

        if existing_player:
            send_message(
                user_chat_id,
                "شما از قبل عضو این بازی هستید."
            )
            return

        db.execute(
            """
            INSERT INTO players (game_code, user_id, display_name, role, is_alive, score)
            VALUES (?, ?, ?, NULL, 1, 0)
            """,
            (game_code, user_id, display_name)
        )

    send_message(
        user_chat_id,
        "🎉 شما با موفقیت عضو بازی شدید. منتظر شروع بازی بمانید."
    )


def handle_callback_query(callback_query):
    query_id = callback_query.get("id")
    user_id = callback_query.get("from", {}).get("id")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = callback_query.get("data", "")

    if not data:
        answer_callback_query(
            query_id,
            "درخواست نامعتبر است.",
            show_alert=True
        )
        return

    if data == "create_new_game":
        create_game_lobby(chat_id)
        answer_callback_query(query_id, "بازی جدید ساخته شد.")
        return

    if data.startswith("start_game:"):
        game_code = data.split(":", 1)[1]
        game = game_logic.get_game(game_code)

        if not game:
            answer_callback_query(
                query_id,
                "بازی پیدا نشد.",
                show_alert=True
            )
            return

        if game["status"] != GAME_STATUS_REGISTERING:
            answer_callback_query(
                query_id,
                "بازی در این وضعیت قابل شروع نیست.",
                show_alert=True
            )
            return

        result = game_logic.start_game_round(game_code, chat_id)
        if not result.get("ok"):
            answer_callback_query(
                query_id,
                result.get("error", "خطا در شروع بازی"),
                show_alert=True
            )
            return

        answer_callback_query(query_id, "بازی با موفقیت شروع شد.")
        edit_message_reply_markup(chat_id, message_id, reply_markup=None)
        return

    if data.startswith("show_players:"):
        game_code = data.split(":", 1)[1]
        players = game_logic.get_players(game_code)

        if not players:
            answer_callback_query(
                query_id,
                "هنوز هیچ بازیکنی عضو نشده است.",
                show_alert=True
            )
            return

        player_list = "\n".join(
            [f"- {player['display_name']}" for player in players]
        )

        send_message(
            chat_id,
            f"👥 <b>بازیکنان ثبت‌نام‌شده:</b>\n{player_list}"
        )
        answer_callback_query(query_id, "لیست بازیکنان ارسال شد.")
        return

    if data.startswith("vote:"):
        parts = data.split(":")
        if len(parts) < 3:
            answer_callback_query(
                query_id,
                "داده رای نامعتبر است.",
                show_alert=True
            )
            return

        game_code = parts[1]
        target_id = int(parts[2])

        current_round = game_logic.get_current_round(game_code)
        if not current_round or current_round["status"] != "voting":
            answer_callback_query(
                query_id,
                "در حال حاضر مرحله رای‌گیری فعال نیست.",
                show_alert=True
            )
            return

        voter = game_logic.get_player_by_user_id(game_code, user_id)
        if not voter or not voter["is_alive"]:
            answer_callback_query(
                query_id,
                "فقط بازیکنان فعال می‌توانند رای دهند.",
                show_alert=True
            )
            return

        game_logic.save_vote(current_round["id"], user_id, target_id)
        answer_callback_query(query_id, "رای شما ثبت شد.")
        return

    answer_callback_query(
        query_id,
        "دکمه ناشناخته است.",
        show_alert=True
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
