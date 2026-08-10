import sqlite3
from contextlib import contextmanager
import os

DB_FILE = os.getenv("DB_FILE", "bot_database.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        # جدول بازی‌ها: اضافه شدن ستون round_status برای مدیریت فازهای بازی (رای‌گیری، حدس جاسوس، تساوی و...)
        db.execute('''CREATE TABLE IF NOT EXISTS games 
                      (game_code TEXT PRIMARY KEY, admin_id INTEGER, status TEXT DEFAULT 'registering', 
                       round_status TEXT DEFAULT 'none', word_pair_id INTEGER, 
                       created_at TEXT, round_number INTEGER DEFAULT 0, is_round_active INTEGER DEFAULT 0)''')
        
        # جدول بازیکنان: ثابت است (تغییری نیاز نداشت)
        db.execute('''CREATE TABLE IF NOT EXISTS players 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, game_code TEXT, user_id INTEGER, 
                       display_name TEXT, role TEXT, is_alive INTEGER DEFAULT 1, score INTEGER DEFAULT 0, 
                       joined_at TEXT, FOREIGN KEY(game_code) REFERENCES games(game_code))''')
        
        # جدول کلمات: ثابت است
        db.execute('''CREATE TABLE IF NOT EXISTS word_pairs 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, word1 TEXT, word2 TEXT, 
                       category TEXT, used_count INTEGER DEFAULT 0)''')
        
        # جدول راندها: ثابت است
        db.execute('''CREATE TABLE IF NOT EXISTS rounds 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, game_code TEXT, round_number INTEGER, 
                       word_pair_id INTEGER, status TEXT DEFAULT 'speaking', started_at TEXT, ended_at TEXT,
                       FOREIGN KEY(game_code) REFERENCES games(game_code))''')
        
        # جدول رای‌ها: ثابت است
        db.execute('''CREATE TABLE IF NOT EXISTS votes 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER, voter_id INTEGER, 
                       target_id INTEGER, voted_at TEXT,
                       FOREIGN KEY(round_id) REFERENCES rounds(id))''')
        
        # جدول وضعیت کاربران: فیلد data برای ذخیره اطلاعات موقت (مثل کلمه جاسوس یا آی‌دی تارگت‌های تساوی) حیاتی است
        db.execute('''CREATE TABLE IF NOT EXISTS user_states 
                      (user_id INTEGER PRIMARY KEY, state TEXT, game_code TEXT, data TEXT)''')

# --- توابع مدیریت وضعیت بازی (Game State Management) ---

def set_game_round_status(game_code, status):
    """تغییر وضعیت فاز بازی (مثلا: 'voting', 'spy_guess', 'tie_voting', 'none')"""
    with get_db() as db:
        db.execute("UPDATE games SET round_status = ? WHERE game_code = ?", (status, game_code))

def set_user_state(user_id, state, game_code=None, data=None):
    """ذخیره وضعیت کاربر (برای مدیریت حدس جاسوس یا مراحل خاص)"""
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO user_states (user_id, state, game_code, data) VALUES (?, ?, ?, ?)", 
                   (user_id, state, game_code, data))

def get_user_state(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM user_states WHERE user_id = ?", (user_id,)).fetchone()

# --- توابع مدیریت بازیکنان ---

def get_game_players(game_code):
    with get_db() as db:
        return db.execute("SELECT * FROM players WHERE game_code = ? ORDER BY id ASC", (game_code,)).fetchall()

def remove_player(user_id, game_code):
    with get_db() as db:
        db.execute("DELETE FROM players WHERE user_id = ? AND game_code = ?", (user_id, game_code))

# --- توابع پایه ---

def get_game(game_code):
    with get_db() as db:
        return db.execute("SELECT * FROM games WHERE game_code = ?", (game_code,)).fetchone()

def update_game_status(game_code, status):
    with get_db() as db:
        db.execute("UPDATE games SET status = ? WHERE game_code = ?", (status, game_code))

def add_player(game_code, user_id, display_name):
    # چک می‌کنیم اگر بازیکن قبلا عضو بوده و حذف شده، دوباره اضافه شود
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO players (game_code, user_id, display_name, is_alive) VALUES (?, ?, ?, 1)", 
                   (game_code, user_id, display_name))

def add_word_pair(word1, word2, category="general"):
    with get_db() as db:
        db.execute("INSERT INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)", (word1, word2, category))
