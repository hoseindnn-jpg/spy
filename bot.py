from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import requests
from datetime import datetime
import time

app = Flask(__name__)

TOKEN = "8898647964:AAHYLtihj2D6xfLXPltEA4fcUE5wOSktV94"
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
        
        # افزودن کلمات به دیتابیس (در صورت عدم وجود)
        for word1, word2 in default_pairs:
            c.execute("INSERT OR IGNORE INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)",
                      (word1, word2, 'general'))
        
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

def get_alive_players(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT id, user_id, display_name, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
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
        c.execute("SELECT id, user_id, display_name, role, score FROM players WHERE game_code = ?", (game_code,))
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
        c.execute("SELECT word1, word2 FROM word_pairs wp JOIN games g ON g.word_pair_id = wp.id WHERE g.game_code = ?", (game_code,))
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
        
        print(f"✅ نقش‌ها: شهروند={citizen_count}, گمراه={misled_count}, جاسوس={spy_count}")
        
        roles = ['citizen'] * citizen_count + ['misled'] * misled_count + ['spy'] * spy_count
        random.shuffle(roles)
        
        for player_id, role in zip(player_ids, roles):
            c.execute("UPDATE players SET role = ? WHERE id = ?", (role, player_id))
        
        conn.commit()
        
        c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1 AND role IS NOT NULL", (game_code,))
        assigned_count = c.fetchone()[0]
        print(f"✅ {assigned_count} نقش با موفقیت توزیع شد.")
        
        return {'citizen': citizen_count, 'misled': misled_count, 'spy': spy_count}
    
    except Exception as e:
        print(f"❌ خطا در توزیع نقش‌ها: {e}")
        return None
    finally:
        conn.close()

def get_word_pair():
    """دریافت یک جفت کلمه استفاده نشده"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT id, word1, word2, category FROM word_pairs ORDER BY used_count ASC, RANDOM() LIMIT 1")
        pair = c.fetchone()
        if pair:
            print(f"✅ کلمه انتخاب شد: {pair[1]} - {pair[2]}")
        else:
            print("❌ هیچ کلمه‌ای در دیتابیس وجود ندارد!")
        return pair
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
        word1, word2 = c.fetchone()
        if role == 'citizen':
            return word1
        elif role == 'misled':
            return word2
        else:
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
        c.execute("UPDATE players SET score = score + ? WHERE game_code = ? AND role = ?",
                  (points, game_code, role))
        conn.commit()
    except Exception as e:
        print(f"Error in add_score_to_team: {e}")
    finally:
        conn.close()

def start_new_game(chat_id, admin_id, game_mode='multi'):
    """شروع بازی جدید با حالت مشخص"""
    game_code = generate_code()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO games (game_code, admin_id, status, created_at, is_round_active, game_mode) VALUES (?, ?, 'registering', ?, 0, ?)",
                  (game_code, admin_id, datetime.now().isoformat(), game_mode))
        conn.commit()
        print(f"✅ بازی جدید با کد {game_code} ایجاد شد.")
    except Exception as e:
        send_message(chat_id, f"❌ خطا در ایجاد بازی: {str(e)}")
        return
    finally:
        conn.close()
    
    if game_mode == 'single':
        send_message(chat_id,  
                    f"🎮 بازی جاسوس (حالت تک‌نفره) ساخته شد!\n\n"
                    f"📋 کد بازی: <code>{game_code}</code>\n\n"
                    f"تعداد بازیکنان را وارد کنید (۳ تا ۲۰):")
    else:
        bot_info = requests.get(f"{BASE_URL}/getMe").json()
        bot_username = bot_info['result']['username']
        register_link = f"https://t.me/{bot_username}?start=register_{game_code}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "✅ پایان ثبت‌نام", "callback_data": f"finish_register:{game_code}"}]
            ]
        }
        send_message(chat_id,
                    f"🎮 بازی جاسوس (حالت چندنفره) ساخته شد!\n\n"
                    f"📋 کد بازی: <code>{game_code}</code>\n\n"
                    f"🔗 لینک ثبت‌نام:\n{register_link}\n\n"
                    f"این لینک رو برای دوستان بفرست تا بتونن عضو بشن.\n\n"
                    f"بعد از ثبت‌نام همه، روی دکمه «پایان ثبت‌نام» کلیک کن.",
                    keyboard)

def start_game_round(game_code, chat_id):
    """شروع یک دور جدید از بازی"""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        
        # مرحله 1: پاک کردن آرای قبلی
        c.execute("DELETE FROM votes WHERE round_id IN (SELECT id FROM rounds WHERE game_code = ?)", (game_code,))
        
        # مرحله 2: شمارش بازیکنان زنده
        c.execute("SELECT COUNT(*) FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
        count = c.fetchone()[0]
        print(f"🔍 تعداد بازیکنان زنده: {count}")
        
        if count < 3:
            send_message(chat_id, f"⚠️ تعداد بازیکنان زنده ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع دور لازمه.")
            conn.close()
            return
        
        # مرحله 3: تنظیم نقش پیش‌فرض برای بازیکنانی که نقش ندارند
        c.execute("UPDATE players SET role = 'citizen' WHERE game_code = ? AND is_alive = 1 AND role IS NULL", (game_code,))
        conn.commit()
        
        # مرحله 4: توزیع نقش‌ها
        role_counts = assign_roles(game_code)
        if not role_counts:
            send_message(chat_id, "❌ خطا در توزیع نقش‌ها!")
            conn.close()
            return
        
        # مرحله 5: انتخاب جفت کلمه
        word_pair = get_word_pair()
        if not word_pair:
            send_message(chat_id, "❌ هیچ جفت کلمه‌ای در دیتابیس وجود نداره! لطفاً ابتدا کلمات رو اضافه کن.")
            conn.close()
            return
        
        word_pair_id, word1, word2, category = word_pair
        
        # مرحله 6: ثبت دور جدید
        c.execute("UPDATE games SET status = 'playing', round_number = round_number + 1, is_round_active = 0, word_pair_id = ? WHERE game_code = ?",
                  (word_pair_id, game_code))
        c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
        round_number = c.fetchone()[0]
        
        c.execute("INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at) VALUES (?, ?, ?, 'speaking', ?)",
                  (game_code, round_number, word_pair_id, datetime.now().isoformat()))
        round_id = c.lastrowid
        
        c.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))
        conn.commit()
        
        # مرحله 7: دریافت حالت بازی
        game_mode = get_game_mode(game_code)
        
        if game_mode == 'single':
            # حالت تک‌نفره - نمایش نقش‌ها به صورت متوالی
            c.execute("SELECT id, user_id, display_name, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
            players = c.fetchall()
            conn.close()
            
            if not players:
                send_message(chat_id, "❌ هیچ بازیکنی ثبت نشده است!")
                return
            
            # ذخیره لیست بازیکنان برای نمایش متوالی
            pending_single_player_names[game_code] = {
                'players': players,
                'current_index': 0,
                'round_id': round_id,
                'round_number': round_number
            }
            
            # نمایش اولین بازیکن
            show_next_single_player(game_code, chat_id)
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 نفر بعدی", "callback_data": f"single_next:{game_code}"}]
                ]
            }
            send_message(chat_id, "👤 برای مشاهده نقش هر بازیکن، دکمه «نفر بعدی» را بزنید.", keyboard)
            
        else:
            # حالت چندنفره - ارسال کلمات به بازیکنان
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
            send_message(chat_id, f"✅ دور {round_number} شروع شد! {count} نفر در بازی هستن.\n\n📊 تعداد نقش‌ها (فقط برای مدیر):\n• شهروندان: {role_counts['citizen']}\n• گمراهان: {role_counts['misled']}\n• جاسوس‌ها: {role_counts['spy']}\n\nکلمات به همه ارسال شد. بعد از اینکه همه صحبت کردن، رای‌گیری رو شروع کن.", keyboard)
    
    except Exception as e:
        send_message(chat_id, f"❌ خطا در شروع بازی: {str(e)}\n\nلطفاً با پشتیبانی تماس بگیرید.")
        print(f"Error in start_game_round: {e}")

def show_next_single_player(game_code, chat_id):
    """نمایش نقش بازیکن بعدی در حالت تک‌نفره"""
    try:
        data = pending_single_player_names.get(game_code)
        if not data:
            send_message(chat_id, "❌ خطا: اطلاعات بازی یافت نشد! لطفاً بازی را مجدداً شروع کنید.")
            return
        
        players = data.get('players', [])
        current_index = data.get('current_index', 0)
        round_number = data.get('round_number', 0)
        
        if not players:
            send_message(chat_id, "❌ خطا: لیست بازیکنان خالی است!")
            return
        
        if current_index >= len(players):
            send_message(chat_id, "✅ همه نقش‌ها نمایش داده شدند!\n\nاکنون می‌توانید رای‌گیری حضوری را شروع کنید.")
            del pending_single_player_names[game_code]
            return
        
        player_id, player_user_id, display_name, role = players[current_index]
        word_pair_id = get_word_pair_id_for_game(game_code)
        
        if not word_pair_id:
            send_message(chat_id, f"❌ خطا: کلمه‌ای برای بازی یافت نشد! لطفاً کلمات را به دیتابیس اضافه کنید.")
            return
        
        if role == 'spy':
            word = "🕵️‍♂️ شما جاسوس هستید! (کلمه‌ای نمی‌بینید)"
        else:
            word = get_word_for_role(word_pair_id, role)
            word = f"🔍 {word}"
        
        message = f"🎭 <b>بازیکن {current_index + 1} از {len(players)}</b>\n\n"
        message += f"👤 نام: {display_name}\n"
        message += f"🎭 نقش: {get_role_persian(role)}\n"
        message += f"📝 کلمه: {word}\n\n"
        message += f"📌 دور {round_number}"
        
        send_message(chat_id, message)
        
        data['current_index'] = current_index + 1
        pending_single_player_names[game_code] = data
        
    except Exception as e:
        send_message(chat_id, f"❌ خطا در نمایش نقش: {str(e)}")
        print(f"Error in show_next_single_player: {e}")

def get_word_pair_id_for_game(game_code):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT word_pair_id FROM games WHERE game_code = ?", (game_code,))
        result = c.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"Error in get_word_pair_id_for_game: {e}")
        return None
    finally:
        conn.close()
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
            
            # شروع بازی جدید - انتخاب حالت
            if data == "new_game":
                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT game_code FROM games WHERE status != 'finished' AND admin_id = ?", (user_id,))
                    existing_game = c.fetchone()
                except Exception as e:
                    send_message(chat_id, f"❌ خطا در بررسی بازی قبلی: {str(e)}")
                    return jsonify({"ok": True})
                finally:
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
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "👥 چند نفره", "callback_data": f"start_game_mode:multi:{user_id}"}],
                            [{"text": "📱 تک گوشی", "callback_data": f"start_game_mode:single:{user_id}"}]
                        ]
                    }
                    send_message(chat_id, "🎮 <b>حالت بازی را انتخاب کنید:</b>\n\n"
                                        "👥 <b>چند نفره:</b> هر بازیکن با گوشی خودش وارد می‌شود\n"
                                        "📱 <b>تک گوشی:</b> همه روی یک گوشی بازی می‌کنند", keyboard)
            
            elif data.startswith("start_game_mode:"):
                parts = data.split(":")
                game_mode = parts[1]
                admin_id = int(parts[2])
                if user_id == admin_id:
                    start_new_game(chat_id, user_id, game_mode)
            
            elif data.startswith("confirm_new_game:"):
                admin_id = int(data.split(":")[1])
                if user_id == admin_id:
                    conn = sqlite3.connect(DB_FILE, timeout=10)
                    c = conn.cursor()
                    try:
                        c.execute("DELETE FROM games WHERE admin_id = ? AND status != 'finished'", (admin_id,))
                        c.execute("DELETE FROM players WHERE game_code IN (SELECT game_code FROM games WHERE admin_id = ?)", (admin_id,))
                        conn.commit()
                    except Exception as e:
                        send_message(chat_id, f"❌ خطا در حذف بازی قبلی: {str(e)}")
                        return jsonify({"ok": True})
                    finally:
                        conn.close()
                    
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "👥 چند نفره", "callback_data": f"start_game_mode:multi:{user_id}"}],
                            [{"text": "📱 تک گوشی", "callback_data": f"start_game_mode:single:{user_id}"}]
                        ]
                    }
                    send_message(chat_id, "🎮 <b>حالت بازی را انتخاب کنید:</b>\n\n"
                                        "👥 <b>چند نفره:</b> هر بازیکن با گوشی خودش وارد می‌شود\n"
                                        "📱 <b>تک گوشی:</b> همه روی یک گوشی بازی می‌کنند", keyboard)
            
            elif data.startswith("finish_register:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
                    count = c.fetchone()[0]
                except Exception as e:
                    send_message(chat_id, f"❌ خطا در شمارش بازیکنان: {str(e)}")
                    return jsonify({"ok": True})
                finally:
                    conn.close()
                
                if count < 3:
                    send_message(chat_id, f"⚠️ تعداد بازیکنان ({count}) کافی نیست!\n\nحداقل ۳ نفر برای شروع بازی لازمه.\n\nبازیکنان بیشتری ثبت‌نام کنن.")
                else:
                    start_game_round(game_code, chat_id)
            
            elif data.startswith("single_next:"):
                game_code = data.split(":")[1]
                show_next_single_player(game_code, chat_id)
            
            elif data.startswith("start_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])
                
                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
                    conn.commit()
                except Exception as e:
                    send_message(chat_id, f"❌ خطا در شروع رای‌گیری: {str(e)}")
                    return jsonify({"ok": True})
                finally:
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
                
                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
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
                    send_message(chat_id, "✅ رای شما ثبت شد!")
                except Exception as e:
                    send_message(chat_id, f"❌ خطا در ثبت رای: {str(e)}")
                finally:
                    conn.close()
            
            elif data.startswith("finish_voting:") or data.startswith("finish_tie_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])
                finish_voting_round(game_code, round_id, chat_id)
            
            elif data.startswith("new_round:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                try:
                    c.execute("UPDATE players SET is_alive = 1 WHERE game_code = ?", (game_code,))
                    c.execute("UPDATE games SET status = 'playing' WHERE game_code = ?", (game_code,))
                    conn.commit()
                except Exception as e:
                    send_message(chat_id, f"❌ خطا در شروع دور جدید: {str(e)}")
                    return jsonify({"ok": True})
                finally:
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
        
        # ================ شروع ربات ================
        if text == "/start":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎮 شروع بازی جدید", "callback_data": "new_game"}]
                ]
            }
            send_message(chat_id, "🕵️‍♂️ <b>به ربات جاسوس پیشرفته خوش اومدی!</b>\n\nیه بازی گروهی جذاب برای کشف جاسوس بین دوستان.", keyboard)
            return jsonify({"ok": True})
        # ================ حالت تک‌نفره - دریافت تعداد بازیکنان و اسامی ================
        is_single_mode = False
        game_code = None
        
        conn = sqlite3.connect(DB_FILE, timeout=10)
        c = conn.cursor()
        try:
            c.execute("SELECT game_code FROM games WHERE admin_id = ? AND game_mode = 'single' AND status = 'registering'", (user_id,))
            single_game = c.fetchone()
        except Exception as e:
            print(f"Error finding single game: {e}")
            single_game = None
        finally:
            conn.close()
        
        if single_game:
            game_code = single_game[0]
            is_single_mode = True
        
        if is_single_mode and game_code:
            if game_code in pending_single_player_names:
                data = pending_single_player_names[game_code]
                
                if data.get('step') == 'awaiting_count':
                    try:
                        count = int(text)
                        if 3 <= count <= 20:
                            data['count'] = count
                            data['names'] = []
                            data['step'] = 'collecting_names'
                            pending_single_player_names[game_code] = data
                            
                            send_message(chat_id, f"✅ تعداد بازیکنان: {count} نفر\n\n"
                                                 f"لطفاً اسامی بازیکنان را ارسال کنید.\n\n"
                                                 f"📝 می‌توانید هر اسم را در یک خط جداگانه یا در پیام‌های جداگانه بفرستید.\n"
                                                 f"(برای اتمام، {count} اسم باید ارسال شود)")
                        else:
                            send_message(chat_id, "❌ تعداد باید بین ۳ تا ۲۰ باشد. لطفاً دوباره تلاش کن.")
                    except ValueError:
                        send_message(chat_id, "❌ لطفاً یک عدد معتبر وارد کنید (۳ تا ۲۰).")
                    return jsonify({"ok": True})
                
                elif data.get('step') == 'collecting_names':
                    names_to_add = []
                    if '\n' in text:
                        names_to_add = [name.strip() for name in text.split('\n') if name.strip()]
                    else:
                        names_to_add = [text.strip()]
                    
                    valid_names = []
                    for name in names_to_add:
                        if len(name) >= 2:
                            valid_names.append(name)
                        else:
                            send_message(chat_id, f"❌ اسم «{name}» کمتر از ۲ کاراکتر است. لطفاً دوباره تلاش کن.")
                            return jsonify({"ok": True})
                    
                    data['names'].extend(valid_names)
                    current_count = len(data['names'])
                    total_count = data['count']
                    
                    if current_count >= total_count:
                        conn = sqlite3.connect(DB_FILE, timeout=10)
                        c = conn.cursor()
                        try:
                            for name in data['names'][:total_count]:
                                c.execute("""
                                    INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
                                    VALUES (?, ?, ?, 'citizen', 1, 0, ?)
                                """, (game_code, user_id, name, datetime.now().isoformat()))
                            conn.commit()
                            
                            c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
                            registered_count = c.fetchone()[0]
                            print(f"✅ {registered_count} بازیکن در دیتابیس ثبت شد.")
                        except Exception as e:
                            send_message(chat_id, f"❌ خطا در ذخیره اسامی: {str(e)}")
                            return jsonify({"ok": True})
                        finally:
                            conn.close()
                        
                        del pending_single_player_names[game_code]
                        
                        send_message(chat_id, f"✅ {total_count} بازیکن ثبت شدند!\n\n" + 
                                     "\n".join([f"{i+1}. {name}" for i, name in enumerate(data['names'][:total_count])]) + 
                                     "\n\n🔄 در حال شروع بازی...")
                        
                        time.sleep(1)
                        start_game_round(game_code, chat_id)
                    else:
                        remaining = total_count - current_count
                        pending_single_player_names[game_code] = data
                        send_message(chat_id, f"✅ {current_count} اسم ثبت شد.\n\n"
                                             f"لطفاً {remaining} اسم دیگر را ارسال کنید.\n"
                                             f"(می‌توانید چند اسم را در یک پیام با خط جدید ارسال کنید)")
                    return jsonify({"ok": True})
            else:
                try:
                    count = int(text)
                    if 3 <= count <= 20:
                        pending_single_player_names[game_code] = {
                            'count': count,
                            'names': [],
                            'step': 'collecting_names'
                        }
                        send_message(chat_id, f"✅ تعداد بازیکنان: {count} نفر\n\n"
                                             f"لطفاً اسامی بازیکنان را ارسال کنید.\n\n"
                                             f"📝 می‌توانید هر اسم را در یک خط جداگانه یا در پیام‌های جداگانه بفرستید.\n"
                                             f"(برای اتمام، {count} اسم باید ارسال شود)")
                    else:
                        send_message(chat_id, "❌ تعداد باید بین ۳ تا ۲۰ باشد. لطفاً دوباره تلاش کن.")
                except ValueError:
                    send_message(chat_id, "❌ لطفاً یک عدد معتبر وارد کنید (۳ تا ۲۰).")
                return jsonify({"ok": True})
        
        # ================ ثبت‌نام در بازی چندنفره ================
        if text.startswith("/start register_"):
            game_code = text.replace("/start register_", "").strip()
            game_status = get_game_status(game_code)
            
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
            send_message(chat_id, "👤 لطفاً یک <b>اسم مستعار</b> برای خودت انتخاب کن:\n\n(این اسم توی بازی نمایش داده میشه)\n\n✏️ فقط اسم رو تایپ کن و بفرست.")
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
            except Exception as e:
                send_message(chat_id, f"❌ خطا در ثبت‌نام: {str(e)}")
                return jsonify({"ok": True})
            finally:
                conn.close()
            
            del pending_registrations[user_id]
            
            send_message(chat_id, f"✅ شما با اسم مستعار «{text.strip()}» در بازی ثبت‌نام شدید!\n\nمنتظر شروع بازی توسط مدیر باشید.")
            
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
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        alive_players = get_alive_players(game_code)
        total_players = len(alive_players)
        
        c.execute("SELECT COUNT(DISTINCT voter_id) FROM votes WHERE round_id = ?", (round_id,))
        voted_count = c.fetchone()[0]
        
        if voted_count < total_players:
            send_message(chat_id, f"⚠️ فقط {voted_count} نفر از {total_players} نفر رای دادن!\n\nهمه باید رای بدن. صبر کن تا همه رای بدن.")
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
    
    except Exception as e:
        print(f"Error in finish_voting_round: {e}")
        send_message(chat_id, f"❌ خطا در پایان رای‌گیری: {str(e)}")
    finally:
        conn.close()

def start_tie_voting_round(game_code, round_id, tied_player_ids, chat_id):
    alive_players = get_alive_players(game_code)
    
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("UPDATE games SET is_round_active = 1 WHERE game_code = ?", (game_code,))
        conn.commit()
    except Exception as e:
        print(f"Error in start_tie_voting_round: {e}")
        send_message(chat_id, f"❌ خطا در شروع رای‌گیری تساوی: {str(e)}")
        return
    finally:
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
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("SELECT user_id, display_name FROM players WHERE id = ? AND game_code = ?", (player_id, game_code))
        spy = c.fetchone()
        
        if not spy:
            return
        
        spy_user_id, spy_name = spy
        word_pair = get_game_word_pair(game_code)
        
        if not word_pair:
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
    except Exception as e:
        print(f"Error in handle_spy_elimination: {e}")
    finally:
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
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
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
    except Exception as e:
        print(f"Error in end_game: {e}")
        send_message(chat_id, f"❌ خطا در نمایش نتایج: {str(e)}")
        return
    finally:
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
    
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)", (word1, word2, category))
        conn.commit()
        return "جفت‌کلمه با موفقیت اضافه شد!"
    except Exception as e:
        return f"❌ خطا: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
