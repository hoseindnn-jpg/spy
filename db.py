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
        db.execute('''CREATE TABLE IF NOT EXISTS games 
                      (game_code TEXT PRIMARY KEY, admin_id INTEGER, status TEXT DEFAULT 'registering', 
                       created_at TEXT, round_number INTEGER DEFAULT 0, is_round_active INTEGER DEFAULT 0, 
                       word_pair_id INTEGER, game_mode TEXT DEFAULT 'multi')''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS players 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, game_code TEXT, user_id INTEGER, 
                       display_name TEXT, role TEXT, is_alive INTEGER DEFAULT 1, score INTEGER DEFAULT 0, 
                       joined_at TEXT, FOREIGN KEY(game_code) REFERENCES games(game_code))''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS word_pairs 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, word1 TEXT, word2 TEXT, 
                       category TEXT, used_count INTEGER DEFAULT 0)''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS rounds 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, game_code TEXT, round_number INTEGER, 
                       word_pair_id INTEGER, status TEXT DEFAULT 'speaking', started_at TEXT, ended_at TEXT,
                       FOREIGN KEY(game_code) REFERENCES games(game_code))''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS votes 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER, voter_id INTEGER, 
                       target_id INTEGER, voted_at TEXT,
                       FOREIGN KEY(round_id) REFERENCES rounds(id))''')

# --- توابع مدیریت کلمات ---
def add_word_pair(word1, word2, category="general"):
    with get_db() as db:
        db.execute("INSERT INTO word_pairs (word1, word2, category) VALUES (?, ?, ?)", (word1, word2, category))

def get_all_word_pairs():
    with get_db() as db:
        return db.execute("SELECT id, word1, word2, category, used_count FROM word_pairs ORDER BY id DESC").fetchall()

# --- توابع نمونه برای استفاده در منطق بازی (بقیه را طبق همین الگو بنویسید) ---
def get_game(game_code):
    with get_db() as db:
        return db.execute("SELECT * FROM games WHERE game_code = ?", (game_code,)).fetchone()

def update_game_status(game_code, status):
    with get_db() as db:
        db.execute("UPDATE games SET status = ? WHERE game_code = ?", (status, game_code))

def add_player(game_code, user_id, display_name):
    with get_db() as db:
        db.execute("INSERT INTO players (game_code, user_id, display_name) VALUES (?, ?, ?)", (game_code, user_id, display_name))
