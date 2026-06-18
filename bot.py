from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import requests
from datetime import datetime

app = Flask(__name__)

TOKEN = "8898647964:AAHDany4sKVKfTbjaBFFg2lsQNnyad6gMg4"  # توکن ربات جدید رو اینجا بذار
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_FILE = "spy_game.db"

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
    load_words_from_json()

    # بازی‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS games (
                    game_code TEXT PRIMARY KEY,
                    admin_id INTEGER,
                    status TEXT DEFAULT 'registering',  -- registering, playing, finished
                    created_at TEXT,
                    round_number INTEGER DEFAULT 0
                 )''')
    
    # بازیکنان
    c.execute('''CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY,
                    game_code TEXT,
                    user_id INTEGER,
                    display_name TEXT,
                    role TEXT,  -- citizen, misled, spy
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
                    status TEXT DEFAULT 'speaking',  -- speaking, voting, finished
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

init_db()

# ================ توابع کمکی ================

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
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

def get_game_status(game_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT status FROM games WHERE game_code = ?", (game_code,))
    status = c.fetchone()
    conn.close()
    return status[0] if status else None

# ================ توزیع نقش‌ها ================
def assign_roles(game_code, players_count):
    """توزیع نقش‌ها بین بازیکنان"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # دریافت لیست بازیکنان زنده
    c.execute("SELECT id FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
    players = c.fetchall()
    player_ids = [p[0] for p in players]
    
    # محاسبه تعداد نقش‌ها
    total = len(player_ids)
    if total < 4:
        spy_count = 1
        misled_count = 1
    elif total < 7:
        spy_count = 1
        misled_count = 2
    else:
        spy_count = 2
        misled_count = 3
    
    citizen_count = total - spy_count - misled_count
    
    # ایجاد لیست نقش‌ها
    roles = ['citizen'] * citizen_count + ['misled'] * misled_count + ['spy'] * spy_count
    random.shuffle(roles)
    
    # اختصاص نقش به بازیکنان
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
    else:  # spy
        return None  # جاسوس کلمه نمی‌بینه

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
            message_id = cb["message"]["message_id"]
            
            # شروع بازی جدید از صفحه اصلی
            # شروع بازی جدید از صفحه اصلی
if data == "new_game":
    game_code = generate_code()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO games (game_code, admin_id, status, created_at) VALUES (?, ?, 'registering', ?)",
              (game_code, user_id, datetime.now().isoformat()))
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
            
            # دریافت لینک ثبت‌نام
            elif data.startswith("get_link:"):
                game_code = data.split(":")[1]
                bot_info = requests.get(f"{BASE_URL}/getMe").json()
                bot_username = bot_info['result']['username']
                register_link = f"https://t.me/{bot_username}?start=register_{game_code}"
                
                send_message(chat_id, f"🔗 لینک ثبت‌نام در بازی:\n{register_link}\n\nاین لینک رو برای دوستان بفرست تا بتونن عضو بشن.", disable_web_page_preview=True)
            
            # پایان ثبت‌نام
            elif data.startswith("finish_register:"):
                game_code = data.split(":")[1]
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                
                # بررسی تعداد بازیکنان
                c.execute("SELECT COUNT(*) FROM players WHERE game_code = ?", (game_code,))
                count = c.fetchone()[0]
                
                if count < 4:
                    send_message(chat_id, f"⚠️ تعداد بازیکنان ({count}) کافی نیست!\n\nحداقل ۴ نفر برای شروع بازی لازمه.\n\nبازیکنان بیشتری ثبت‌نام کنن.")
                else:
                    # توزیع نقش‌ها
                    role_counts = assign_roles(game_code, count)
                    
                    # انتخاب جفت کلمه
                    word_pair = get_word_pair()
                    if not word_pair:
                        send_message(chat_id, "❌ هیچ جفت کلمه‌ای در دیتابیس وجود نداره! لطفاً ابتدا کلمات رو اضافه کن.")
                        conn.close()
                        return jsonify({"ok": True})
                    
                    word_pair_id, word1, word2, category = word_pair
                    
                    # ذخیره دور جدید
                    c.execute("UPDATE games SET status = 'playing', round_number = round_number + 1 WHERE game_code = ?", 
                             (game_code,))
                    c.execute("SELECT round_number FROM games WHERE game_code = ?", (game_code,))
                    round_number = c.fetchone()[0]
                    
                    c.execute("INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at) VALUES (?, ?, ?, 'speaking', ?)",
                              (game_code, round_number, word_pair_id, datetime.now().isoformat()))
                    round_id = c.lastrowid
                    
                    # افزایش تعداد استفاده از کلمه
                    c.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))
                    
                    conn.commit()
                    
                    # ارسال کلمات به بازیکنان
                    c.execute("SELECT id, user_id, role FROM players WHERE game_code = ? AND is_alive = 1", (game_code,))
                    players = c.fetchall()
                    
                    for player_id, player_user_id, role in players:
                        if role == 'spy':
                            word_to_send = "🕵️‍♂️ شما <b>جاسوس</b> هستید!\n\nسعی کن کلمه‌ی بقیه رو حدس بزنی و خودت رو لو ندی."
                        else:
                            word = get_word_for_role(word_pair_id, role)
                            word_to_send = f"🔍 کلمه‌ی شما: <b>{word}</b>\n\nنقش شما: {'شهروند' if role == 'citizen' else 'گمراه'}"
                        
                        send_message(player_user_id, f"🎮 <b>دور {round_number} شروع شد!</b>\n\n{word_to_send}\n\nهر نفر به ترتیب یک کلمه مرتبط بگه.")
                    
                    conn.close()
                    
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🗳️ شروع رای‌گیری", "callback_data": f"start_voting:{game_code}:{round_id}"}]
                        ]
                    }
                    send_message(chat_id, f"✅ ثبت‌نام تموم شد! {count} نفر عضو شدن.\n\n📊 تعداد نقش‌ها:\n• شهروندان: {role_counts['citizen']}\n• گمراهان: {role_counts['misled']}\n• جاسوس‌ها: {role_counts['spy']}\n\nکلمات به همه ارسال شد. بعد از اینکه همه صحبت کردن، رای‌گیری رو شروع کن.", keyboard)
            
            # شروع رای‌گیری
            elif data.startswith("start_voting:"):
                parts = data.split(":")
                game_code = parts[1]
                round_id = int(parts[2])
                
                # بررسی اینکه همه صحبت کردن یا نه (در نسخه کامل)
                
                # نمایش دکمه‌های رای برای همه
                alive_players = get_alive_players(game_code)
                
                for player in alive_players:
                    player_id, player_user_id, player_name, role = player
                    
                    # ساخت دکمه‌های رای (به جز خودش)
                    vote_buttons = []
                    for target in alive_players:
                        if target[0] != player_id:  # به خودش رای نده
                            vote_buttons.append([{"text": target[2], "callback_data": f"vote:{round_id}:{player_id}:{target[0]}"}])
                    
                    keyboard = {"inline_keyboard": vote_buttons}
                    send_message(player_user_id, f"🗳️ <b>دور رای‌گیری</b>\n\nبه کسی که فکر می‌کنی جاسوسه رای بده:", keyboard)
                
                # پیام به مدیر
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "✅ پایان رای‌گیری", "callback_data": f"finish_voting:{game_code}:{round_id}"}]
                    ]
                }
                send_message(chat_id, "🗳️ رای‌گیری شروع شد!\n\nهمه می‌تونن به یک نفر رای بدن.\nبعد از اینکه همه رای دادن، روی دکمه پایان رای‌گیری کلیک کن.", keyboard)
            
            # دریافت رای
            elif data.startswith("vote:"):
                parts = data.split(":")
                round_id = int(parts[1])
                voter_id = int(parts[2])
                target_id = int(parts[3])
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                
                # ذخیره یا بروزرسانی رای
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
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                
                # بررسی تعداد رای‌ها
                alive_players = get_alive_players(game_code)
                total_players = len(alive_players)
                
                c.execute("SELECT COUNT(DISTINCT voter_id) FROM votes WHERE round_id = ?", (round_id,))
                voted_count = c.fetchone()[0]
                
                if voted_count < total_players:
                    send_message(chat_id, f"⚠️ فقط {voted_count} نفر از {total_players} نفر رای دادن!\n\nهمه باید رای بدن. صبر کن تا همه رای بدن.")
                else:
                    # محاسبه بیشترین رای
                    c.execute("""
                        SELECT target_id, COUNT(*) as vote_count 
                        FROM votes 
                        WHERE round_id = ? 
                        GROUP BY target_id 
                        ORDER BY vote_count DESC, RANDOM()
                        LIMIT 1
                    """, (round_id,))
                    result = c.fetchone()
                    
                    if result:
                        target_id, vote_count = result
                        
                        # حذف بازیکن
                        c.execute("UPDATE players SET is_alive = 0 WHERE id = ?", (target_id,))
                        c.execute("SELECT display_name, role FROM players WHERE id = ?", (target_id,))
                        eliminated = c.fetchone()
                        
                        conn.commit()
                        conn.close()
                        
                        send_message(chat_id, f"⛔️ <b>{eliminated[0]}</b> با {vote_count} رای حذف شد!\n\nنقش اون: {eliminated[1]}")
                        
                        # بررسی شرایط برنده شدن (ادامه در نسخه کامل)
                    else:
                        conn.close()
                        send_message(chat_id, "❌ مشکلی در رای‌گیری پیش اومد!")
            
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
            
            # درخواست اسم مستعار
            send_message(chat_id, "👤 لطفاً یک <b>اسم مستعار</b> برای خودت انتخاب کن:\n\n(این اسم توی بازی نمایش داده میشه)")
            
            # ذخیره کاربر برای مرحله بعد (در نسخه کامل)
            return jsonify({"ok": True})
        
        # دریافت اسم مستعار (ادامه ثبت‌نام)
        # (در نسخه کامل)
        
        return jsonify({"ok": True})
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"ok": True})

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
