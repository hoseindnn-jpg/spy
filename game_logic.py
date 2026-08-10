import json
import os
import random
from datetime import datetime

from db import get_db, set_user_state, clear_user_state
from telegram_api import send_message

ROLE_CITIZEN = "citizen"
ROLE_SPY = "spy"
ROLE_MISLED = "misled"

GAME_STATUS_REGISTERING = "registering"
GAME_STATUS_PLAYING = "playing"

ROUND_STATUS_SPEAKING = "speaking"
ROUND_STATUS_VOTING = "voting"
ROUND_STATUS_TIE_VOTING = "tie_voting"
ROUND_STATUS_AWAITING_ADMIN_TIE_RESOLUTION = "awaiting_admin_tie_resolution"
ROUND_STATUS_AWAITING_SPY_GUESS = "awaiting_spy_guess"

ROUND_STATUS_NONE = "none"

WINNER_SPY_MISLED = "spy_misled"

SCORE_CITIZEN = 2
SCORE_SPY = 5
SCORE_MISLED = 7

ROLE_MAPPING = {
    3: {ROLE_SPY: 0, ROLE_MISLED: 1, ROLE_CITIZEN: 2},
    4: {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 2},
    5: {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 3},
    6: {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 4},
    7: {ROLE_SPY: 1, ROLE_MISLED: 2, ROLE_CITIZEN: 4},
    8: {ROLE_SPY: 1, ROLE_MISLED: 2, ROLE_CITIZEN: 5},
    9: {ROLE_SPY: 2, ROLE_MISLED: 2, ROLE_CITIZEN: 5},
    10: {ROLE_SPY: 2, ROLE_MISLED: 2, ROLE_CITIZEN: 6},
    11: {ROLE_SPY: 2, ROLE_MISLED: 3, ROLE_CITIZEN: 6},
    12: {ROLE_SPY: 2, ROLE_MISLED: 3, ROLE_CITIZEN: 7},
    13: {ROLE_SPY: 2, ROLE_MISLED: 4, ROLE_CITIZEN: 7},
    14: {ROLE_SPY: 2, ROLE_MISLED: 4, ROLE_CITIZEN: 8},
    15: {ROLE_SPY: 3, ROLE_MISLED: 4, ROLE_CITIZEN: 8},
    16: {ROLE_SPY: 3, ROLE_MISLED: 5, ROLE_CITIZEN: 8},
    17: {ROLE_SPY: 3, ROLE_MISLED: 5, ROLE_CITIZEN: 9},
    18: {ROLE_SPY: 3, ROLE_MISLED: 5, ROLE_CITIZEN: 10},
    19: {ROLE_SPY: 3, ROLE_MISLED: 6, ROLE_CITIZEN: 10},
    20: {ROLE_SPY: 3, ROLE_MISLED: 6, ROLE_CITIZEN: 11},
}


def now_str():
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


def get_game(game_code):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM games WHERE game_code = ?",
            (game_code,)
        ).fetchone()


def get_players(game_code):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? ORDER BY id ASC",
            (game_code,)
        ).fetchall()


def get_alive_players(game_code):
    with get_db() as db:
        return db.execute(
            """
            SELECT * FROM players
            WHERE game_code = ? AND is_alive = 1
            ORDER BY id ASC
            """,
            (game_code,)
        ).fetchall()


def get_player_by_user_id(game_code, user_id):
    with get_db() as db:
        return db.execute(
            """
            SELECT * FROM players
            WHERE game_code = ? AND user_id = ?
            """,
            (game_code, user_id)
        ).fetchone()


def get_current_round(game_code):
    with get_db() as db:
        return db.execute(
            """
            SELECT * FROM rounds
            WHERE game_code = ?
            ORDER BY round_number DESC, id DESC
            LIMIT 1
            """,
            (game_code,)
        ).fetchone()


def get_random_word_pair():
    words_path = os.path.join(os.path.dirname(__file__), "words.json")

    if not os.path.exists(words_path):
        return None

    try:
        with open(words_path, "r", encoding="utf-8") as f:
            words = json.load(f)
    except Exception as exc:
        print(f"Error reading words.json: {exc}")
        return None

    if not isinstance(words, list) or not words:
        return None

    item = random.choice(words)

    if not isinstance(item, dict):
        return None

    if "word1" not in item or "word2" not in item:
        return None

    return item


def reset_all_players_alive(game_code):
    with get_db() as db:
        db.execute(
            "UPDATE players SET is_alive = 1 WHERE game_code = ?",
            (game_code,)
        )


def set_game_status(game_code, status):
    with get_db() as db:
        db.execute(
            "UPDATE games SET status = ? WHERE game_code = ?",
            (status, game_code)
        )


def set_game_round_status(game_code, round_status):
    with get_db() as db:
        db.execute(
            "UPDATE games SET round_status = ? WHERE game_code = ?",
            (round_status, game_code)
        )


def set_game_round_info(game_code, round_number, word_pair_id, is_round_active):
    with get_db() as db:
        db.execute(
            """
            UPDATE games
            SET round_number = ?, word_pair_id = ?, is_round_active = ?
            WHERE game_code = ?
            """,
            (round_number, word_pair_id, is_round_active, game_code)
        )


def set_game_round_active(game_code, is_active):
    with get_db() as db:
        db.execute(
            "UPDATE games SET is_round_active = ? WHERE game_code = ?",
            (is_active, game_code)
        )


def create_round(game_code, round_number, word_pair_id, word1, word2, status=ROUND_STATUS_SPEAKING):
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO rounds (
                game_code, round_number, word_pair_id, word1, word2, status,
                tie_break_level, tie_target_data, pending_elimination_user_id,
                pending_spy_user_id, started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?)
            """,
            (game_code, round_number, word_pair_id, word1, word2, status, now_str())
        )
        return cursor.lastrowid


def set_round_status(round_id, status):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET status = ? WHERE id = ?",
            (status, round_id)
        )


def set_round_tie_state(round_id, tie_break_level, target_user_ids, status):
    with get_db() as db:
        db.execute(
            """
            UPDATE rounds
            SET tie_break_level = ?, tie_target_data = ?, status = ?
            WHERE id = ?
            """,
            (tie_break_level, json_dumps(target_user_ids), status, round_id)
        )


def set_round_pending_elimination(round_id, user_id):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET pending_elimination_user_id = ? WHERE id = ?",
            (user_id, round_id)
        )


def set_round_pending_spy(round_id, user_id):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET pending_spy_user_id = ? WHERE id = ?",
            (user_id, round_id)
        )


def clear_round_votes(round_id):
    with get_db() as db:
        db.execute("DELETE FROM votes WHERE round_id = ?", (round_id,))


def end_round(round_id):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET ended_at = ? WHERE id = ?",
            (now_str(), round_id)
        )


def save_vote(round_id, voter_id, target_id):
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM votes WHERE round_id = ? AND voter_id = ?",
            (round_id, voter_id)
        ).fetchone()

        if existing:
            db.execute(
                """
                UPDATE votes
                SET target_id = ?, voted_at = ?
                WHERE id = ?
                """,
                (target_id, now_str(), existing["id"])
            )
        else:
            db.execute(
                """
                INSERT INTO votes (round_id, voter_id, target_id, voted_at)
                VALUES (?, ?, ?, ?)
                """,
                (round_id, voter_id, target_id, now_str())
            )


def get_round_votes(round_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM votes WHERE round_id = ?",
            (round_id,)
        ).fetchall()


def get_voted_user_ids(round_id):
    rows = get_round_votes(round_id)
    return {row["voter_id"] for row in rows}


def get_non_voters(game_code):
    current_round = get_current_round(game_code)

    if not current_round:
        return []

    alive_players = get_alive_players(game_code)
    voted_user_ids = get_voted_user_ids(current_round["id"])

    non_voters = []

    for player in alive_players:
        if player["user_id"] not in voted_user_ids:
            non_voters.append(player)

    return non_voters


def have_all_alive_players_voted(game_code):
    return len(get_non_voters(game_code)) == 0


def count_alive_roles(game_code):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT role, COUNT(*) AS cnt
            FROM players
            WHERE game_code = ? AND is_alive = 1
            GROUP BY role
            """,
            (game_code,)
        ).fetchall()

    result = {
        ROLE_CITIZEN: 0,
        ROLE_SPY: 0,
        ROLE_MISLED: 0,
    }

    for row in rows:
        result[row["role"]] = row["cnt"]

    return result


def assign_roles(game_code):
    players = get_players(game_code)
    total_players = len(players)

    if total_players < 3 or total_players > 20:
        return {"ok": False, "error": "تعداد بازیکن‌ها باید بین ۳ تا ۲۰ نفر باشد."}

    mapping = ROLE_MAPPING[total_players]

    roles = (
        [ROLE_SPY] * mapping[ROLE_SPY]
        + [ROLE_MISLED] * mapping[ROLE_MISLED]
        + [ROLE_CITIZEN] * mapping[ROLE_CITIZEN]
    )

    random.shuffle(roles)

    with get_db() as db:
        for player, role in zip(players, roles):
            db.execute(
                "UPDATE players SET role = ?, is_alive = 1 WHERE id = ?",
                (role, player["id"])
            )

    return {"ok": True, "mapping": mapping}


# =========================
# اصلاح ارسال نقش‌ها
# =========================
def send_roles_to_players(game_code, word_pair):
    players = get_players(game_code)

    for player in players:
        role = player["role"]

        if role == ROLE_SPY:
            text = (
                "🕵️‍♂️ شما جاسوس هستید.\n"
                "سعی کنید با صحبت‌های دیگران کلمه را حدس بزنید."
            )

        elif role == ROLE_MISLED:
            text = f"🔤 کلمه شما:\n{word_pair['word2']}"

        else:
            text = f"🔤 کلمه شما:\n{word_pair['word1']}"

        try:
            send_message(player["user_id"], text)
        except Exception as exc:
            print(f"Failed sending role to {player['user_id']}: {exc}")

    return {"ok": True}


def get_role_counts_text(mapping, total_players):
    return (
        f"تعداد بازیکن‌ها: {total_players}\n"
        f"تعداد جاسوس‌ها: {mapping[ROLE_SPY]}\n"
        f"تعداد گمراه‌ها: {mapping[ROLE_MISLED]}\n"
        f"تعداد شهروندها: {mapping[ROLE_CITIZEN]}"
    )


def start_game_round(game_code, chat_id):
    game = get_game(game_code)

    if not game:
        return {"ok": False, "error": "بازی پیدا نشد."}

    players = get_players(game_code)

    if len(players) < 3:
        return {"ok": False, "error": "حداقل ۳ بازیکن برای شروع بازی لازم است."}

    assign_result = assign_roles(game_code)

    if not assign_result["ok"]:
        return assign_result

    word_pair = get_random_word_pair()

    if not word_pair:
        return {"ok": False, "error": "فایل words.json پیدا نشد یا خالی است."}

    round_number = (game["round_number"] or 0) + 1

    set_game_round_info(
        game_code,
        round_number,
        None,
        1
    )

    set_game_status(game_code, GAME_STATUS_PLAYING)
    set_game_round_status(game_code, ROUND_STATUS_SPEAKING)

    round_id = create_round(
        game_code,
        round_number,
        None,
        word_pair["word1"],
        word_pair["word2"],
        ROUND_STATUS_SPEAKING
    )

    send_roles_to_players(game_code, word_pair)

    send_message(
        chat_id,
        f"🎮 راند {round_number} شروع شد.\n\n"
        "نقش‌ها و کلمه‌ها در پی‌وی بازیکنان ارسال شد.\n"
        "مرحله فعلی: صحبت کردن"
    )

    return {
        "ok": True,
        "round_id": round_id,
        "round_number": round_number
    }


def build_vote_result(votes):
    vote_count = {}

    for vote in votes:
        target_id = vote["target_id"]
        vote_count[target_id] = vote_count.get(target_id, 0) + 1

    max_votes = max(vote_count.values())

    top_targets = [
        target_id
        for target_id, cnt in vote_count.items()
        if cnt == max_votes
    ]

    return vote_count, max_votes, top_targets


def mark_player_dead(game_code, user_id):
    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET is_alive = 0
            WHERE game_code = ? AND user_id = ?
            """,
            (game_code, user_id)
        )


def resolve_elimination_and_continue(game_code, chat_id, eliminated_user_id):
    eliminated_player = get_player_by_user_id(game_code, eliminated_user_id)

    if not eliminated_player:
        return {"ok": False, "error": "بازیکن پیدا نشد."}

    if eliminated_player["role"] == ROLE_SPY:
        current_round = get_current_round(game_code)

        set_round_pending_spy(current_round["id"], eliminated_user_id)

        set_round_status(
            current_round["id"],
            ROUND_STATUS_AWAITING_SPY_GUESS
        )

        set_game_round_status(
            game_code,
            ROUND_STATUS_AWAITING_SPY_GUESS
        )

        # ثبت وضعیت برای app.py
        set_user_state(
            eliminated_user_id,
            "awaiting_spy_guess",
            game_code,
            game_code
        )

        send_message(
            chat_id,
            f"{eliminated_player['display_name']} حذف شد.\n"
            "او جاسوس بود و حالا یک فرصت برای حدس کلمه دارد."
        )

        send_message(
            eliminated_user_id,
            "🕵️‍♂️ شما حذف شدید.\n"
            "حالا کلمه اصلی شهروندها را برای ربات ارسال کنید."
        )

        return {
            "ok": True,
            "awaiting_spy_guess": True
        }

    mark_player_dead(game_code, eliminated_user_id)

    send_message(
        chat_id,
        f"❌ بازیکن {eliminated_player['display_name']} حذف شد.\n"
        f"نقش او: {role_to_fa(eliminated_player['role'])}"
    )

    result = evaluate_win_conditions(game_code, chat_id)

    if result.get("ok"):
        return result

    current_round = get_current_round(game_code)

    if current_round:
        end_round(current_round["id"])

    set_game_round_status(game_code, ROUND_STATUS_SPEAKING)

    send_message(
        chat_id,
        "🎮 بازی ادامه دارد.\n"
        "دوباره صحبت کنید و سپس رأی‌گیری جدید را شروع کنید."
    )

    return {"ok": True}


def finish_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)

    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    # جلوگیری از پایان رأی‌گیری قبل از رأی همه
    non_voters = get_non_voters(game_code)

    if non_voters:
        names = "، ".join([p["display_name"] for p in non_voters])

        send_message(
            chat_id,
            f"⛔ هنوز این بازیکنان رأی نداده‌اند:\n{names}"
        )

        return {
            "ok": False,
            "error": "همه بازیکنان رأی نداده‌اند."
        }

    votes = get_round_votes(current_round["id"])

    if not votes:
        return {"ok": False, "error": "هیچ رأیی ثبت نشده است."}

    vote_count, max_votes, top_targets = build_vote_result(votes)

    if len(top_targets) > 1:
        tie_break_level = current_round["tie_break_level"] or 0

        if tie_break_level == 0:
            return start_tie_voting_round(
                game_code,
                chat_id,
                top_targets
            )

        return start_admin_tie_resolution(
            game_code,
            chat_id,
            top_targets
        )

    return resolve_elimination_and_continue(
        game_code,
        chat_id,
        top_targets[0]
    )


def start_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)

    if not current_round:
        return {"ok": False, "error": "راند فعالی وجود ندارد."}

    alive_players = get_alive_players(game_code)

    if len(alive_players) < 2:
        return {"ok": False, "error": "بازیکن کافی وجود ندارد."}

    set_round_status(current_round["id"], ROUND_STATUS_VOTING)

    set_game_round_status(
        game_code,
        ROUND_STATUS_VOTING
    )

    clear_round_votes(current_round["id"])

    send_message(
        chat_id,
        "🗳 مرحله رأی‌گیری شروع شد."
    )

    return {
        "ok": True,
        "round_id": current_round["id"]
    }


def start_tie_voting_round(game_code, chat_id, target_user_ids):
    current_round = get_current_round(game_code)

    clear_round_votes(current_round["id"])

    set_round_tie_state(
        current_round["id"],
        1,
        target_user_ids,
        ROUND_STATUS_TIE_VOTING
    )

    set_game_round_status(
        game_code,
        ROUND_STATUS_TIE_VOTING
    )

    names = []

    for user_id in target_user_ids:
        player = get_player_by_user_id(game_code, user_id)

        if player:
            names.append(player["display_name"])

    send_message(
        chat_id,
        "⚖️ رأی‌ها مساوی شد.\n"
        f"بین این بازیکنان دوباره رأی‌گیری می‌شود:\n{'، '.join(names)}"
    )

    return {"ok": True}


def start_admin_tie_resolution(game_code, chat_id, target_user_ids):
    current_round = get_current_round(game_code)

    set_round_tie_state(
        current_round["id"],
        2,
        target_user_ids,
        ROUND_STATUS_AWAITING_ADMIN_TIE_RESOLUTION
    )

    set_game_round_status(
        game_code,
        ROUND_STATUS_AWAITING_ADMIN_TIE_RESOLUTION
    )

    return {
        "ok": True,
        "awaiting_admin_tie_resolution": True
    }


def admin_select_tie_loser(game_code, chat_id, selected_user_id):
    current_round = get_current_round(game_code)

    target_ids = json_loads(
        current_round["tie_target_data"],
        default=[]
    )

    if selected_user_id not in target_ids:
        return {
            "ok": False,
            "error": "این بازیکن در لیست مساوی‌ها نیست."
        }

    set_round_pending_elimination(
        current_round["id"],
        selected_user_id
    )

    player = get_player_by_user_id(game_code, selected_user_id)

    return {
        "ok": True,
        "display_name": player["display_name"]
    }


def confirm_admin_selected_tie_loser(game_code, chat_id):
    current_round = get_current_round(game_code)

    selected_user_id = current_round["pending_elimination_user_id"]

    return resolve_elimination_and_continue(
        game_code,
        chat_id,
        selected_user_id
    )


def process_spy_guess(game_code, chat_id, spy_user_id, guessed_word):
    current_round = get_current_round(game_code)

    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    if current_round["pending_spy_user_id"] != spy_user_id:
        return {
            "ok": False,
            "error": "اجازه حدس ندارید."
        }

    guessed_word = (guessed_word or "").strip()
    correct_word = (current_round["word1"] or "").strip()

    clear_user_state(spy_user_id)

    if guessed_word == correct_word:
        send_message(
            chat_id,
            f"🕵️ جاسوس کلمه را درست حدس زد:\n{correct_word}"
        )

        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_SPY,
            "جاسوس کلمه را درست حدس زد."
        )

    mark_player_dead(game_code, spy_user_id)

    send_message(
        chat_id,
        f"❌ جاسوس نتوانست کلمه را حدس بزند.\n"
        f"حدس ثبت‌شده: {guessed_word or 'بدون پاسخ'}"
    )

    result = evaluate_win_conditions(game_code, chat_id)

    if result.get("ok"):
        return result

    end_round(current_round["id"])

    set_game_round_status(
        game_code,
        ROUND_STATUS_SPEAKING
    )

    send_message(
        chat_id,
        "🎮 بازی ادامه دارد."
    )

    return {"ok": True}


def role_to_fa(role):
    if role == ROLE_CITIZEN:
        return "شهروند"

    if role == ROLE_SPY:
        return "جاسوس"

    if role == ROLE_MISLED:
        return "گمراه"

    return role

def get_scoreboard_text(game_code):
    players = get_players(game_code)
    if not players:
        return "هیچ بازیکنی در این بازی وجود ندارد."

    players = sorted(players, key=lambda x: x["score"], reverse=True)

    lines = ["🏆 امتیازات بازیکن‌ها:"]
    for index, player in enumerate(players, start=1):
        lines.append(f"{index}. {player['display_name']} - {player['score']} امتیاز")

    return "\n".join(lines)


def reveal_roles_text(game_code):
    players = get_players(game_code)
    if not players:
        return "هیچ بازیکنی در بازی نیست."

    lines = ["نقش بازیکن‌ها:"]
    for player in players:
        lines.append(f"- {player['display_name']}: {role_to_fa(player['role'])}")

    return "\n".join(lines)

