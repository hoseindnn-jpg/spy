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

# دیکشنری برای ذخیره کاربرانی که در حال انتخاب اسم مستعار هستن
pending_registrations = {}

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

    # بازی‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS games (
                    game_code TEXT PRIMARY KEY,
                    admin_id INTEGER,
                    status TEXT DEFAULT 'registering',
                    created_at TEXT,
                    round_number INTEGER DEFAULT 0,
                    is_round_active INTEGER DEFAULT 0
                 )''')

    # بازیکنان
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

    # جفت‌کلمات
    c.execute('''CREATE TABLE IF NOT EXISTS word_pairs (
                    id INTEGER PRIMARY KEY,
                    word1 TEXT,
                    word2 TEXT,
                    category TEXT,
                    used_count INTEGER DEFAULT 0
                 )''')

    # دورهای بازی
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

    # رای‌گیری
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

    # تاریخچه بازی
    c.execute('''CREATE TABLE IF NOT EXISTS game_history (
                    id INTEGER PRIMARY KEY,
                    game_code TEXT,
                    round_id INTEGER,
                    player_id INTEGER,
                    action TEXT,
                    details TEXT,
                    created_at TEXT,
                    FOREIGN KEY (game_code) REFERENCES games (game_code),
                    FOREIGN KEY (round_id) REFERENCES rounds (id),
                    FOREIGN KEY (player_id) REFERENCES players (id)
                 )''')

    conn.commit()
    conn.close()

    # بارگذاری کلمات از فایل JSON
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

def get_player_by_user_id(game_code, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, display_name, role, is_alive, score FROM players WHERE game_code = ? AND user_id = ?",
              (game_code, user_id))
    player = c.fetchone()
    conn.close()
    return player

def get_alive_players(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, user_id, display_name, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
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

def get_alive_players_count(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
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

def get_all_players(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, display_name, user_id, role, is_alive, score FROM players WHERE game_code = ?", (game_code,))
    players = c.fetchall()
    conn.close()
    return players

# ================ توزیع نقش‌ها ================
def assign_roles(game_code, players_count):
    """توزیع نقش‌ها بین بازیکنان بر اساس جدول ترکیب"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()
    player_ids = [p[0] for p in players]

    total = len(player_ids)

    # جدول ترکیب نقش‌ها بر اساس تعداد بازیکنان
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

    if total < 3 or total > 20:
        conn.close()
        return None

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

# ================ انتخاب کلمه ================
def get_word_pair():
    """دریافت یک جفت کلمه استفاده نشده"""
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

# ================ توابع کمکی پیشرفته ================
def reset_round(game_code):
    """بازنشانی کامل یک دور (برای شروع دور جدید با همه بازیکنان)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # همه بازیکنان رو زنده کن
    c.execute("UPDATE players SET is_alive = 1, role = 'citizen' WHERE game_code = ?", (game_code,))
    # وضعیت بازی رو به registering برگردون (برای شروع مجدد)
    c.execute("UPDATE games SET status = 'registering', is_round_active = 0 WHERE game_code = ?", (game_code,))
    conn.commit()
    conn.close()

def get_round_scoreboard(game_code):
    """دریافت جدول امتیازات برای یک بازی"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT display_name, score FROM players WHERE game_code = ? ORDER BY score DESC", (game_code,))
    scoreboard = c.fetchall()
    conn.close()
    return scoreboard

def get_role_persian(role):
    """تبدیل نقش انگلیسی به فارسی"""
    return {'citizen': 'شهروند', 'misled': 'گمراه', 'spy': 'جاسوس'}.get(role, role)

def get_round_players_with_roles(game_code, round_id):
    """دریافت لیست بازیکنان و نقش‌هایشان در یک دور خاص"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT p.display_name, p.role 
        FROM players p
        JOIN rounds r ON r.game_code = p.game_code
        WHERE p.game_code = ? AND r.id = ?
    """, (game_code, round_id))
    players = c.fetchall()
    conn.close()
    return players
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

        # هندل دکمه‌ها
        if "callback_query" in update:
            cb = update["callback_query"]
            data = cb["data"]
            chat_id = cb["message"]["chat"]["id"]
            user_id = cb["from"]["id"]

            # شروع بازی جدید از صفحه اصلی
            if data == "new_game":
                # بررسی بازی قبلی
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
                    # حذف بازی قبلی
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("DELETE FROM games WHERE admin_id = ? AND status != 'finished'", (admin_id,))
                    c.execute("DELETE FROM players WHERE game_code IN (SELECT game_code FROM games WHERE admin_id = ?)", (admin_id,))
                    conn.commit()
                    conn.close()
                    start_new_game(chat_id, user_id)

            # پایان ثبت‌نام
            elif data.startswith("finish_register:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()

                c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
                count = c.fetchone()[0]

                if count < 3:
                    send_message(chat_id, f"⚠️ تعداد بازیکنان ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع بازی لازمه.\n\nبازیکنان بیشتری ثبت‌نام کنن.")
                else:
                    # شروع بازی
                    start_game_round(game_code, chat_id)

            # شروع رای‌گیری
            elif data.startswith("start_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])

                # فعال کردن وضعیت رای‌گیری
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
                conn.commit()
                conn.close()

                start_voting_round(game_code, round_id, chat_id)

            # دریافت رای
            elif data.startswith("vote:"):
                parts = data.split(":")
                round_id = int(parts[1])
                voter_id = int(parts[2])
                target_id = int(parts[3])

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()

                # بررسی اینکه رای‌گیری فعال باشد
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

            # پایان رای‌گیری
            elif data.startswith("finish_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])
                finish_voting_round(game_code, round_id, chat_id)

            # شروع دور جدید (بعد از پایان دور)
            elif data.startswith("new_round:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT status FROM games WHERE game_code = ?", (game_code,))
                game_status = c.fetchone()[0]
                conn.close()

                if game_status == 'finished':
                    # همه رو زنده کن و بازی رو از نو شروع کن
                    reset_round(game_code)
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
                    admin = c.fetchone()
                    conn.close()
                    send_message(chat_id, "🔄 دور جدید با همه بازیکنان شروع می‌شود...")
                    start_game_round(game_code, chat_id)
                else:
                    send_message(chat_id, "⚠️ بازی هنوز تمام نشده! صبر کن تا دور فعلی تمام شود.")

            return jsonify({"ok": True})

        # ================ هندل پیام‌های متنی ================
        if "message" not in update:
            return jsonify({"ok": True})

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        user_name = msg["from"].get("first_name", "ناشناس")
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

        # دریافت اسم مستعار (ادامه ثبت‌نام)
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

        return jsonify({"ok": True})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"ok": True})

# ================ توابع اصلی بازی ================
def start_new_game(chat_id, admin_id):
    """شروع یک بازی جدید"""
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
    """شروع یک دور جدید از بازی"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # دریافت تعداد بازیکنان
    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    count = c.fetchone()[0]

    if count < 3:
        send_message(chat_id, f"⚠️ تعداد بازیکنان ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع بازی لازمه.")
        conn.close()
        return

    # توزیع نقش‌ها
    role_counts = assign_roles(game_code, count)

    # انتخاب جفت کلمه
    word_pair = get_word_pair()
    if not word_pair:
        send_message(chat_id, "❌ هیچ جفت کلمه‌ای در دیتابیس وجود نداره! لطفاً ابتدا کلمات رو اضافه کن.")
        conn.close()
        return

    word_pair_id, word1, word2, category = word_pair

    # ثبت دور جدید
    c.execute("UPDATE games SET status = 'playing', round_number = round_number + 1, is_round_active = 0 WHERE game_code = ?",
             (game_code,))
    c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
    round_number = c.fetchone()[0]

    c.execute("INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at) VALUES (?, ?, ?, 'speaking', ?)",
              (game_code, round_number, word_pair_id, datetime.now().isoformat()))
    round_id = c.lastrowid

    c.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))
    conn.commit()

    # ارسال کلمات به بازیکنان
    c.execute("SELECT id, user_id, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()

    for player_id, player_user_id, role in players:
        if role == 'spy':
            word_to_send = "🕵️‍♂️ شما <b>جاسوس</b> هستید!\n\nشما کلمه‌ای نمی‌بینید. سعی کن با دقت به حرف‌های بقیه، کلمه رو حدس بزنی!"
        else:
            word = get_word_for_role(word_pair_id, role)
            word_to_send = f"🔍 کلمه‌ی شما: <b>{word}</b>"

        send_message(player_user_id, f"🎮 <b>دور {round_number} شروع شد!</b>\n\n{word_to_send}\n\nهر نفر به ترتیب یک کلمه مرتبط بگه.")

    conn.close()

    keyboard = {
        "inline_keyboard": [
            [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
        ]
    }
    send_message(chat_id, f"✅ ثبت‌نام تموم شد! {count} نفر عضو شدن.\n\n📊 تعداد نقش‌ها (فقط برای مدیر):\n• شهروندان: {role_counts['citizen']}\n• گمراهان: {role_counts['misled']}\n• جاسوس‌ها: {role_counts['spy']}\n\nکلمات به همه ارسال شد. بعد از اینکه همه صحبت کردن، رای‌گیری رو شروع کن.", keyboard)

def start_voting_round(game_code, round_id, chat_id):
    """شروع رای‌گیری برای یک دور"""
    alive_players = get_alive_players(game_code)

    for player in alive_players:
        player_id, player_user_id, player_name, role = player

        vote_buttons = []
        for target in alive_players:
            if target[0] != player_id:
                vote_buttons.append([{"text": target[2], "callback_data": f"vote:{round_id}:{player_id}:{target[0]}"}])

        keyboard = {"inline_keyboard": vote_buttons}
        send_message(player_user_id, f"🗳️ <b>دور رای‌گیری</b>\n\nبه کسی که فکر می‌کنی جاسوسه رای بده:", keyboard)

    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ پایان رای‌گیری", "callback_data": f"finish_voting:{game_code}:{round_id}"}]
        ]
    }
    send_message(chat_id, "🗳️ رای‌گیری شروع شد!\n\nهمه می‌تونن به یک نفر رای بدن.\nبعد از اینکه همه رای دادن، روی دکمه پایان رای‌گیری کلیک کن.", keyboard)

def finish_voting_round(game_code, round_id, chat_id):
    """پایان رای‌گیری و بررسی نتایج"""
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

    # غیرفعال کردن رای‌گیری
    c.execute("UPDATE games SET is_round_active = 0 WHERE game_code = ?", (game_code,))

    # محاسبه نتایج رای‌گیری
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

    # پیدا کردن بیشترین رای
    max_votes = results[0][1]
    top_candidates = [r[0] for r in results if r[1] == max_votes]

    # حذف بازیکن با بیشترین رای
    eliminated = None
    if len(top_candidates) == 1:
        target_id = top_candidates[0]
        c.execute("UPDATE players SET is_alive = 0 WHERE id = ?", (target_id,))
        c.execute("SELECT display_name, role FROM players WHERE id = ?", (target_id,))
        eliminated = c.fetchone()

        conn.commit()

        # ارسال نتیجه به همه (با نقش فارسی)
        role_persian = get_role_persian(eliminated[1])
        send_message(chat_id, f"⛔️ <b>{eliminated[0]}</b> با {max_votes} رای حذف شد!\n\n🔍 نقش مخفی اون: <b>{role_persian}</b>")

        # به خود فرد هم اعلام کن
        c.execute("SELECT user_id FROM players WHERE id = ?", (target_id,))
        eliminated_user = c.fetchone()
        if eliminated_user:
            send_message(eliminated_user[0], f"⛔️ شما با {max_votes} رای حذف شدید!\n\n🔍 نقش شما: <b>{role_persian}</b>")

    else:
        # تساوی بین چند نفر
        names = []
        for target_id in top_candidates:
            c.execute("SELECT display_name FROM players WHERE id = ?", (target_id,))
            name = c.fetchone()
            if name:
                names.append(name[0])
        
        conn.commit()
        conn.close()
        send_message(chat_id, f"⚠️ رای‌گیری مساوی شد!\n\n{', '.join(names)} هر کدام {max_votes} رای داشتند.\n\nاین افراد باید دوباره یک کلمه بگن و رای‌گیری مجدد انجام بشه.")
        
        # شروع رای‌گیری جدید بین همین افراد
        # (اجرای مجدد رای‌گیری با همان round_id)
        start_voting_round(game_code, round_id, chat_id)
        return

    conn.commit()

    # بررسی شرایط برنده شدن
    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1 AND role = 'citizen'", (game_code,))
    citizen_count = c.fetchone()[0]

    if citizen_count == 0:
        # اضافه کردن امتیاز به گمراهان و جاسوس‌ها
        c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1 AND role IN ('misled', 'spy')", (game_code,))
        winners = c.fetchall()
        for player_id in winners:
            c.execute("UPDATE players SET score = score + 10 WHERE id = ?", (player_id[0],))
        conn.commit()
        conn.close()
        end_game(game_code, chat_id)
        send_message(chat_id, "🎉 گمراهان و جاسوس‌ها برنده شدن!")
        return

    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1 AND role IN ('spy', 'misled')", (game_code,))
    non_citizen_count = c.fetchone()[0]

    if non_citizen_count == 0:
        # اضافه کردن امتیاز به شهروندها
        c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1 AND role = 'citizen'", (game_code,))
        citizens = c.fetchall()
        for player_id in citizens:
            c.execute("UPDATE players SET score = score + 2 WHERE id = ?", (player_id[0],))
        conn.commit()
        conn.close()
        end_game(game_code, chat_id)
        send_message(chat_id, "🎉 شهروندان برنده شدن!")
        return

    # پایان دور (بدون برنده نهایی)
    c.execute("UPDATE games SET status = 'round_finished' WHERE game_code = ?", (game_code,))
    conn.commit()
    conn.close()

    # نمایش نتایج دور
    end_game(game_code, chat_id, round_id)

    # دکمه دور جدید برای مدیر
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔄 شروع دور جدید", "callback_data": f"new_round:{game_code}"}]
        ]
    }
    send_message(chat_id, "🎯 این دور به پایان رسید. برای شروع دور جدید روی دکمه زیر کلیک کن.", keyboard)

def end_game(game_code, chat_id, round_id=None):
    """پایان بازی یا دور و نمایش نتایج"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # دریافت امتیازات و نقش‌ها
    if round_id:
        # نتایج یک دور خاص
        c.execute("""
            SELECT p.display_name, p.role, p.score 
            FROM players p
            JOIN rounds r ON r.game_code = p.game_code
            WHERE p.game_code = ? AND r.id = ?
        """, (game_code, round_id))
    else:
        # نتایج نهایی بازی
        c.execute("""
            SELECT p.display_name, p.role, p.score 
            FROM players p
            WHERE p.game_code = ?
            ORDER BY p.score DESC
        """, (game_code,))
    
    players_data = c.fetchall()
    conn.close()

    if not players_data:
        send_message(chat_id, "⚠️ هیچ داده‌ای برای نمایش وجود ندارد!")
        return

    # ساخت پیام نتایج
    message = "🏁 <b>نتیجه بازی:</b>\n\n"
    
    for display_name, role, score in players_data:
        role_persian = get_role_persian(role)
        message += f"• {display_name} → {role_persian} | امتیاز: {score}\n"
    
    # اضافه کردن برنده
    if players_data:
        winner = players_data[0]
        message += f"\n🏆 <b>برنده: {winner[0]} با {winner[2]} امتیاز!</b>"

    send_message(chat_id, message)
