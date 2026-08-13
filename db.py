# db.py
import sqlite3
import os
import json
from contextlib import contextmanager

DB_FILE = os.getenv("DATABASE_PATH", os.getenv("DB_FILE", "bot_database.db"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        # ─── بازی‌ها ───
        db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_code TEXT PRIMARY KEY,
                admin_id INTEGER,
                status TEXT DEFAULT 'registering',
                round_status TEXT DEFAULT 'none',
                word_pair_id INTEGER,
                created_at TEXT,
                round_number INTEGER DEFAULT 0,
                is_round_active INTEGER DEFAULT 0,
                advanced_roles TEXT DEFAULT '[]',
                first_elimination_done INTEGER DEFAULT 0,
                winner_team TEXT
            )
        """)

        # ─── بازیکنان ───
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
                extra_role TEXT,
                extra_role_data TEXT,
                FOREIGN KEY(game_code) REFERENCES games(game_code),
                UNIQUE(game_code, user_id)
            )
        """)

        # ─── جفت‌کلمه‌ها ───
        db.execute("""
            CREATE TABLE IF NOT EXISTS word_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word1 TEXT NOT NULL,
                word2 TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                used_count INTEGER DEFAULT 0
            )
        """)

        # ─── راندها ───
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
                panto_user_id INTEGER,
                bomber_pending_user_id INTEGER,
                round_score_delta TEXT,
                started_at TEXT,
                ended_at TEXT,
                FOREIGN KEY(game_code) REFERENCES games(game_code)
            )
        """)

        # ─── رأی‌ها ───
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

        # ─── وضعیت کاربران ───
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                game_code TEXT,
                data TEXT
            )
        """)

        # ایندکس‌ها
        db.execute("CREATE INDEX IF NOT EXISTS idx_players_game_code ON players(game_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rounds_game_code ON rounds(game_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rounds_composite ON rounds(game_code, round_number)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_votes_round_id ON votes(round_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_votes_voter_id ON votes(voter_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_user_states_game_code ON user_states(game_code)")
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_round_voter_unique
            ON votes(round_id, voter_id)
        """)


# ─────────────── ابزار کمکی ───────────────
def now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(data):
    return json.dumps(data, ensure_ascii=False)


def json_loads(data, default=None):
    if not data:
        return default if default is not None else {}
    try:
        return json.loads(data)
    except Exception:
        return default if default is not None else {}


# ─────────────── بازی ───────────────
def create_game(game_code, admin_id):
    with get_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO games
                (game_code, admin_id, status, round_status, created_at)
            VALUES (?, ?, 'registering', 'none', ?)
            """,
            (game_code, admin_id, now_str())
        )


def get_game(game_code):
    with get_db() as db:
        return db.execute("SELECT * FROM games WHERE game_code = ?", (game_code,)).fetchone()


def update_game_status(game_code, status):
    with get_db() as db:
        db.execute("UPDATE games SET status = ? WHERE game_code = ?", (status, game_code))


def update_game_round_status(game_code, round_status):
    with get_db() as db:
        db.execute("UPDATE games SET round_status = ? WHERE game_code = ?", (round_status, game_code))


def update_game_round_info(game_code, round_number, word_pair_id, is_round_active):
    with get_db() as db:
        db.execute(
            """
            UPDATE games
            SET round_number = ?, word_pair_id = ?, is_round_active = ?
            WHERE game_code = ?
            """,
            (round_number, word_pair_id, is_round_active, game_code)
        )


def set_game_advanced_roles(game_code, role_list):
    with get_db() as db:
        db.execute(
            "UPDATE games SET advanced_roles = ? WHERE game_code = ?",
            (json_dumps(role_list), game_code)
        )


def get_game_advanced_roles(game_code):
    game = get_game(game_code)
    if not game:
        return []
    return json_loads(game["advanced_roles"], default=[])


def set_first_elimination_done(game_code):
    with get_db() as db:
        db.execute("UPDATE games SET first_elimination_done = 1 WHERE game_code = ?", (game_code,))


def set_game_winner(game_code, team):
    with get_db() as db:
        db.execute("UPDATE games SET winner_team = ? WHERE game_code = ?", (team, game_code))


# ─────────────── بازیکنان ───────────────
def add_player(game_code, user_id, display_name, role=None, is_alive=1, score=0, joined_at=None):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO players
                (game_code, user_id, display_name, role, is_alive, score, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_code, user_id) DO UPDATE SET
                display_name = excluded.display_name,
                role = excluded.role,
                is_alive = excluded.is_alive,
                score = excluded.score,
                joined_at = excluded.joined_at
            """,
            (game_code, user_id, display_name, role, is_alive, score, joined_at or now_str())
        )


def get_players(game_code):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? ORDER BY id ASC",
            (game_code,)
        ).fetchall()


def get_player(game_code, user_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
            (game_code, user_id)
        ).fetchone()


def get_alive_players(game_code):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? AND is_alive = 1 ORDER BY id ASC",
            (game_code,)
        ).fetchall()


def update_player_role(game_code, user_id, role):
    with get_db() as db:
        db.execute(
            "UPDATE players SET role = ? WHERE game_code = ? AND user_id = ?",
            (role, game_code, user_id)
        )


def update_player_alive(game_code, user_id, alive):
    with get_db() as db:
        db.execute(
            "UPDATE players SET is_alive = ? WHERE game_code = ? AND user_id = ?",
            (int(alive), game_code, user_id)
        )


def update_player_extra_role(game_code, user_id, extra_role, extra_role_data=None):
    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET extra_role = ?, extra_role_data = ?
            WHERE game_code = ? AND user_id = ?
            """,
            (extra_role, json_dumps(extra_role_data) if extra_role_data is not None else None,
             game_code, user_id)
        )


def update_player_extra_role_data(game_code, user_id, extra_role_data):
    with get_db() as db:
        db.execute(
            "UPDATE players SET extra_role_data = ? WHERE game_code = ? AND user_id = ?",
            (json_dumps(extra_role_data), game_code, user_id)
        )


def delete_player(game_code, user_id):
    with get_db() as db:
        db.execute("DELETE FROM players WHERE game_code = ? AND user_id = ?", (game_code, user_id))


def reset_players_alive(game_code):
    with get_db() as db:
        db.execute("UPDATE players SET is_alive = 1 WHERE game_code = ?", (game_code,))


def get_players_with_extra_role(game_code, extra_role):
    with get_db() as db:
        return db.execute(
            """
            SELECT * FROM players
            WHERE game_code = ? AND extra_role = ?
            """,
            (game_code, extra_role)
        ).fetchall()


# ─────────────── وضعیت کاربر ───────────────
def set_user_state(user_id, state, game_code=None, data=None):
    with get_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO user_states (user_id, state, game_code, data)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, state, game_code, data)
        )


def get_user_state(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM user_states WHERE user_id = ?", (user_id,)).fetchone()


def clear_user_state(user_id):
    with get_db() as db:
        db.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))


# ─────────────── کلمات ───────────────
def add_word_pair(word1, word2, category="general"):
    with get_db() as db:
        db.execute(
            "INSERT INTO word_pairs (word1, word2, category, used_count) VALUES (?, ?, ?, 0)",
            (word1, word2, category)
        )


def get_unused_word_pair():
    with get_db() as db:
        return db.execute(
            "SELECT * FROM word_pairs WHERE used_count = 0 ORDER BY id ASC LIMIT 1"
        ).fetchone()


def mark_word_pair_used(word_pair_id):
    with get_db() as db:
        db.execute("UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?", (word_pair_id,))


# ─────────────── راندها ───────────────
def create_round(
    game_code,
    round_number,
    word_pair_id=None,
    word1=None,
    word2=None,
    status="speaking"
):
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO rounds (
                game_code,
                round_number,
                word_pair_id,
                word1,
                word2,
                status,
                tie_break_level,
                tie_target_data,
                pending_elimination_user_id,
                pending_spy_user_id,
                panto_user_id,
                bomber_pending_user_id,
                round_score_delta,
                started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL, '{}', ?)
            """,
            (
                game_code,
                round_number,
                word_pair_id,
                word1,
                word2,
                status,
                now_str()
            )
        )
        return cursor.lastrowid


def get_current_round(game_code):
    with get_db() as db:
        return db.execute(
            """
            SELECT *
            FROM rounds
            WHERE game_code = ?
            ORDER BY round_number DESC, id DESC
            LIMIT 1
            """,
            (game_code,)
        ).fetchone()


def get_round_by_id(round_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM rounds WHERE id = ?",
            (round_id,)
        ).fetchone()


def update_round_status(round_id, status):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET status = ? WHERE id = ?",
            (status, round_id)
        )


def update_round_tie_state(round_id, tie_break_level, target_user_ids, status):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET tie_break_level = ?,
                tie_target_data = ?,
                status = ?
            WHERE id = ?
            """,
            (
                tie_break_level,
                json_dumps(target_user_ids),
                status,
                round_id
            )
        )


def get_round_tie_targets(round_id):
    round_data = get_round_by_id(round_id)

    if not round_data:
        return []

    return json_loads(round_data["tie_target_data"], default=[])


def set_round_pending_elimination(round_id, user_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET pending_elimination_user_id = ?
            WHERE id = ?
            """,
            (user_id, round_id)
        )


def clear_round_pending_elimination(round_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET pending_elimination_user_id = NULL
            WHERE id = ?
            """,
            (round_id,)
        )


def set_round_pending_spy(round_id, user_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET pending_spy_user_id = ?
            WHERE id = ?
            """,
            (user_id, round_id)
        )


def clear_round_pending_spy(round_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET pending_spy_user_id = NULL
            WHERE id = ?
            """,
            (round_id,)
        )


def set_round_panto_user(round_id, user_id):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET panto_user_id = ? WHERE id = ?",
            (user_id, round_id)
        )


def set_round_bomber_pending_user(round_id, user_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET bomber_pending_user_id = ?
            WHERE id = ?
            """,
            (user_id, round_id)
        )


def clear_round_bomber_pending_user(round_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET bomber_pending_user_id = NULL
            WHERE id = ?
            """,
            (round_id,)
        )


def get_round_score_delta(round_id):
    round_data = get_round_by_id(round_id)

    if not round_data:
        return {}

    return json_loads(round_data["round_score_delta"], default={})


def update_round_score_delta(round_id, user_id, delta):
    """
    امتیاز موقت نقش‌هایی مثل Duel را در همان دور نگه می‌دارد.
    این مقدار در پایان دور به score اصلی بازیکن اضافه می‌شود.
    """
    with get_db() as db:
        round_data = db.execute(
            "SELECT round_score_delta FROM rounds WHERE id = ?",
            (round_id,)
        ).fetchone()

        if not round_data:
            return False

        score_data = json_loads(round_data["round_score_delta"], default={})
        user_key = str(user_id)

        score_data[user_key] = int(score_data.get(user_key, 0)) + int(delta)

        db.execute(
            """
            UPDATE rounds
            SET round_score_delta = ?
            WHERE id = ?
            """,
            (json_dumps(score_data), round_id)
        )

    return True


def end_round(round_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET status = 'finished',
                ended_at = ?
            WHERE id = ?
            """,
            (now_str(), round_id)
        )


# ─────────────── رأی‌ها ───────────────
def save_vote(round_id, voter_id, target_id):
    """
    هر بازیکن در هر رأی‌گیری فقط یک رأی دارد.
    با رأی جدید، رأی قبلی او تغییر می‌کند.
    """
    with get_db() as db:
        old_vote = db.execute(
            """
            SELECT id
            FROM votes
            WHERE round_id = ? AND voter_id = ?
            """,
            (round_id, voter_id)
        ).fetchone()

        if old_vote:
            db.execute(
                """
                UPDATE votes
                SET target_id = ?, voted_at = ?
                WHERE id = ?
                """,
                (target_id, now_str(), old_vote["id"])
            )
        else:
            db.execute(
                """
                INSERT INTO votes (round_id, voter_id, target_id, voted_at)
                VALUES (?, ?, ?, ?)
                """,
                (round_id, voter_id, target_id, now_str())
            )


def get_votes_for_round(round_id):
    with get_db() as db:
        return db.execute(
            """
            SELECT *
            FROM votes
            WHERE round_id = ?
            ORDER BY id ASC
            """,
            (round_id,)
        ).fetchall()


def get_vote(round_id, voter_id):
    with get_db() as db:
        return db.execute(
            """
            SELECT *
            FROM votes
            WHERE round_id = ? AND voter_id = ?
            """,
            (round_id, voter_id)
        ).fetchone()


def get_voted_user_ids(round_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT voter_id FROM votes WHERE round_id = ?",
            (round_id,)
        ).fetchall()

    return {row["voter_id"] for row in rows}


def clear_round_votes(round_id):
    with get_db() as db:
        db.execute(
            "DELETE FROM votes WHERE round_id = ?",
            (round_id,)
        )


def count_votes(round_id):
    with get_db() as db:
        return db.execute(
            """
            SELECT target_id, COUNT(*) AS vote_count
            FROM votes
            WHERE round_id = ?
            GROUP BY target_id
            ORDER BY vote_count DESC, target_id ASC
            """,
            (round_id,)
        ).fetchall()


# ─────────────── امتیازها ───────────────
def add_player_score(game_code, user_id, amount):
    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET score = score + ?
            WHERE game_code = ? AND user_id = ?
            """,
            (int(amount), game_code, user_id)
        )


def apply_round_score_deltas(round_id, game_code):
    """
    امتیازهای موقت ثبت‌شده در rounds.round_score_delta
    را به امتیاز اصلی بازیکن‌ها اضافه می‌کند؛ مناسب نقش Duel.
    """
    score_data = get_round_score_delta(round_id)

    if not score_data:
        return

    with get_db() as db:
        for user_id, delta in score_data.items():
            db.execute(
                """
                UPDATE players
                SET score = score + ?
                WHERE game_code = ? AND user_id = ?
                """,
                (int(delta), game_code, int(user_id))
            )


def add_score_to_team(game_code, role, amount):
    """
    امتیاز تیمی را به تمام اعضای آن نقش می‌دهد؛
    چه زنده باشند و چه قبلاً حذف شده باشند.
    """
    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET score = score + ?
            WHERE game_code = ? AND role = ?
            """,
            (int(amount), game_code, role)
        )


def get_scoreboard(game_code):
    with get_db() as db:
        return db.execute(
            """
            SELECT *
            FROM players
            WHERE game_code = ?
            ORDER BY score DESC, display_name COLLATE NOCASE ASC
            """,
            (game_code,)
        ).fetchall()


# ─────────────── ابزارهای پایان/پاک‌سازی بازی ───────────────
def reset_game_for_next_round(game_code):
    """
    این تابع فقط وضعیت کلی را برای دور بعدی آماده می‌کند.
    نقش‌دهی، انتخاب کلمه و تعیین نقش‌های پیشرفته توسط game_logic انجام می‌شود.
    """
    with get_db() as db:
        db.execute(
            """
            UPDATE games
            SET round_status = 'none',
                is_round_active = 0,
                first_elimination_done = 0,
                winner_team = NULL
            WHERE game_code = ?
            """,
            (game_code,)
        )


def delete_game(game_code):
    """
    ابتدا داده‌های وابسته حذف می‌شوند تا دیتابیس تمیز بماند.
    """
    with get_db() as db:
        round_ids = db.execute(
            "SELECT id FROM rounds WHERE game_code = ?",
            (game_code,)
        ).fetchall()

        for row in round_ids:
            db.execute(
                "DELETE FROM votes WHERE round_id = ?",
                (row["id"],)
            )

        db.execute("DELETE FROM rounds WHERE game_code = ?", (game_code,))
        db.execute("DELETE FROM players WHERE game_code = ?", (game_code,))
        db.execute("DELETE FROM user_states WHERE game_code = ?", (game_code,))
        db.execute("DELETE FROM games WHERE game_code = ?", (game_code,))


def get_user_active_game(user_id):
    """
    بازی فعال کاربر را برمی‌گرداند.
    برای جلوگیری از حضور یک کاربر در چند لابی/بازی هم‌زمان استفاده می‌شود.
    """
    with get_db() as db:
        return db.execute(
            """
            SELECT g.*
            FROM games g
            INNER JOIN players p ON p.game_code = g.game_code
            WHERE p.user_id = ?
              AND g.status IN ('registering', 'playing')
            ORDER BY g.created_at DESC
            LIMIT 1
            """,
            (user_id,)
        ).fetchone()
