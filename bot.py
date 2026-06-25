from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import requests
from datetime import datetime
import time

app = Flask(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_FILE = "spy_game.db"

# دیکشنری‌ها
pending_registrations = {}
pending_spy_guesses = {}
pending_single_player_names = {}

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
def init_db():
    """ایجاد جداول دیتابیس و افزودن کلمات پیش‌فرض"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    try:
        # ایجاد جداول
        c.execute('''CREATE TABLE IF NOT EXISTS games (
                        game_code TEXT PRIMARY KEY,
                        admin_id INTEGER,
                        status TEXT DEFAULT 'registering',
                        created_at TEXT,
                        round_number INTEGER DEFAULT 0,
                        is_round_active INTEGER DEFAULT 0,
                        word_pair_id INTEGER,
                        game_mode TEXT DEFAULT 'multi'
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
        print("✅ جداول دیتابیس با موفقیت ایجاد شدند.")

        # ================ افزودن کلمات پیش‌فرض ================
        default_pairs = [
            ("سینما", "تئاتر"), ("مدرسه", "دانشگاه"), ("رستوران", "کافه"),
            ("کتاب", "مجله"), ("دریا", "اقیانوس"), ("کوه", "تپه"),
            ("ماشین", "موتور"), ("گربه", "سگ"), ("پیتزا", "ساندویچ"),
            ("شیرینی", "کیک"), ("باغ", "جنگل"), ("شهر", "روستا"),
            ("هواپیما", "هلیکوپتر"), ("قطار", "اتوبوس"), ("کفش", "چکمه"),
            ("کلاه", "عینک"), ("شب", "روز"), ("تابستان", "زمستان"),
            ("عشق", "دوستی"), ("انرژی", "قدرت"), ("پارک", "باغ وحش"),
            ("آشپزخانه", "رستوران"), ("ماهی", "پرنده"), ("صندلی", "میز"),
            ("تلفن", "تبلت"), ("لباس", "کت"), ("برف", "باران"),
            ("آفتاب", "ماه"), ("تخت", "مبل"), ("چای", "قهوه"),
            ("نان", "کیک"), ("لبخند", "خنده"), ("گریه", "ناراحتی"),
            ("سفر", "مهاجرت"), ("خرید", "فروش"), ("مهمانی", "جشن"),
            ("عروسی", "نامزدی"), ("بیمارستان", "درمانگاه"), ("پزشک", "پرستار"),
            ("معلم", "استاد"), ("دانشجو", "دانش‌آموز"), ("چراغ", "لامپ"),
            ("فرش", "موکت"), ("تخم‌مرغ", "مرغ"), ("شیر", "ماست"),
            ("نانوایی", "سوپرمارکت"), ("باشگاه", "سالن ورزشی"), ("قلم", "مداد"),
            ("کیف", "کوله‌پشتی"), ("کودک", "نوجوان"), ("پلیس", "دزد"),
            ("دکتر", "بیمار"), ("آشپز", "گارسون"), ("مهندس", "معمار"),
            ("خلبان", "مهماندار"), ("غواص", "کشتی‌گیر"), ("کشاورز", "دامدار")
        ]

        for word1, word2 in default_pairs:
            c.execute(
                "INSERT OR IGNORE INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)",
                (word1, word2, 'general')
            )

        conn.commit()
        print(f"✅ {len(default_pairs)} جفت‌کلمه پیش‌فرض به دیتابیس اضافه شد.")

    except Exception as e:
        print(f"❌ خطا در ایجاد دیتابیس: {e}")
    finally:
        conn.close()

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

def edit_message_reply_markup(chat_id, message_id, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    if reply_markup is not None:
        data["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/editMessageReplyMarkup", json=data, timeout=10)
    except Exception as e:
        print(f"Error editing reply markup: {e}")

def answer_callback_query(callback_query_id, text=None, show_alert=False):
    data = {
        "callback_query_id": callback_query_id,
        "show_alert": show_alert
    }
    if text:
        data["text"] = text
    try:
        requests.post(f"{BASE_URL}/answerCallbackQuery", json=data, timeout=10)
    except Exception as e:
        print(f"Error answering callback query: {e}")

def get_alive_players(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id, user_id, display_name, role FROM players WHERE game_code = ? AND is_alive = 1",
            (game_code,)
        )
        players = c.fetchall()
        return players
    except Exception as e:
        print(f"Error in get_alive_players: {e}")
        return []
    finally:
        conn.close()

def get_all_players(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id, user_id, display_name, role, score FROM players WHERE game_code = ?",
            (game_code,)
        )
        players = c.fetchall()
        return players
    except Exception as e:
        print(f"Error in get_all_players: {e}")
        return []
    finally:
        conn.close()

def get_players_count(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
        count = c.fetchone()[0]
        return count
    except Exception as e:
        print(f"Error in get_players_count: {e}")
        return 0
    finally:
        conn.close()

def get_game_status(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT status FROM games WHERE game_code = ?", (game_code,))
        status = c.fetchone()
        return status[0] if status else None
    except Exception as e:
        print(f"Error in get_game_status: {e}")
        return None
    finally:
        conn.close()

def get_game_mode(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT game_mode FROM games WHERE game_code = ?", (game_code,))
        mode = c.fetchone()
        return mode[0] if mode else 'multi'
    except Exception as e:
        print(f"Error in get_game_mode: {e}")
        return 'multi'
    finally:
        conn.close()

def get_role_persian(role):
    return {'citizen': 'شهروند', 'misled': 'گمراه', 'spy': 'جاسوس'}.get(role, role)

def get_game_word_pair(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT word1, word2
            FROM word_pairs wp
            JOIN games g ON g.word_pair_id = wp.id
            WHERE g.game_code = ?
        """, (game_code,))
        result = c.fetchone()
        return result
    except Exception as e:
        print(f"Error in get_game_word_pair: {e}")
        return None
    finally:
        conn.close()

# ================ توزیع نقش و کلمه ================
def assign_roles(game_code):
    """توزیع نقش‌ها بین بازیکنان زنده"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
        players = c.fetchall()
        player_ids = [p[0] for p in players]
        total = len(player_ids)

        print(f"🔍 تعداد بازیکنان برای توزیع نقش: {total}")

        if total < 3:
            print(f"❌ تعداد بازیکنان ({total}) کمتر از حداقل (۳) است!")
            return None

        if total > 20:
            print(f"❌ تعداد بازیکنان ({total}) بیشتر از حداکثر (۲۰) است!")
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
            print(f"❌ ترکیب نقش برای {total} نفر یافت نشد!")
            return None

        spy_count = roles_config['spy']
        misled_count = roles_config['misled']
        citizen_count = roles_config['citizen']

        roles = (
            ['spy'] * spy_count +
            ['misled'] * misled_count +
            ['citizen'] * citizen_count
        )
        random.shuffle(roles)

        for player_id, role in zip(player_ids, roles):
            c.execute(
                "UPDATE players SET role = ? WHERE id = ? AND game_code = ?",
                (role, player_id, game_code)
            )

        conn.commit()

        c.execute("""
            SELECT role, COUNT(*)
            FROM players
            WHERE game_code = ? AND is_alive = 1
            GROUP BY role
        """, (game_code,))
        assigned = c.fetchall()
        print(f"✅ نقش‌ها تخصیص یافت: {assigned}")

        return roles_config

    except Exception as e:
        print(f"Error in assign_roles: {e}")
        return None
    finally:
        conn.close()

def get_word_pair():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, word1, word2
            FROM word_pairs
            ORDER BY used_count ASC, RANDOM()
            LIMIT 1
        """)
        return c.fetchone()
    except Exception as e:
        print(f"Error in get_word_pair: {e}")
        return None
    finally:
        conn.close()

def get_word_for_role(word_pair_id, role):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT word1, word2 FROM word_pairs WHERE id = ?", (word_pair_id,))
        result = c.fetchone()
        if not result:
            return None

        word1, word2 = result
        if role == 'citizen':
            return word1
        if role == 'misled':
            return word2
        return None
    except Exception as e:
        print(f"Error in get_word_for_role: {e}")
        return None
    finally:
        conn.close()

def add_score_to_team(game_code, role, points):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE players
            SET score = score + ?
            WHERE game_code = ? AND role = ?
        """, (points, game_code, role))
        conn.commit()
    except Exception as e:
        print(f"Error in add_score_to_team: {e}")
    finally:
        conn.close()

# ================ توابع شروع بازی ================
def start_game_round(game_code, chat_id):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    try:
        c.execute("SELECT admin_id, status, game_mode FROM games WHERE game_code = ?", (game_code,))
        game = c.fetchone()

        if not game:
            send_message(chat_id, "❌ بازی پیدا نشد!")
            return

        admin_id, status, game_mode = game

        if game_mode != 'multi':
            send_message(chat_id, "❌ این تابع فقط برای بازی چندنفره است!")
            return

        players_count = get_players_count(game_code)
        if players_count < 3:
            send_message(chat_id, "❌ برای شروع بازی حداقل ۳ بازیکن نیاز است!")
            return

        c.execute("UPDATE players SET is_alive = 1 WHERE game_code = ?", (game_code,))
        conn.commit()

        roles_config = assign_roles(game_code)
        if not roles_config:
            send_message(chat_id, "❌ خطا در تخصیص نقش‌ها!")
            return

        word_pair = get_word_pair()
        if not word_pair:
            send_message(chat_id, "❌ هیچ جفت‌کلمه‌ای در دیتابیس وجود ندارد!")
            return

        word_pair_id, word1, word2 = word_pair

        c.execute(
            "UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?",
            (word_pair_id,)
        )

        c.execute("""
            UPDATE games
            SET status = 'playing',
                word_pair_id = ?,
                round_number = round_number + 1,
                is_round_active = 1
            WHERE game_code = ?
        """, (word_pair_id, game_code))

        c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
        round_number = c.fetchone()[0]

        c.execute("""
            INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at)
            VALUES (?, ?, ?, 'speaking', ?)
        """, (game_code, round_number, word_pair_id, datetime.now().isoformat()))

        round_id = c.lastrowid
        conn.commit()

        alive_players = get_alive_players(game_code)
        for player_id, user_id, display_name, role in alive_players:
            if role == 'spy':
                send_message(
                    user_id,
                    f"🎭 <b>دور {round_number} شروع شد!</b>\n\n"
                    f"نقش شما: <b>{get_role_persian(role)}</b>\n"
                    f"شما کلمه‌ای دریافت نمی‌کنید.\n"
                    "سعی کن از صحبت بقیه کلمه اصلی را حدس بزنی."
                )
            else:
                word = get_word_for_role(word_pair_id, role)
                send_message(
                    user_id,
                    f"🎭 <b>دور {round_number} شروع شد!</b>\n\n"
                    f"نقش شما: <b>{get_role_persian(role)}</b>\n"
                    f"کلمه شما: <b>{word}</b>"
                )

        keyboard = {
            "inline_keyboard": [
                [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
            ]
        }

        send_message(
            chat_id,
            f"🎮 <b>دور {round_number} شروع شد!</b>\n\n"
            "نقش‌ها و کلمات برای بازیکنان ارسال شد.\n"
            "حالا همه بازیکنان باید هر کدام یک کلمه مرتبط بگویند.\n"
            "بعد از اتمام صحبت‌ها، روی دکمه زیر بزن تا رای‌گیری شروع شود.",
            keyboard
        )

    except Exception as e:
        print(f"Error in start_game_round: {e}")
        send_message(chat_id, f"❌ خطا در شروع دور بازی: {str(e)}")
    finally:
        conn.close()

# ================ ساخت بازی ================
def create_new_game(admin_id, game_mode='multi'):
    game_code = generate_code()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO games (game_code, admin_id, status, created_at, game_mode)
            VALUES (?, ?, 'registering', ?, ?)
        """, (game_code, admin_id, datetime.now().isoformat(), game_mode))
        conn.commit()
        return game_code
    except Exception as e:
        print(f"Error in create_new_game: {e}")
        return None
    finally:
        conn.close()

# ================ تک‌نفره ================
def create_single_mode_game(admin_id):
    return create_new_game(admin_id, 'single')

def start_single_mode_game(game_code, admin_id, player_names):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    try:
        players_count = len(player_names)
        if players_count < 3:
            send_message(admin_id, "❌ برای حالت تک‌نفره حداقل ۳ بازیکن نیاز است!")
            return False

        if players_count > 20:
            send_message(admin_id, "❌ حداکثر تعداد بازیکن ۲۰ نفر است!")
            return False

        for name in player_names:
            c.execute("""
                INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
                VALUES (?, ?, ?, 'citizen', 1, 0, ?)
            """, (game_code, admin_id, name, datetime.now().isoformat()))

        conn.commit()
        conn.close()

        return start_single_round(game_code, admin_id)

    except Exception as e:
        print(f"Error in start_single_mode_game: {e}")
        send_message(admin_id, f"❌ خطا در شروع بازی تک‌نفره: {str(e)}")
        try:
            conn.close()
        except Exception:
            pass
        return False

def start_single_round(game_code, admin_id):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    try:
        c.execute("UPDATE players SET is_alive = 1 WHERE game_code = ?", (game_code,))
        conn.commit()

        roles_config = assign_roles(game_code)
        if not roles_config:
            send_message(admin_id, "❌ خطا در تخصیص نقش‌ها!")
            return False

        word_pair = get_word_pair()
        if not word_pair:
            send_message(admin_id, "❌ هیچ جفت‌کلمه‌ای در دیتابیس وجود ندارد!")
            return False

        word_pair_id, word1, word2 = word_pair

        c.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))

        c.execute("""
            UPDATE games
            SET status = 'playing',
                word_pair_id = ?,
                round_number = round_number + 1,
                is_round_active = 1
            WHERE game_code = ?
        """, (word_pair_id, game_code))

        c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
        round_number = c.fetchone()[0]

        c.execute("""
            INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at)
            VALUES (?, ?, ?, 'speaking', ?)
        """, (game_code, round_number, word_pair_id, datetime.now().isoformat()))

        round_id = c.lastrowid
        conn.commit()

        c.execute("""
            SELECT id, display_name, role
            FROM players
            WHERE game_code = ? AND is_alive = 1
        """, (game_code,))
        players = c.fetchall()

        role_lines = []
        for player_id, display_name, role in players:
            if role == 'spy':
                role_lines.append(f"• {display_name} → {get_role_persian(role)}")
            else:
                word = get_word_for_role(word_pair_id, role)
                role_lines.append(f"• {display_name} → {get_role_persian(role)} | کلمه: {word}")

        keyboard = {
            "inline_keyboard": [
                [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
            ]
        }

        send_message(
            admin_id,
            f"🎮 <b>دور {round_number} تک‌نفره شروع شد!</b>\n\n"
            + "\n".join(role_lines) +
            "\n\nبعد از اینکه همه یک کلمه گفتند، رای‌گیری را شروع کن.",
            keyboard
        )
        return True

    except Exception as e:
        print(f"Error in start_single_round: {e}")
        send_message(admin_id, f"❌ خطا در شروع دور تک‌نفره: {str(e)}")
        return False
    finally:
        conn.close()

# ================ وب‌هوک ================
@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    if not update:
        return jsonify({"ok": True})

    try:
        # ================= callback_query =================
        if "callback_query" in update:
            callback_query = update["callback_query"]
            data = callback_query.get("data", "")
            callback_query_id = callback_query.get("id")
            from_user = callback_query.get("from", {})
            user_id = from_user.get("id")
            message = callback_query.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            message_id = message.get("message_id")

            if data == "new_game":
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "👥 بازی چندنفره", "callback_data": "create_multi_game"}],
                        [{"text": "📱 بازی تک‌نفره", "callback_data": "create_single_game"}]
                    ]
                }
                send_message(
                    chat_id,
                    "🎮 نوع بازی را انتخاب کن:",
                    keyboard
                )
                answer_callback_query(callback_query_id)
                return jsonify({"ok": True})

            if data == "create_multi_game":
                game_code = create_new_game(user_id, 'multi')
                if not game_code:
                    answer_callback_query(callback_query_id, "خطا در ساخت بازی", True)
                    return jsonify({"ok": True})

                join_link = f"https://t.me/{os.environ.get('BOT_USERNAME', 'YOUR_BOT_USERNAME')}?start=join_{game_code}"

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "▶️ شروع بازی", "callback_data": f"start_game:{game_code}"}]
                    ]
                }

                send_message(
                    chat_id,
                    f"✅ <b>بازی چندنفره ساخته شد!</b>\n\n"
                    f"🔑 کد بازی: <code>{game_code}</code>\n"
                    f"🔗 لینک عضویت:\n{join_link}\n\n"
                    "لینک را برای دوستانت بفرست تا وارد بازی شوند.\n"
                    "وقتی همه آمدند، دکمه شروع بازی را بزن.",
                    keyboard,
                    disable_web_page_preview=True
                )
                answer_callback_query(callback_query_id)
                return jsonify({"ok": True})

            if data == "create_single_game":
                game_code = create_single_mode_game(user_id)
                if not game_code:
                    answer_callback_query(callback_query_id, "خطا در ساخت بازی", True)
                    return jsonify({"ok": True})

                pending_single_player_names[user_id] = {
                    "game_code": game_code,
                    "step": "awaiting_count"
                }

                send_message(
                    chat_id,
                    "📱 <b>حالت تک‌نفره فعال شد.</b>\n\n"
                    "لطفاً تعداد بازیکنان را وارد کن."
                )
                answer_callback_query(callback_query_id)
                return jsonify({"ok": True})

            if data.startswith("start_game:"):
                parts = data.split(":")
                if len(parts) != 2:
                    answer_callback_query(callback_query_id, "داده نامعتبر است", True)
                    return jsonify({"ok": True})

                game_code = parts[1]

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT admin_id, game_mode FROM games WHERE game_code = ?", (game_code,))
                    row = c.fetchone()
                except Exception as e:
                    print(f"Error in start_game callback: {e}")
                    row = None
                finally:
                    conn.close()

                if not row:
                    answer_callback_query(callback_query_id, "بازی پیدا نشد", True)
                    return jsonify({"ok": True})

                admin_id, game_mode = row

                if user_id != admin_id:
                    answer_callback_query(callback_query_id, "فقط مدیر بازی می‌تواند بازی را شروع کند", True)
                    return jsonify({"ok": True})

                if game_mode != 'multi':
                    answer_callback_query(callback_query_id, "این دکمه برای بازی چندنفره است", True)
                    return jsonify({"ok": True})

                start_game_round(game_code, chat_id)
                answer_callback_query(callback_query_id, "بازی شروع شد")
                return jsonify({"ok": True})

            if data.startswith("start_voting:"):
                parts = data.split(":")
                if len(parts) != 3:
                    answer_callback_query(callback_query_id, "داده نامعتبر است", True)
                    return jsonify({"ok": True})

                game_code = parts[1]
                round_id = parts[2]

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
                    row = c.fetchone()
                except Exception as e:
                    print(f"Error in start_voting callback: {e}")
                    row = None
                finally:
                    conn.close()

                if not row:
                    answer_callback_query(callback_query_id, "بازی پیدا نشد", True)
                    return jsonify({"ok": True})

                admin_id = row[0]

                if user_id != admin_id:
                    answer_callback_query(callback_query_id, "فقط مدیر بازی می‌تواند رای‌گیری را شروع کند", True)
                    return jsonify({"ok": True})

                alive_players = get_alive_players(game_code)
                if len(alive_players) <= 1:
                    answer_callback_query(callback_query_id, "بازیکن زنده کافی برای رای‌گیری وجود ندارد", True)
                    return jsonify({"ok": True})

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("UPDATE rounds SET status = 'voting' WHERE id = ? AND game_code = ?", (round_id, game_code))
                    c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
                    conn.commit()
                except Exception as e:
                    print(f"Error updating voting status: {e}")
                finally:
                    conn.close()

                for player in alive_players:
                    player_id, player_user_id, player_name, role = player
                    vote_buttons = []

                    for target in alive_players:
                        target_id, target_user_id, target_name, target_role = target
                        if target_id != player_id:
                            vote_buttons.append([
                                {
                                    "text": target_name,
                                    "callback_data": f"vote:{round_id}:{player_id}:{target_id}"
                                }
                            ])

                    keyboard = {"inline_keyboard": vote_buttons}

                    send_message(
                        player_user_id,
                        "🗳️ <b>رای‌گیری شروع شد</b>\n\n"
                        "به بازیکنی که فکر می‌کنی مشکوک‌تر است رای بده:",
                        keyboard
                    )

                admin_keyboard = {
                    "inline_keyboard": [
                        [{"text": "✅ پایان رای‌گیری", "callback_data": f"finish_voting:{game_code}:{round_id}"}]
                    ]
                }

                send_message(
                    chat_id,
                    "🗳️ رای‌گیری شروع شد!\n\n"
                    "بعد از اینکه همه رای دادند، روی دکمه زیر بزن.",
                    admin_keyboard
                )

                if message_id:
                    try:
                        edit_message_reply_markup(chat_id, message_id, {"inline_keyboard": []})
                    except Exception:
                        pass

                answer_callback_query(callback_query_id, "رای‌گیری شروع شد")
                return jsonify({"ok": True})

            if data.startswith("vote:"):
                parts = data.split(":")
                if len(parts) != 4:
                    answer_callback_query(callback_query_id, "داده رای نامعتبر است", True)
                    return jsonify({"ok": True})

                round_id = parts[1]
                voter_id = int(parts[2])
                target_id = int(parts[3])

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT user_id, is_alive FROM players WHERE id = ?", (voter_id,))
                    voter_row = c.fetchone()

                    if not voter_row:
                        answer_callback_query(callback_query_id, "رای‌دهنده پیدا نشد", True)
                        return jsonify({"ok": True})

                    voter_user_id, voter_alive = voter_row

                    if user_id != voter_user_id:
                        answer_callback_query(callback_query_id, "این رای مربوط به شما نیست", True)
                        return jsonify({"ok": True})

                    if voter_alive != 1:
                        answer_callback_query(callback_query_id, "شما از بازی حذف شده‌اید", True)
                        return jsonify({"ok": True})

                    c.execute("SELECT is_alive FROM players WHERE id = ?", (target_id,))
                    target_row = c.fetchone()

                    if not target_row or target_row[0] != 1:
                        answer_callback_query(callback_query_id, "این بازیکن دیگر زنده نیست", True)
                        return jsonify({"ok": True})

                    c.execute("SELECT id FROM votes WHERE round_id = ? AND voter_id = ?", (round_id, voter_id))
                    existing_vote = c.fetchone()

                    if existing_vote:
                        answer_callback_query(callback_query_id, "شما قبلاً رای داده‌اید", True)
                        return jsonify({"ok": True})

                    c.execute("""
                        INSERT INTO votes (round_id, voter_id, target_id, voted_at)
                        VALUES (?, ?, ?, ?)
                    """, (round_id, voter_id, target_id, datetime.now().isoformat()))
                    conn.commit()

                except Exception as e:
                    print(f"Error in vote callback: {e}")
                    answer_callback_query(callback_query_id, "خطا در ثبت رای", True)
                    return jsonify({"ok": True})
                finally:
                    conn.close()

                answer_callback_query(callback_query_id, "✅ رای شما ثبت شد")

                try:
                    edit_message_reply_markup(chat_id, message_id, {"inline_keyboard": []})
                except Exception:
                    pass

                send_message(chat_id, "📩 یک رای جدید ثبت شد.")
                return jsonify({"ok": True})

            if data.startswith("finish_voting:"):
                parts = data.split(":")
                if len(parts) != 3:
                    answer_callback_query(callback_query_id, "داده نامعتبر است", True)
                    return jsonify({"ok": True})

                game_code = parts[1]
                round_id = parts[2]

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
                    row = c.fetchone()
                except Exception as e:
                    print(f"Error in finish_voting callback: {e}")
                    row = None
                finally:
                    conn.close()

                if not row:
                    answer_callback_query(callback_query_id, "بازی پیدا نشد", True)
                    return jsonify({"ok": True})

                admin_id = row[0]

                if user_id != admin_id:
                    answer_callback_query(callback_query_id, "فقط مدیر بازی می‌تواند رای‌گیری را تمام کند", True)
                    return jsonify({"ok": True})

                finish_voting_round(game_code, round_id, chat_id)
                answer_callback_query(callback_query_id, "رای‌گیری بررسی شد")
                return jsonify({"ok": True})

            if data.startswith("finish_tie_voting:"):
                parts = data.split(":")
                if len(parts) != 3:
                    answer_callback_query(callback_query_id, "داده نامعتبر است", True)
                    return jsonify({"ok": True})

                game_code = parts[1]
                round_id = parts[2]

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
                    row = c.fetchone()
                except Exception as e:
                    print(f"Error in finish_tie_voting callback: {e}")
                    row = None
                finally:
                    conn.close()

                if not row:
                    answer_callback_query(callback_query_id, "بازی پیدا نشد", True)
                    return jsonify({"ok": True})

                admin_id = row[0]

                if user_id != admin_id:
                    answer_callback_query(callback_query_id, "فقط مدیر بازی می‌تواند رای‌گیری تساوی را تمام کند", True)
                    return jsonify({"ok": True})

                finish_voting_round(game_code, round_id, chat_id)
                answer_callback_query(callback_query_id, "رای‌گیری تساوی بررسی شد")
                return jsonify({"ok": True})

            if data.startswith("new_round:"):
                parts = data.split(":")
                if len(parts) != 2:
                    answer_callback_query(callback_query_id, "داده نامعتبر است", True)
                    return jsonify({"ok": True})

                game_code = parts[1]

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT admin_id, game_mode FROM games WHERE game_code = ?", (game_code,))
                    row = c.fetchone()
                except Exception as e:
                    print(f"Error in new_round callback: {e}")
                    row = None
                finally:
                    conn.close()

                if not row:
                    answer_callback_query(callback_query_id, "بازی پیدا نشد", True)
                    return jsonify({"ok": True})

                admin_id, game_mode = row

                if user_id != admin_id:
                    answer_callback_query(callback_query_id, "فقط مدیر بازی می‌تواند دور جدید را شروع کند", True)
                    return jsonify({"ok": True})

                if game_mode == 'single':
                    start_single_round(game_code, admin_id)
                else:
                    start_game_round(game_code, chat_id)

                answer_callback_query(callback_query_id, "دور جدید شروع شد")
                return jsonify({"ok": True})

            answer_callback_query(callback_query_id)
            return jsonify({"ok": True})

        # ================= message =================
        if "message" not in update:
            return jsonify({"ok": True})

        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        text = message.get("text", "").strip()

        # شروع ربات
        if text == "/start":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎮 شروع بازی جدید", "callback_data": "new_game"}]
                ]
            }
            send_message(
                chat_id,
                "🕵️‍♂️ <b>به ربات جاسوس پیشرفته خوش اومدی!</b>\n\n"
                "برای ساخت بازی جدید، روی دکمه زیر بزن.\n"
                "این ربات از بازی گروهی و تک‌نفره پشتیبانی می‌کند.",
                keyboard
            )
            return jsonify({"ok": True})

        # جوین از طریق لینک
        if text.startswith("/start join_"):
            game_code = text.replace("/start join_", "").strip()

            if not game_code:
                send_message(chat_id, "❌ کد بازی نامعتبر است!")
                return jsonify({"ok": True})

            game_status = get_game_status(game_code)
            if not game_status:
                send_message(chat_id, "❌ بازی پیدا نشد!")
                return jsonify({"ok": True})

            if game_status != 'registering':
                send_message(chat_id, "❌ این بازی در حال ثبت‌نام نیست یا تموم شده!")
                return jsonify({"ok": True})

            game_mode = get_game_mode(game_code)
            if game_mode != 'multi':
                send_message(chat_id, "❌ این بازی برای حالت تک‌نفره طراحی شده است!")
                return jsonify({"ok": True})

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT id FROM players WHERE game_code = ? AND user_id = ?", (game_code, user_id))
                existing = c.fetchone()
            except Exception as e:
                send_message(chat_id, f"❌ خطا در بررسی ثبت‌نام: {str(e)}")
                return jsonify({"ok": True})
            finally:
                conn.close()

            if existing:
                send_message(chat_id, "✅ شما قبلاً در این بازی ثبت‌نام کردید!")
                return jsonify({"ok": True})

            pending_registrations[user_id] = game_code
            send_message(
                chat_id,
                "👤 لطفاً یک <b>اسم مستعار</b> برای خودت انتخاب کن:\n\n"
                "(این اسم توی بازی نمایش داده میشه)\n\n"
                "✏️ فقط اسم رو تایپ کن و بفرست."
            )
            return jsonify({"ok": True})

        # حالت تک‌نفره - دریافت تعداد بازیکنان و اسامی
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        try:
            c.execute("""
                SELECT game_code
                FROM games
                WHERE admin_id = ? AND game_mode = 'single' AND status = 'registering'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            single_game = c.fetchone()
        except Exception as e:
            print(f"Error checking single game: {e}")
            single_game = None
        finally:
            conn.close()

        if user_id in pending_single_player_names:
            state = pending_single_player_names[user_id]

            if state["step"] == "awaiting_count":
                if not text.isdigit():
                    send_message(chat_id, "❌ لطفاً فقط عدد وارد کن.")
                    return jsonify({"ok": True})

                count = int(text)
                if count < 3 or count > 20:
                    send_message(chat_id, "❌ تعداد بازیکنان باید بین ۳ تا ۲۰ نفر باشد.")
                    return jsonify({"ok": True})

                state["count"] = count
                state["names"] = []
                state["current_index"] = 1
                state["step"] = "awaiting_names"

                send_message(chat_id, f"👤 اسم بازیکن شماره 1 را وارد کن:")
                return jsonify({"ok": True})

            if state["step"] == "awaiting_names":
                if len(text) < 2:
                    send_message(chat_id, "❌ اسم باید حداقل ۲ کاراکتر باشد.")
                    return jsonify({"ok": True})

                if text in state["names"]:
                    send_message(chat_id, "❌ این اسم قبلاً وارد شده. یک اسم دیگر وارد کن.")
                    return jsonify({"ok": True})

                state["names"].append(text)

                if len(state["names"]) >= state["count"]:
                    game_code = state["game_code"]
                    player_names = state["names"]
                    del pending_single_player_names[user_id]

                    success = start_single_mode_game(game_code, user_id, player_names)
                    if success:
                        send_message(chat_id, "✅ بازی تک‌نفره با موفقیت شروع شد.")
                    return jsonify({"ok": True})
                else:
                    next_index = len(state["names"]) + 1
                    send_message(chat_id, f"👤 اسم بازیکن شماره {next_index} را وارد کن:")
                    return jsonify({"ok": True})

        # دریافت اسم مستعار (ثبت‌نام چندنفره)
        if user_id in pending_registrations:
            game_code = pending_registrations[user_id]

            if len(text.strip()) < 2:
                send_message(chat_id, "❌ اسم مستعار باید حداقل ۲ کاراکتر باشه. لطفاً دوباره تلاش کن.")
                return jsonify({"ok": True})

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute(
                    "SELECT display_name FROM players WHERE game_code = ? AND display_name = ?",
                    (game_code, text.strip())
                )
                duplicate = c.fetchone()

                if duplicate:
                    send_message(
                        chat_id,
                        f"❌ اسم مستعار «{text.strip()}» قبلاً توسط کس دیگه‌ای انتخاب شده! لطفاً اسم دیگه‌ای انتخاب کن."
                    )
                    return jsonify({"ok": True})

                c.execute("""
                    INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
                    VALUES (?, ?, ?, 'citizen', 1, 0, ?)
                """, (game_code, user_id, text.strip(), datetime.now().isoformat()))
                conn.commit()

            except Exception as e:
                send_message(chat_id, f"❌ خطا در ثبت‌نام: {str(e)}")
                return jsonify({"ok": True})
            finally:
                conn.close()

            del pending_registrations[user_id]

            send_message(
                chat_id,
                f"✅ شما با اسم مستعار «{text.strip()}» در بازی ثبت‌نام شدید!\n\n"
                "منتظر شروع بازی توسط مدیر باشید."
            )

            admin = None
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT admin_id FROM games WHERE game_code = ?", (game_code,))
                admin = c.fetchone()
            except Exception as e:
                print(f"Error getting admin: {e}")
            finally:
                conn.close()

            if admin:
                send_message(
                    admin[0],
                    f"🔔 کاربر جدید با اسم «{text.strip()}» به بازی پیوست.\n\n"
                    f"تعداد بازیکنان فعلی: {get_players_count(game_code)} نفر"
                )

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

def reset_votes_for_next_voting(round_id):
    """
    وقتی همان دور باید ادامه پیدا کند، رای‌های قبلی پاک می‌شوند
    تا رای‌گیری بعدی با همین round_id دچار تداخل نشود.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM votes WHERE round_id = ?", (round_id,))
        conn.commit()
    except Exception as e:
        print(f"Error in reset_votes_for_next_voting: {e}")
    finally:
        conn.close()

def send_continue_round_message(game_code, chat_id, round_id):
    """
    اگر بازی هنوز تمام نشده باشد:
    - به بازیکنان زنده می‌گوید دوباره یک کلمه بگویند
    - به مدیر دکمه شروع رای‌گیری می‌دهد
    """
    try:
        alive_players = get_alive_players(game_code)

        if not alive_players:
            send_message(chat_id, "⚠️ بازیکن زنده‌ای برای ادامه بازی وجود ندارد.")
            return

        for player in alive_players:
            player_id, player_user_id, player_name, role = player
            send_message(
                player_user_id,
                "🗣️ <b>بازی هنوز ادامه دارد.</b>\n\n"
                "لطفاً دوباره هر نفر یک کلمه مرتبط بگه.\n"
                "بعد از اینکه همه صحبت کردن، مدیر رای‌گیری بعدی رو شروع می‌کنه."
            )

        keyboard = {
            "inline_keyboard": [
                [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
            ]
        }

        send_message(
            chat_id,
            "✅ بازی هنوز تمام نشده.\n\n"
            "بازیکنان زنده باید دوباره یک کلمه بگن.\n"
            "بعد از اتمام صحبت‌ها، برای شروع رای‌گیری بعدی روی دکمه زیر بزن.",
            keyboard
        )

    except Exception as e:
        print(f"Error in send_continue_round_message: {e}")
        send_message(chat_id, f"❌ خطا در ادامه بازی: {str(e)}")

def get_alive_role_counts(game_code):
    """
    تعداد نقش‌های زنده بازی را برمی‌گرداند.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT role, COUNT(*)
            FROM players
            WHERE game_code = ? AND is_alive = 1
            GROUP BY role
        """, (game_code,))
        rows = c.fetchall()

        counts = {
            'citizen': 0,
            'misled': 0,
            'spy': 0
        }

        for role, count in rows:
            if role in counts:
                counts[role] = count

        return counts

    except Exception as e:
        print(f"Error in get_alive_role_counts: {e}")
        return {
            'citizen': 0,
            'misled': 0,
            'spy': 0
        }
    finally:
        conn.close()

def finish_game_by_rule(game_code, chat_id, winner_type, reason_text=None):
    """
    پایان بازی بر اساس نوع برنده.

    winner_type:
    - citizens
    - spies
    - misled
    - spies_and_misled
    """
    try:
        if winner_type == 'citizens':
            add_score_to_team(game_code, 'citizen', 2)
            winner_message = "🎉 شهروندان برنده شدند!"

        elif winner_type == 'spies':
            add_score_to_team(game_code, 'spy', 6)
            winner_message = "🎉 تیم جاسوس‌ها برنده شد!"

        elif winner_type == 'misled':
            add_score_to_team(game_code, 'misled', 10)
            winner_message = "🎉 تیم گمراهان برنده شد!"

        elif winner_type == 'spies_and_misled':
            add_score_to_team(game_code, 'spy', 6)
            add_score_to_team(game_code, 'misled', 10)
            winner_message = "🎉 جاسوس‌ها و گمراهان برنده شدند!"

        else:
            winner_message = "🏁 بازی تمام شد."

        if reason_text:
            send_message(chat_id, f"{reason_text}\n\n{winner_message}")
        else:
            send_message(chat_id, winner_message)

        end_game(game_code, chat_id)

    except Exception as e:
        print(f"Error in finish_game_by_rule: {e}")
        send_message(chat_id, f"❌ خطا در پایان بازی: {str(e)}")

def start_balance_spy_guess(game_code, chat_id, round_id=None):
    """
    قانون سوم پایان بازی:
    وقتی تعداد شهروندهای زنده با مجموع گمراهان و جاسوس‌ها برابر شود،
    یک جاسوس زنده باید کلمه اصلی را حدس بزند.

    اگر جاسوس زنده‌ای وجود نداشته باشد، فقط گمراهان برنده می‌شوند.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, user_id, display_name
            FROM players
            WHERE game_code = ? AND is_alive = 1 AND role = 'spy'
            ORDER BY id ASC
            LIMIT 1
        """, (game_code,))
        spy = c.fetchone()

        word_pair = get_game_word_pair(game_code)
        if not word_pair:
            send_message(chat_id, "❌ جفت‌کلمه این بازی پیدا نشد و امکان حدس نهایی وجود ندارد.")
            finish_game_by_rule(
                game_code,
                chat_id,
                'misled',
                "⚠️ به دلیل خطا در پیدا کردن کلمه اصلی، بازی با برد گمراهان تمام شد."
            )
            return True

        main_word = word_pair[0]

        if not spy:
            finish_game_by_rule(
                game_code,
                chat_id,
                'misled',
                "⚖️ تعداد شهروندها با مجموع گمراهان و جاسوس‌ها برابر شده است.\n\n"
                "اما جاسوس زنده‌ای برای حدس نهایی وجود ندارد."
            )
            return True

        spy_player_id, spy_user_id, spy_name = spy

        pending_spy_guesses[spy_user_id] = {
            'game_code': game_code,
            'main_word': main_word,
            'player_id': spy_player_id,
            'spy_name': spy_name,
            'chat_id': chat_id,
            'round_id': round_id,
            'guess_type': 'balance_final'
        }

        send_message(
            spy_user_id,
            "⚖️ <b>مرحله حدس نهایی جاسوس</b>\n\n"
            "تعداد شهروندهای زنده با مجموع جاسوس‌ها و گمراهان برابر شده است.\n\n"
            "حالا شما به عنوان جاسوس باید کلمه اصلی را حدس بزنید.\n\n"
            "✅ اگر درست حدس بزنی، جاسوس‌ها همراه با گمراهان برنده می‌شوند.\n"
            "❌ اگر اشتباه حدس بزنی، فقط گمراهان برنده می‌شوند.\n\n"
            "✏️ فقط خود کلمه را تایپ کن و بفرست."
        )

        send_message(
            chat_id,
            "⚖️ تعداد شهروندهای زنده با مجموع گمراهان و جاسوس‌ها برابر شده است.\n\n"
            "⏳ بازی وارد مرحله حدس نهایی شد.\n"
            "منتظر حدس جاسوس باشید."
        )

        return True

    except Exception as e:
        print(f"Error in start_balance_spy_guess: {e}")
        send_message(chat_id, f"❌ خطا در شروع حدس نهایی جاسوس: {str(e)}")
        return True
    finally:
        conn.close()

def check_game_finished_after_elimination(game_code, chat_id, round_id=None):
    """
    بعد از حذف هر بازیکن بررسی می‌کند آیا بازی طبق قوانین جدید تمام شده یا نه.

    قوانین:
    1. اگر همه جاسوس‌ها و گمراهان حذف شده باشند، شهروندان برنده‌اند.
    2. اگر شهروندی باقی نمانده باشد، غیرشهروندها برنده‌اند.
    3. اگر تعداد شهروندهای زنده با مجموع جاسوس‌ها و گمراهان برابر شود،
       مرحله حدس نهایی جاسوس اجرا می‌شود.
    """
    counts = get_alive_role_counts(game_code)

    citizen_count = counts['citizen']
    misled_count = counts['misled']
    spy_count = counts['spy']
    non_citizen_count = misled_count + spy_count

    print(
        f"🔍 End check for game {game_code}: "
        f"citizen={citizen_count}, misled={misled_count}, spy={spy_count}, "
        f"non_citizen={non_citizen_count}"
    )

    # فقط شهروندها مانده‌اند
    if non_citizen_count == 0 and citizen_count > 0:
        finish_game_by_rule(
            game_code,
            chat_id,
            'citizens',
            "✅ همه جاسوس‌ها و گمراهان حذف شده‌اند و فقط شهروندان باقی مانده‌اند."
        )
        return True

    # هیچ شهروندی باقی نمانده
    if citizen_count == 0 and non_citizen_count > 0:
        if spy_count > 0 and misled_count > 0:
            finish_game_by_rule(
                game_code,
                chat_id,
                'spies_and_misled',
                "✅ هیچ شهروندی در بازی باقی نمانده است."
            )
        elif spy_count > 0:
            finish_game_by_rule(
                game_code,
                chat_id,
                'spies',
                "✅ هیچ شهروندی در بازی باقی نمانده است."
            )
        else:
            finish_game_by_rule(
                game_code,
                chat_id,
                'misled',
                "✅ هیچ شهروندی در بازی باقی نمانده است."
            )
        return True

    # قانون برابری
    if citizen_count > 0 and non_citizen_count > 0 and citizen_count == non_citizen_count:
        return start_balance_spy_guess(game_code, chat_id, round_id)

    return False

def handle_spy_elimination(game_code, player_id, chat_id, round_id=None):
    """
    اگر جاسوس با رای حذف شود، همان جاسوس فرصت حدس کلمه اصلی را دارد.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute(
            "SELECT user_id, display_name FROM players WHERE id = ? AND game_code = ?",
            (player_id, game_code)
        )
        spy = c.fetchone()

        if not spy:
            send_message(chat_id, "⚠️ اطلاعات جاسوس حذف‌شده پیدا نشد.")
            return

        spy_user_id, spy_name = spy
        word_pair = get_game_word_pair(game_code)

        if not word_pair:
            send_message(chat_id, "⚠️ جفت‌کلمه این بازی پیدا نشد.")
            return

        main_word = word_pair[0]

        pending_spy_guesses[spy_user_id] = {
            'game_code': game_code,
            'main_word': main_word,
            'player_id': player_id,
            'spy_name': spy_name,
            'chat_id': chat_id,
            'round_id': round_id,
            'guess_type': 'eliminated_spy'
        }

        send_message(
            spy_user_id,
            "🔍 شما به عنوان جاسوس حذف شدید!\n\n"
            "برای نجات تیم جاسوس‌ها، کلمه اصلی را حدس بزن.\n\n"
            "✅ اگر درست حدس بزنی، تیم جاسوس‌ها برنده می‌شود.\n"
            "❌ اگر اشتباه حدس بزنی، وضعیت بازی بر اساس بازیکنان باقی‌مانده بررسی می‌شود.\n\n"
            "✏️ فقط خود کلمه را تایپ کن و بفرست."
        )

        send_message(
            chat_id,
            f"🕵️‍♂️ <b>{spy_name}</b> جاسوس بود و حذف شد.\n\n"
            "⏳ حالا باید منتظر حدس جاسوس باشید."
        )

    except Exception as e:
        print(f"Error in handle_spy_elimination: {e}")
        send_message(chat_id, f"❌ خطا در مرحله حدس جاسوس: {str(e)}")
    finally:
        conn.close()

def check_spy_guess(user_id, guessed_word):
    """
    مدیریت حدس جاسوس.

    دو نوع حدس:
    1) eliminated_spy
    2) balance_final
    """
    if user_id not in pending_spy_guesses:
        return None

    data = pending_spy_guesses[user_id]

    game_code = data['game_code']
    main_word = data['main_word']
    chat_id = data['chat_id']
    round_id = data.get('round_id')
    guess_type = data.get('guess_type', 'eliminated_spy')

    del pending_spy_guesses[user_id]

    guessed_clean = guessed_word.strip().lower()
    main_clean = main_word.strip().lower()
    is_correct = guessed_clean == main_clean

    # حالت 1: جاسوس حذف‌شده
    if guess_type == 'eliminated_spy':
        if is_correct:
            send_message(
                user_id,
                f"✅ <b>درست حدس زدی!</b>\n\n"
                f"کلمه اصلی: <b>{main_word}</b>\n\n"
                "🎉 تیم جاسوس‌ها برنده شد!"
            )

            all_players = get_all_players(game_code)
            for player in all_players:
                player_user_id = player[1]
                if player_user_id != user_id:
                    send_message(
                        player_user_id,
                        "🎉 جاسوس حذف‌شده کلمه اصلی را درست حدس زد!\n\n"
                        f"کلمه اصلی: <b>{main_word}</b>\n"
                        "تیم جاسوس‌ها برنده شد!"
                    )

            finish_game_by_rule(
                game_code,
                chat_id,
                'spies',
                "🎯 جاسوس حذف‌شده کلمه اصلی را درست حدس زد."
            )
            return True

        send_message(
            user_id,
            f"❌ <b>اشتباه حدس زدی!</b>\n\n"
            f"حدس شما: <b>{guessed_word}</b>\n"
            f"کلمه اصلی: <b>{main_word}</b>"
        )

        send_message(
            chat_id,
            "❌ جاسوس حذف‌شده کلمه اصلی را اشتباه حدس زد.\n\n"
            f"حدس جاسوس: <b>{guessed_word}</b>\n"
            f"کلمه اصلی: <b>{main_word}</b>"
        )

        game_finished = check_game_finished_after_elimination(game_code, chat_id, round_id)
        if game_finished:
            return False

        if round_id:
            reset_votes_for_next_voting(round_id)
            send_continue_round_message(game_code, chat_id, round_id)
        else:
            send_message(
                chat_id,
                "✅ بازی هنوز تمام نشده است، اما شناسه دور پیدا نشد و امکان ادامه رای‌گیری خودکار وجود ندارد."
            )

        return False
            eliminated_user_id = eliminated_user[0] if eliminated_user else None

            if eliminated_user_id:
                send_message(
                    eliminated_user_id,
                    f"⛔️ شما از بازی حذف شدید.\n\n"
                    f"نقش شما: <b>{role_persian}</b>"
                )

            c.execute(
                "UPDATE rounds SET status = 'speaking' WHERE id = ? AND game_code = ?",
                (round_id, game_code)
            )
            conn.commit()

            # اگر جاسوس حذف شده، مرحله حدس جاسوس اجرا شود
            if eliminated_role == 'spy':
                handle_spy_elimination(game_code, target_id, chat_id, round_id)
                return

            # اگر جاسوس حذف نشده، بررسی کن آیا بازی تمام شده یا نه
            game_finished = check_game_finished_after_elimination(game_code, chat_id, round_id)
            if game_finished:
                return

            # بازی ادامه دارد
            reset_votes_for_next_voting(round_id)
            send_continue_round_message(game_code, chat_id, round_id)
            return

        # اگر چند نفر رای مساوی دارند
        send_message(
            chat_id,
            "⚖️ رای‌گیری مساوی شد!\n\n"
            "بین افرادی که بیشترین رای را آوردند، دوباره رای‌گیری می‌شود."
        )
        start_tie_voting_round(game_code, round_id, chat_id, top_candidates)

    except Exception as e:
        print(f"Error in finish_voting_round: {e}")
        send_message(chat_id, f"❌ خطا در پایان رای‌گیری: {str(e)}")
    finally:
        conn.close()

def start_tie_voting_round(game_code, round_id, chat_id, top_candidates):
    """
    شروع رای‌گیری تساوی فقط بین کاندیداهای مساوی.
    """
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    try:
        # رای‌های قبلی همین دور پاک می‌شوند
        c.execute("DELETE FROM votes WHERE round_id = ?", (round_id,))
        conn.commit()

        alive_players = get_alive_players(game_code)

        if not alive_players:
            send_message(chat_id, "⚠️ بازیکن زنده‌ای برای رای‌گیری تساوی وجود ندارد.")
            return

        placeholders = ",".join(["?"] * len(top_candidates))
        query = f"""
            SELECT id, display_name
            FROM players
            WHERE game_code = ?
              AND id IN ({placeholders})
              AND is_alive = 1
        """
        c.execute(query, [game_code] + top_candidates)
        tied_players = c.fetchall()

        if not tied_players:
            send_message(chat_id, "⚠️ بازیکنان رای مساوی پیدا نشدند.")
            return

        for player in alive_players:
            player_id, player_user_id, player_name, role = player
            vote_buttons = []

            for target_id, target_name in tied_players:
                if target_id != player_id:
                    vote_buttons.append([
                        {
                            "text": target_name,
                            "callback_data": f"vote:{round_id}:{player_id}:{target_id}"
                        }
                    ])

            if not vote_buttons:
                continue

            keyboard = {"inline_keyboard": vote_buttons}

            send_message(
                player_user_id,
                "⚖️ <b>رای‌گیری تساوی</b>\n\n"
                "رای‌گیری فقط بین افراد مساوی تکرار می‌شود.\n"
                "یکی را انتخاب کن:",
                keyboard
            )

        admin_keyboard = {
            "inline_keyboard": [
                [{"text": "✅ پایان رای‌گیری تساوی", "callback_data": f"finish_tie_voting:{game_code}:{round_id}"}]
            ]
        }

        send_message(
            chat_id,
            "⚖️ رای‌گیری تساوی شروع شد.\n\n"
            "بعد از اینکه همه رای دادند، دکمه زیر را بزن.",
            admin_keyboard
        )

    except Exception as e:
        print(f"Error in start_tie_voting_round: {e}")
        send_message(chat_id, f"❌ خطا در شروع رای‌گیری تساوی: {str(e)}")
    finally:
        conn.close()

# ================ مدیریت کلمات ================
def add_word_pair(word1, word2, category='general'):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO word_pairs (word1, word2, category)
            VALUES (?, ?, ?)
        """, (word1, word2, category))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error in add_word_pair: {e}")
        return False
    finally:
        conn.close()

def get_all_word_pairs():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT id, word1, word2, category, used_count FROM word_pairs ORDER BY id DESC")
        return c.fetchall()
    except Exception as e:
        print(f"Error in get_all_word_pairs: {e}")
        return []
    finally:
        conn.close()

# ================ ست کردن وب‌هوک ================
def set_webhook(webhook_url):
    try:
        response = requests.post(
            f"{BASE_URL}/setWebhook",
            json={"url": webhook_url},
            timeout=10
        )
        print(response.json())
    except Exception as e:
        print(f"Error setting webhook: {e}")

# ================ اجرای برنامه ================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        print(f"Setting webhook to: {webhook_url}")
        set_webhook(webhook_url)

    app.run(host="0.0.0.0", port=port)
