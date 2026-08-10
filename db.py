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
        # جدول بازی‌ها
        db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_code TEXT PRIMARY KEY,
                admin_id INTEGER,
                status TEXT DEFAULT 'registering',
                round_status TEXT DEFAULT 'none',
                word_pair_id INTEGER,
                created_at TEXT,
                round_number INTEGER DEFAULT 0,
                is_round_active INTEGER DEFAULT 0
            )
        """)

        # جدول بازیکنان
        db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT,
                is_alive INTEGER DEFAULT 1,
                score INTEGER DEFAULT 0,
                joined_at TEXT,
                FOREIGN KEY(game_code) REFERENCES games(game_code),
                UNIQUE(game_code, user_id)
            )
        """)

        # جدول کلمات
        db.execute("""
            CREATE TABLE IF NOT EXISTS word_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word1 TEXT NOT NULL,
                word2 TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                used_count INTEGER DEFAULT 0
            )
        """)

        # جدول راندها - نسخه هماهنگ با game_logic.py
        db.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_code TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                word_pair_id INTEGER,
                word1 TEXT,
                word2 TEXT,
                status TEXT DEFAULT 'speaking',
                tie_break_level INTEGER DEFAULT 0,
                tie_target_data TEXT,
                pending_elimination_user_id INTEGER,
                pending_spy_user_id INTEGER,
                started_at TEXT,
                ended_at TEXT,
                FOREIGN KEY(game_code) REFERENCES games(game_code)
            )
        """)

        # جدول رای‌ها
        db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                voter_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                voted_at TEXT,
                FOREIGN KEY(round_id) REFERENCES rounds(id)
            )
        """)

        # جدول وضعیت کاربران
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                game_code TEXT,
                data TEXT
            )
        """)

        # ایندکس‌ها برای سرعت بهتر
        db.execute("CREATE INDEX IF NOT EXISTS idx_players_game_code ON players(game_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rounds_game_code ON rounds(game_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rounds_composite ON rounds(game_code, round_number)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_votes_round_id ON votes(round_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_votes_voter_id ON votes(voter_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_user_states_game_code ON user_states(game_code)")


# --- وضعیت بازی ---
def set_game_round_status(game_code, status):
    with get_db() as db:
        db.execute("UPDATE games SET round_status = ? WHERE game_code = ?", (status, game_code))


def update_game_status(game_code, status):
    with get_db() as db:
        db.execute("UPDATE games SET status = ? WHERE game_code = ?", (status, game_code))


# --- وضعیت کاربر ---
def set_user_state(user_id, state, game_code=None, data=None):
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO user_states (user_id, state, game_code, data)
            VALUES (?, ?, ?, ?)
        """, (user_id, state, game_code, data))


def get_user_state(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM user_states WHERE user_id = ?", (user_id,)).fetchone()


def clear_user_state(user_id):
    with get_db() as db:
        db.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))


# --- بازی ---
def get_game(game_code):
    with get_db() as db:
        return db.execute("SELECT * FROM games WHERE game_code = ?", (game_code,)).fetchone()


# --- بازیکنان ---
def get_game_players(game_code):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? ORDER BY id ASC",
            (game_code,)
        ).fetchall()


def get_players(game_code):
    return get_game_players(game_code)


def remove_player(user_id, game_code):
    with get_db() as db:
        db.execute("DELETE FROM players WHERE user_id = ? AND game_code = ?", (user_id, game_code))


def add_player(game_code, user_id, display_name, role=None, is_alive=1, score=0, joined_at=None):
    with get_db() as db:
        db.execute("""
            INSERT INTO players (game_code, user_id, display_name, role, is_alive, score, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_code, user_id) DO UPDATE SET
                display_name = excluded.display_name,
                role = excluded.role,
                is_alive = excluded.is_alive,
                score = excluded.score,
                joined_at = excluded.joined_at
        """, (game_code, user_id, display_name, role, is_alive, score, joined_at))


# --- کلمات ---
def add_word_pair(word1, word2, category="general"):
    with get_db() as db:
        db.execute("""
            INSERT INTO word_pairs (word1, word2, category, used_count)
            VALUES (?, ?, ?, 0)
        """, (word1, word2, category))


def get_unused_word_pair():
    with get_db() as db:
        return db.execute("""
            SELECT * FROM word_pairs
            WHERE used_count = 0
            ORDER BY id ASC
            LIMIT 1
        """).fetchone()


def mark_word_pair_used(word_pair_id):
    with get_db() as db:
        db.execute("""
            UPDATE word_pairs
            SET used_count = used_count + 1
            WHERE id = ?
        """, (word_pair_id,))


# --- راندها ---
def create_round(game_code, round_number, word_pair_id, status="speaking", started_at=None):
    with get_db() as db:
        db.execute("""
            INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
        """, (game_code, round_number, word_pair_id, status, started_at))


def get_current_round(game_code):
    with get_db() as db:
        return db.execute("""
            SELECT * FROM rounds
            WHERE game_code = ?
            ORDER BY round_number DESC, id DESC
            LIMIT 1
        """, (game_code,)).fetchone()


# --- رأی‌ها ---
def save_vote(round_id, voter_id, target_id, voted_at=None):
    with get_db() as db:
        db.execute("""
            INSERT INTO votes (round_id, voter_id, target_id, voted_at)
            VALUES (?, ?, ?, ?)
        """, (round_id, voter_id, target_id, voted_at))


def get_votes_for_round(round_id):
    with get_db() as db:
        return db.execute("""
            SELECT * FROM votes WHERE round_id = ?
        """, (round_id,)).fetchall()
