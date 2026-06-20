from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import requests
from datetime import datetime

app = Flask(__name__)

TOKEN = "8898647964:AAHDany4sKVKfTbjaBFFg2lsQNnyad6gMg4"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_FILE = "spy_game.db"

# دیکشنری‌ها
pending_registrations = {}
pending_spy_guesses = {}

# ================ تابع بررسی عضویت در کانال ================
def is_user_member_of_channel(user_id, channel_username):
    """بررسی می‌کند که آیا کاربر در کانال عضو است یا خیر."""
    try:
        url = f"{BASE_URL}/getChatMember"
        params = {
            "chat_id": f"@{channel_username}",
            "user_id": user_id
        }
        response = requests.get(url, params=params, timeout=10).json()
        if response["ok"]:
            status = response["result"]["status"]
            return status in ["member", "creator", "administrator"]
        else:
            print(f"Error checking membership: {response}")
            return False
    except Exception as e:
        print(f"Exception in is_user_member: {e}")
        return False

# ================ دیتابیس ================
def load_words_from_json():
    """بارگذاری کلمات از فایل JSON به دیتابیس"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        import json
        with open('words.json', 'r', encoding='utf-8') as f:
            words = json.load(f)
        for word_pair in words:
            c.execute("INSERT OR IGNORE INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)",
                      (word_pair['word1'], word_pair['word2'], 'general'))
        conn.commit()
        print(f"✅ {len(words)} جفت‌کلمه از فایل JSON به دیتابیس اضافه شد!")
    except FileNotFoundError:
        print("⚠️ فایل words.json پیدا نشد! لطفاً فایل رو به پروژه اضافه کن.")
    except Exception as e:
        print(f"❌ خطا در بارگذاری کلمات: {e}")
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS games (
                    game_code TEXT PRIMARY KEY,
                    admin_id INTEGER,
                    status TEXT DEFAULT 'registering',
                    created_at TEXT,
                    round_number INTEGER DEFAULT 0,
                    is_round_active INTEGER DEFAULT 0,
                    word_pair_id INTEGER
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY,
                    game_code TEXT,
                    user_id INTEGER,
                    display_name TEXT,
                    role TEXT,
                    is_alive INTEGER DEFAULT 1,
                    score INTEGER DEFAULT 0,
                    joined_at TEXT,
                    FOREIGN KEY (game_code) REFERENCES games (game_code)
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS word_pairs (
                    id INTEGER PRIMARY KEY,
                    word1 TEXT,
                    word2 TEXT,
                    category TEXT,
                    used_count INTEGER DEFAULT 0
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY,
                    game_code TEXT,
                    round_number INTEGER,
                    word_pair_id INTEGER,
                    status TEXT DEFAULT 'speaking',
                    started_at TEXT,
                    ended_at TEXT,
                    FOREIGN KEY (game_code) REFERENCES games (game_code),
                    FOREIGN KEY (word_pair_id) REFERENCES word_pairs (id)
                 )''')

    c.execute('''CREATE TABLE IF NOT EXISTS votes (
                    id INTEGER PRIMARY KEY,
                    round_id INTEGER,
                    voter_id INTEGER,
                    target_id INTEGER,
                    voted_at TEXT,
                    FOREIGN KEY (round_id) REFERENCES rounds (id),
                    FOREIGN KEY (voter_id) REFERENCES players (id),
                    FOREIGN KEY (target_id) REFERENCES players (id)
                 )''')

    conn.commit()
    conn.close()
    load_words_from_json()

init_db()

# ================ توابع کمکی ================
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def send_message(chat_id, text, reply_markup=None, disable_web_page_preview=False):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    if disable_web_page_preview:
        data["disable_web_page_preview"] = True
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=data, timeout=10)
    except Exception as e:
        print(f"Error sending: {e}")

def get_alive_players(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, user_id, display_name, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()
    conn.close()
    return players

def get_all_players(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, user_id, display_name, role, score FROM players WHERE game_code = ?", (game_code,))
    players = c.fetchall()
    conn.close()
    return players

def get_players_count(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_game_status(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT status FROM games WHERE game_code = ?", (game_code,))
    status = c.fetchone()
    conn.close()
    return status[0] if status else None

def get_role_persian(role):
    return {'citizen': 'شهروند', 'misled': 'گمراه', 'spy': 'جاسوس'}.get(role, role)

def get_game_word_pair(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT word1, word2 FROM word_pairs wp JOIN games g ON g.word_pair_id = wp.id WHERE g.game_code = ?", (game_code,))
    result = c.fetchone()
    conn.close()
    return result
# ================ توزیع نقش و کلمه ================
def assign_roles(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()
    player_ids = [p[0] for p in players]
    total = len(player_ids)

    if total < 3 or total > 20:
        conn.close()
        return None

    role_mapping = {
        3: {'spy': 0, 'misled': 1, 'citizen': 2},
        4: {'spy': 0, 'misled': 1, 'citizen': 3},
        5: {'spy': 1, 'misled': 1, 'citizen': 3},
        6: {'spy': 1, 'misled': 1, 'citizen': 4},
        7: {'spy': 1, 'misled': 2, 'citizen': 4},
        8: {'spy': 1, 'misled': 2, 'citizen': 5},
        9: {'spy': 1, 'misled': 3, 'citizen': 5},
        10: {'spy': 1, 'misled': 3, 'citizen': 6},
        11: {'spy': 2, 'misled': 3, 'citizen': 6},
        12: {'spy': 2, 'misled': 3, 'citizen': 7},
        13: {'spy': 2, 'misled': 4, 'citizen': 7},
        14: {'spy': 2, 'misled': 4, 'citizen': 8},
        15: {'spy': 2, 'misled': 5, 'citizen': 8},
        16: {'spy': 2, 'misled': 5, 'citizen': 9},
        17: {'spy': 3, 'misled': 5, 'citizen': 9},
        18: {'spy': 3, 'misled': 5, 'citizen': 10},
        19: {'spy': 3, 'misled': 6, 'citizen': 10},
        20: {'spy': 3, 'misled': 6, 'citizen': 11},
    }

    roles_config = role_mapping.get(total)
    if not roles_config:
        conn.close()
        return None

    spy_count = roles_config['spy']
    misled_count = roles_config['misled']
    citizen_count = roles_config['citizen']

    roles = ['citizen'] * citizen_count + ['misled'] * misled_count + ['spy'] * spy_count
    random.shuffle(roles)

    for player_id, role in zip(player_ids, roles):
        c.execute("UPDATE players SET role = ? WHERE id = ?", (role, player_id))

    conn.commit()
    conn.close()
    return {'citizen': citizen_count, 'misled': misled_count, 'spy': spy_count}

def get_word_pair():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, word1, word2, category FROM word_pairs ORDER BY used_count ASC, RANDOM() LIMIT 1")
    pair = c.fetchone()
    conn.close()
    return pair

def get_word_for_role(word_pair_id, role):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT word1, word2 FROM word_pairs WHERE id = ?", (word_pair_id,))
    word1, word2 = c.fetchone()
    conn.close()
    if role == 'citizen':
        return word1
    elif role == 'misled':
        return word2
    else:
        return None

# ================ امتیازدهی ================
def add_score_to_team(game_code, role, points):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE players SET score = score + ? WHERE game_code = ? AND role = ?",
              (points, game_code, role))
    conn.commit()
    conn.close()

# ================ توابع اصلی بازی ================
def start_new_game(chat_id, admin_id):
    game_code = generate_code()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO games (game_code, admin_id, status, created_at, is_round_active) VALUES (?, ?, 'registering', ?, 0)",
              (game_code, admin_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    bot_info = requests.get(f"{BASE_URL}/getMe").json()
    bot_username = bot_info['result']['username']
    register_link = f"https://t.me/{bot_username}?start=register_{game_code}"

    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ پایان ثبت‌نام", "callback_data": f"finish_register:{game_code}"}]
        ]
    }
    send_message(chat_id,
                 f"🎮 بازی جاسوس جدید ساخته شد!\n\n"
                 f"📋 کد بازی: <code>{game_code}</code>\n\n"
                 f"🔗 لینک ثبت‌نام:\n{register_link}\n\n"
                 f"این لینک رو برای دوستان بفرست تا بتونن عضو بشن.\n\n"
                 f"بعد از ثبت‌نام همه، روی دکمه «پایان ثبت‌نام» کلیک کن.",
                 keyboard)

def start_game_round(game_code, chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # پاک کردن آرای قبلی
    c.execute("DELETE FROM votes WHERE round_id IN (SELECT id FROM rounds WHERE game_code = ?)", (game_code,))

    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    count = c.fetchone()[0]

    if count < 3:
        send_message(chat_id, f"⚠️ تعداد بازیکنان زنده ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع دور لازمه.")
        conn.close()
        return

    role_counts = assign_roles(game_code)
    if not role_counts:
        conn.close()
        return

    word_pair = get_word_pair()
    if not word_pair:
        send_message(chat_id, "❌ هیچ جفت کلمه‌ای در دیتابیس وجود نداره! لطفاً ابتدا کلمات رو اضافه کن.")
        conn.close()
        return

    word_pair_id, word1, word2, category = word_pair

    c.execute("UPDATE games SET status = 'playing', round_number = round_number + 1, is_round_active = 0, word_pair_id = ? WHERE game_code = ?",
              (word_pair_id, game_code))
    c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
    round_number = c.fetchone()[0]

    c.execute("INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at) VALUES (?, ?, ?, 'speaking', ?)",
              (game_code, round_number, word_pair_id, datetime.now().isoformat()))
    round_id = c.lastrowid

    c.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))
    conn.commit()

    # ارسال کلمات به بازیکنان زنده
    c.execute("SELECT id, user_id, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()

    for player_id, player_user_id, role in players:
        if role == 'spy':
            word_to_send = "🕵️‍♂️ شما <b>جاسوس</b> هستید!\n\nشما کلمه‌ای نمی‌بینید. سعی کن با دقت به حرف‌های بقیه، کلمه رو حدس بزنی!"
        else:
            word = get_word_for_role(word_pair_id, role)
            word_to_send = f"🔍 کلمه‌ی شما: <b>{word}</b>"

        send_message(player_user_id, f"🎮 <b>دور {round_number} شروع شد!</b>\n\n{word_to_send}\n\nهر نفر به ترتیب یک کلمه مرتبط بگه.")

    # انتخاب و اعلام نفر اول
    alive_players = get_alive_players(game_code)
    if alive_players:
        first_player = random.choice(alive_players)
        first_player_name = first_player[2]
        for player in alive_players:
            send_message(player[1], f"🗣️ نفر اول برای صحبت کردن: <b>{first_player_name}</b>\n\nلطفاً یک کلمه مرتبط با کلمه‌ی خود بگید.")

    conn.close()

    keyboard = {
        "inline_keyboard": [
            [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
        ]
    }
    send_message(chat_id, f"✅ دور {round_number} شروع شد! {count} نفر در بازی هستن.\n\n📊 تعداد نقش‌ها (فقط برای مدیر):\n• شهروندان: {role_counts['citizen']}\n• گمراهان: {role_counts['misled']}\n• جاسوس‌ها: {role_counts['spy']}\n\nکلمات به همه ارسال شد. بعد از اینکه همه صحبت کردن، رای‌گیری رو شروع کن.", keyboard)
   # ================ مسیرهای اصلی ================
@app.route('/')
def home():
    return "ربات جاسوس پیشرفته فعال است!"

@app.route('/telegram', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update:
            return jsonify({"ok": True})

        # ---- بخش بررسی عضویت ----
        user_id = None
        chat_id = None

        if "message" in update:
            user_id = update["message"]["from"]["id"]
            chat_id = update["message"]["chat"]["id"]
        elif "callback_query" in update:
            user_id = update["callback_query"]["from"]["id"]
            chat_id = update["callback_query"]["message"]["chat"]["id"]
        else:
            return jsonify({"ok": True})

        CHANNEL_USERNAME = "nishgoonnn"

        if not is_user_member_of_channel(user_id, CHANNEL_USERNAME):
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔗 عضویت در کانال", "url": "https://t.me/nishgoonnn"}],
                    [{"text": "✅ عضو شدم", "callback_data": "check_membership"}]
                ]
            }
            send_message(
                chat_id,
                "🎭 <b>برای استفاده از ربات، ابتدا باید عضو کانال ما شوید!</b>\n\n"
                "📢 در کانال «مرجع بازی های گروهی و خانوادگی» جدیدترین بازی‌ها و آموزش‌ها رو ببینید.\n\n"
                "👇 لطفاً روی دکمه زیر کلیک کنید و سپس «عضو شدم» را بزنید.",
                reply_markup=keyboard
            )
            return jsonify({"ok": True})
        # --------------------------------

        # هندل دکمه‌ها
        if "callback_query" in update:
            cb = update["callback_query"]
            data = cb["data"]
            chat_id = cb["message"]["chat"]["id"]
            user_id = cb["from"]["id"]

            # بررسی مجدد عضویت برای دکمه‌ها
            if data == "check_membership":
                if is_user_member_of_channel(user_id, CHANNEL_USERNAME):
                    send_message(chat_id, "✅ عضویت شما تأیید شد! حالا می‌توانید از ربات استفاده کنید.")
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🎮 شروع بازی جدید", "callback_data": "new_game"}]
                        ]
                    }
                    send_message(chat_id, "🕵️‍♂️ به ربات خوش آمدید! لطفاً یکی از گزینه‌ها را انتخاب کنید:", keyboard)
                else:
                    send_message(chat_id, "❌ شما هنوز عضو کانال نشدید! لطفاً ابتدا روی دکمه «عضویت در کانال» کلیک کنید و سپس «عضو شدم» را بزنید.")
                return jsonify({"ok": True})

            # شروع بازی جدید
            if data == "new_game":
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT game_code FROM games WHERE status != 'finished' AND admin_id = ?", (user_id,))
                existing_game = c.fetchone()
                conn.close()

                if existing_game:
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🗑️ حذف بازی قبلی و شروع جدید", "callback_data": f"confirm_new_game:{user_id}"}],
                            [{"text": "🔙 بازگشت", "callback_data": "back_to_menu"}]
                        ]
                    }
                    send_message(chat_id, "⚠️ شما یک بازی ناتمام دارید. آیا می‌خواهید آن را حذف کرده و بازی جدیدی شروع کنید؟", keyboard)
                else:
                    start_new_game(chat_id, user_id)

            elif data.startswith("confirm_new_game:"):
                admin_id = int(data.split(":")[1])
                if user_id == admin_id:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM games WHERE admin_id = ? AND status != 'finished'", (admin_id,))
                    c.execute("DELETE FROM players WHERE game_code IN (SELECT game_code FROM games WHERE admin_id = ?)", (admin_id,))
                    conn.commit()
                    conn.close()
                    start_new_game(chat_id, user_id)

            elif data.startswith("finish_register:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
                count = c.fetchone()[0]

                if count < 3:
                    send_message(chat_id, f"⚠️ تعداد بازیکنان ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع بازی لازمه.\n\nبازیکنان بیشتری ثبت‌نام کنن.")
                else:
                    start_game_round(game_code, chat_id)

            elif data.startswith("start_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
                conn.commit()
                conn.close()

                alive_players = get_alive_players(game_code)
                for player in alive_players:
                    player_id, player_user_id, player_name, role = player
                    vote_buttons = []
                    for target in alive_players:
                        if target[0] != player_id:
                            vote_buttons.append([{"text": target[2], "callback_data": f"vote:{round_id}:{player_id}:{target[0]}"}])
                    keyboard = {"inline_keyboard": vote_buttons}
                    send_message(player_user_id, f"🗳️ <b>دور رای‌گیری</b>\n\nبه کسی که فکر می‌کنی جاسوسه رای بده (می‌تونی رای خودتو عوض کنی):", keyboard)

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "✅ پایان رای‌گیری", "callback_data": f"finish_voting:{game_code}:{round_id}"}]
                    ]
                }
                send_message(chat_id, "🗳️ رای‌گیری شروع شد!\n\nهمه می‌تونن به یک نفر رای بدن.\nبعد از اینکه همه رای دادن، روی دکمه پایان رای‌گیری کلیک کن.", keyboard)

            elif data.startswith("vote:"):
                parts = data.split(":")
                round_id = int(parts[1])
                voter_id = int(parts[2])
                target_id = int(parts[3])

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT is_round_active FROM games WHERE game_code = (SELECT game_code FROM rounds WHERE id = ?)", (round_id,))
                is_active = c.fetchone()
                if not is_active or is_active[0] == 0:
                    send_message(chat_id, "❌ رای‌گیری به پایان رسیده یا غیرفعال است!")
                    conn.close()
                    return jsonify({"ok": True})

                c.execute("SELECT id FROM votes WHERE round_id = ? AND voter_id = ?", (round_id, voter_id))
                existing = c.fetchone()
                if existing:
                    c.execute("UPDATE votes SET target_id = ?, voted_at = ? WHERE id = ?",
                              (target_id, datetime.now().isoformat(), existing[0]))
                else:
                    c.execute("INSERT INTO votes (round_id, voter_id, target_id, voted_at) VALUES (?, ?, ?, ?)",
                              (round_id, voter_id, target_id, datetime.now().isoformat()))

                conn.commit()
                conn.close()
                send_message(chat_id, "✅ رای شما ثبت شد!")

            elif data.startswith("finish_voting:") or data.startswith("finish_tie_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])
                finish_voting_round(game_code, round_id, chat_id)

            elif data.startswith("new_round:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("UPDATE players SET is_alive = 1 WHERE game_code = ?", (game_code,))
                c.execute("UPDATE games SET status = 'playing' WHERE game_code = ?", (game_code,))
                conn.commit()
                conn.close()
                send_message(chat_id, "🔄 دور جدید با همه بازیکنان شروع می‌شود...")
                start_game_round(game_code, chat_id)

            return jsonify({"ok": True})

        # ================ هندل پیام‌های متنی ================
        if "message" not in update:
            return jsonify({"ok": True})

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        text = msg.get("text", "").strip()

        # شروع ربات
        if text == "/start":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎮 شروع بازی جدید", "callback_data": "new_game"}]
                ]
            }
            send_message(chat_id, "🕵️‍♂️ <b>به ربات جاسوس پیشرفته خوش اومدی!</b>\n\nیه بازی گروهی جذاب برای کشف جاسوس بین دوستان.", keyboard)
            return jsonify({"ok": True})

        # ثبت‌نام در بازی
        if text.startswith("/start register_"):
            game_code = text.replace("/start register_", "").strip()
            game_status = get_game_status(game_code)

            if game_status != 'registering':
                send_message(chat_id, "❌ این بازی در حال ثبت‌نام نیست یا تموم شده!")
                return jsonify({"ok": True})

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id FROM players WHERE game_code = ? AND user_id = ?", (game_code, user_id))
            existing = c.fetchone()
            conn.close()

            if existing:
                send_message(chat_id, "✅ شما قبلاً در این بازی ثبت‌نام کردید!")
                return jsonify({"ok": True})

            pending_registrations[user_id] = game_code
            send_message(chat_id, "👤 لطفاً یک <b>اسم مستعار</b> برای خودت انتخاب کن:\n\n(این اسم توی بازی نمایش داده میشه)\n\n✏️ فقط اسم رو تایپ کن و بفرست.")
            return jsonify({"ok": True})

        # دریافت اسم مستعار
        if user_id in pending_registrations:
            game_code = pending_registrations[user_id]

            if len(text.strip()) < 2:
                send_message(chat_id, "❌ اسم مستعار باید حداقل ۲ کاراکتر باشه. لطفاً دوباره تلاش کن.")
                return jsonify({"ok": True})

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT display_name FROM players WHERE game_code = ? AND display_name = ?", (game_code, text.strip()))
            duplicate = c.fetchone()

            if duplicate:
                send_message(chat_id, f"❌ اسم مستعار «{text.strip()}» قبلاً توسط کس دیگه‌ای انتخاب شده! لطفاً اسم دیگه‌ای انتخاب کن.")
                conn.close()
                return jsonify({"ok": True})

            c.execute("""
                INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
                VALUES (?, ?, ?, 'citizen', 1, 0, ?)
            """, (game_code, user_id, text.strip(), datetime.now().isoformat()))
            conn.commit()

            del pending_registrations[user_id]

            send_message(chat_id, f"✅ شما با اسم مستعار «{text.strip()}» در بازی ثبت‌نام شدید!\n\nمنتظر شروع بازی توسط مدیر باشید.")

            c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
            admin = c.fetchone()
            conn.close()

            if admin:
                send_message(admin[0], f"🔔 کاربر جدید با اسم «{text.strip()}» به بازی پیوست.\n\nتعداد بازیکنان فعلی: {get_players_count(game_code)} نفر")

            return jsonify({"ok": True})

        # بررسی حدس جاسوس
        if user_id in pending_spy_guesses:
            result = check_spy_guess(user_id, text)
            if result is not None:
                return jsonify({"ok": True})

        return jsonify({"ok": True})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"ok": True})

# ================ توابع مدیریت رای‌گیری و پایان بازی ================
def finish_voting_round(game_code, round_id, chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    alive_players = get_alive_players(game_code)
    total_players = len(alive_players)

    c.execute("SELECT COUNT(DISTINCT voter_id) FROM votes WHERE round_id = ?", (round_id,))
    voted_count = c.fetchone()[0]

    if voted_count < total_players:
        send_message(chat_id, f"⚠️ فقط {voted_count} نفر از {total_players} نفر رای دادن!\n\nهمه باید رای بدن. صبر کن تا همه رای بدن.")
        conn.close()
        return

    c.execute("UPDATE games SET is_round_active = 0 WHERE game_code = ?", (game_code,))

    c.execute("""
        SELECT target_id, COUNT(*) as vote_count
        FROM votes
        WHERE round_id = ?
        GROUP BY target_id
        ORDER BY vote_count DESC
    """, (round_id,))
    results = c.fetchall()

    if not results:
        send_message(chat_id, "❌ هیچ رایی ثبت نشده!")
        conn.close()
        return

    max_votes = results[0][1]
    top_candidates = [r[0] for r in results if r[1] == max_votes]

    if len(top_candidates) == 1:
        target_id = top_candidates[0]
        c.execute("SELECT display_name, role FROM players WHERE id = ?", (target_id,))
        eliminated = c.fetchone()

        if eliminated:
            eliminated_name, eliminated_role = eliminated
            c.execute("UPDATE players SET is_alive = 0 WHERE id = ?", (target_id,))
            conn.commit()

            role_persian = get_role_persian(eliminated_role)
            send_message(chat_id, f"⛔️ <b>{eliminated_name}</b> با {max_votes} رای حذف شد!\n\n🔍 نقش مخفی اون: <b>{role_persian}</b>")

            c.execute("SELECT user_id FROM players WHERE id = ?", (target_id,))
            eliminated_user = c.fetchone()
            if eliminated_user:
                send_message(eliminated_user[0], f"⛔️ شما با {max_votes} رای حذف شدید!\n\n🔍 نقش شما: <b>{role_persian}</b>")

            if eliminated_role == 'spy':
                conn.close()
                handle_spy_elimination(game_code, target_id, chat_id)
                return

            c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1 AND role = 'citizen'", (game_code,))
            citizen_count = c.fetchone()[0]

            if citizen_count == 0:
                add_score_to_team(game_code, 'misled', 10)
                add_score_to_team(game_code, 'spy', 6)
                conn.commit()
                conn.close()
                end_game(game_code, chat_id)
                send_message(chat_id, "🎉 گمراهان و جاسوس‌ها برنده شدن!")
                return

            c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1 AND role IN ('spy', 'misled')", (game_code,))
            non_citizen_count = c.fetchone()[0]

            if non_citizen_count == 0:
                add_score_to_team(game_code, 'citizen', 2)
                conn.commit()
                conn.close()
                end_game(game_code, chat_id)
                send_message(chat_id, "🎉 شهروندان برنده شدن!")
                return

            c.execute("UPDATE games SET status = 'round_finished' WHERE game_code = ?", (game_code,))
            conn.commit()
            conn.close()

            end_game(game_code, chat_id, round_id)

            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 شروع دور جدید", "callback_data": f"new_round:{game_code}"}]
                ]
            }
            send_message(chat_id, "🎯 این دور به پایان رسید. برای شروع دور جدید روی دکمه زیر کلیک کن.", keyboard)

    else:
        names = []
        tied_player_ids = []
        for target_id in top_candidates:
            c.execute("SELECT display_name FROM players WHERE id = ?", (target_id,))
            name = c.fetchone()
            if name:
                names.append(name[0])
                tied_player_ids.append(target_id)

        conn.commit()
        conn.close()

        send_message(chat_id, f"⚠️ رای‌گیری مساوی شد!\n\n{', '.join(names)} هر کدام {max_votes} رای داشتند.\n\nاین افراد باید دوباره یک کلمه بگن و رای‌گیری مجدد انجام بشه.")
        start_tie_voting_round(game_code, round_id, tied_player_ids, chat_id)

def start_tie_voting_round(game_code, round_id, tied_player_ids, chat_id):
    alive_players = get_alive_players(game_code)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
    conn.commit()
    conn.close()

    for player in alive_players:
        player_id, player_user_id, player_name, role = player
        vote_buttons = []
        for target in alive_players:
            if target[0] != player_id and target[0] in tied_player_ids:
                vote_buttons.append([{"text": target[2], "callback_data": f"vote:{round_id}:{player_id}:{target[0]}"}])

        keyboard = {"inline_keyboard": vote_buttons}
        send_message(player_user_id, f"🗳️ <b>رای‌گیری تساوی</b>\n\nبه یکی از این افراد رای بده:\n{', '.join([p[2] for p in alive_players if p[0] in tied_player_ids])}", keyboard)

    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ پایان رای‌گیری تساوی", "callback_data": f"finish_tie_voting:{game_code}:{round_id}"}]
        ]
    }
    send_message(chat_id, f"🗳️ رای‌گیری تساوی شروع شد!\n\nفقط بین این افراد رای بدید: {', '.join([p[2] for p in alive_players if p[0] in tied_player_ids])}", keyboard)

def handle_spy_elimination(game_code, player_id, chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, display_name FROM players WHERE id = ? AND game_code = ?", (player_id, game_code))
    spy = c.fetchone()

    if not spy:
        conn.close()
        return

    spy_user_id, spy_name = spy
    word_pair = get_game_word_pair(game_code)

    if not word_pair:
        conn.close()
        return

    main_word = word_pair[0]

    pending_spy_guesses[spy_user_id] = {
        'game_code': game_code,
        'main_word': main_word,
        'player_id': player_id,
        'spy_name': spy_name,
        'chat_id': chat_id
    }

    send_message(spy_user_id, f"🔍 شما به عنوان جاسوس حذف شدید!\n\nبرای نجات تیم جاسوس‌ها، کلمه‌ی اصلی رو حدس بزن:\n\n✏️ فقط کلمه رو تایپ کن و بفرست.\n\n⚠️ اگه درست حدس بزنی، جاسوس‌ها برنده می‌شن!")
    conn.close()

def check_spy_guess(user_id, guessed_word):
    if user_id not in pending_spy_guesses:
        return None

    data = pending_spy_guesses[user_id]
    game_code = data['game_code']
    main_word = data['main_word']
    chat_id = data['chat_id']

    del pending_spy_guesses[user_id]

    guessed_clean = guessed_word.strip().lower()
    main_clean = main_word.strip().lower()

    if guessed_clean == main_clean:
        add_score_to_team(game_code, 'spy', 6)
        send_message(user_id, f"✅ <b>درست حدس زدی!</b>\n\nکلمه اصلی: {main_word}\n\n🎉 تیم جاسوس‌ها برنده شدن!")

        all_players = get_all_players(game_code)
        for player in all_players:
            if player[1] != user_id:
                send_message(player[1], f"🎉 جاسوس کلمه رو درست حدس زد! تیم جاسوس‌ها برنده شدن!")

        end_game(game_code, chat_id)
        return True
    else:
        send_message(user_id, f"❌ <b>اشتباه حدس زدی!</b>\n\nکلمه‌ای که گفتی: {guessed_word}\n\nشما حذف می‌شوید و بازی ادامه پیدا می‌کند.")
        return False

def end_game(game_code, chat_id, round_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if round_id:
        c.execute("""
            SELECT p.display_name, p.role, p.score
            FROM players p
            JOIN rounds r ON r.game_code = p.game_code
            WHERE p.game_code = ? AND r.id = ?
        """, (game_code, round_id))
    else:
        c.execute("""
            SELECT display_name, role, score
            FROM players
            WHERE game_code = ?
            ORDER BY score DESC
        """, (game_code,))

    players_data = c.fetchall()
    conn.close()

    if not players_data:
        send_message(chat_id, "⚠️ هیچ داده‌ای برای نمایش وجود ندارد!")
        return

    message = "🏁 <b>نتیجه بازی:</b>\n\n"
    for display_name, role, score in players_data:
        role_persian = get_role_persian(role)
        message += f"• {display_name} → {role_persian} | امتیاز: {score}\n"

    if players_data:
        winner = players_data[0]
        message += f"\n🏆 <b>برنده: {winner[0]} با {winner[2]} امتیاز!</b>"

    all_players = get_all_players(game_code)
    for player in all_players:
        send_message(player[1], message)

    send_message(chat_id, message)

# ================ مدیریت کلمات ================
@app.route('/add_words')
def add_words_page():
    return """
    <h1>افزودن جفت‌کلمات</h1>
    <form action="/add_words_submit" method="POST">
        <input type="text" name="word1" placeholder="کلمه اول"><br>
        <input type="text" name="word2" placeholder="کلمه دوم"><br>
        <input type="text" name="category" placeholder="دسته‌بندی (اختیاری)"><br>
        <button type="submit">افزودن</button>
    </form>
    """

@app.route('/add_words_submit', methods=['POST'])
def add_words_submit():
    word1 = request.form.get('word1')
    word2 = request.form.get('word2')
    category = request.form.get('category', 'general')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)", (word1, word2, category))
    conn.commit()
    conn.close()

    return "جفت‌کلمه با موفقیت اضافه شد!"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 
