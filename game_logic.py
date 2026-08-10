import json
import os
import random
from datetime import datetime

from db import get_db
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

    if total_players not in ROLE_MAPPING:
        return {"ok": False, "error": "برای این تعداد بازیکن نقش‌بندی تعریف نشده است."}

    mapping = ROLE_MAPPING[total_players]
    roles = (
        [ROLE_SPY] * mapping[ROLE_SPY]
        + [ROLE_MISLED] * mapping[ROLE_MISLED]
        + [ROLE_CITIZEN] * mapping[ROLE_CITIZEN]
    )

    if len(roles) != total_players:
        return {"ok": False, "error": "تعداد نقش‌ها با تعداد بازیکن‌ها برابر نیست."}

    random.shuffle(roles)

    with get_db() as db:
        for player, role in zip(players, roles):
            db.execute(
                "UPDATE players SET role = ?, is_alive = 1 WHERE id = ?",
                (role, player["id"])
            )

    return {"ok": True, "mapping": mapping}


def send_roles_to_players(game_code, word_pair):
    players = get_players(game_code)
    for player in players:
        role = player["role"]

        if role == ROLE_CITIZEN:
            text = f"نقش شما: شهروند\nکلمه شما: {word_pair['word1']}"
        elif role == ROLE_MISLED:
            text = f"نقش شما: گمراه\nکلمه شما: {word_pair['word2']}"
        elif role == ROLE_SPY:
            text = "نقش شما: جاسوس\nشما کلمه‌ای دریافت نمی‌کنید."
        else:
            text = "نقش شما نامشخص است."

        send_message(player["user_id"], text)

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
        game_code=game_code,
        round_number=round_number,
        word_pair_id=None,
        is_round_active=1
    )
    set_game_status(game_code, GAME_STATUS_PLAYING)
    set_game_round_status(game_code, ROUND_STATUS_SPEAKING)
    reset_all_players_alive(game_code)

    round_id = create_round(
        game_code=game_code,
        round_number=round_number,
        word_pair_id=None,
        word1=word_pair["word1"],
        word2=word_pair["word2"],
        status=ROUND_STATUS_SPEAKING
    )

    send_roles_to_players(game_code, word_pair)

    send_message(
        chat_id,
        f"راند {round_number} شروع شد.\n"
        f"{get_role_counts_text(assign_result['mapping'], len(players))}\n\n"
        "نقش‌ها برای بازیکن‌ها در پی‌وی ارسال شد.\n"
        "مرحله فعلی: صحبت کردن"
    )

    return {"ok": True, "round_id": round_id, "round_number": round_number}


def add_score_to_team(game_code, team_role, score_points):
    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET score = score + ?
            WHERE game_code = ? AND role = ?
            """,
            (score_points, game_code, team_role)
        )


def add_score_to_multiple_teams(game_code, score_map):
    with get_db() as db:
        for role, points in score_map.items():
            db.execute(
                """
                UPDATE players
                SET score = score + ?
                WHERE game_code = ? AND role = ?
                """,
                (points, game_code, role)
            )


def end_current_game(game_code):
    current_round = get_current_round(game_code)
    if current_round:
        end_round(current_round["id"])

    set_game_round_active(game_code, 0)
    set_game_round_status(game_code, ROUND_STATUS_NONE)
    set_game_status(game_code, GAME_STATUS_REGISTERING)


def finish_game_by_rule(game_code, chat_id, winner_type, reason_text):
    if winner_type == ROLE_CITIZEN:
        add_score_to_team(game_code, ROLE_CITIZEN, SCORE_CITIZEN)
        score_text = f"شهروندها هر کدام {SCORE_CITIZEN} امتیاز گرفتند."
        winner_text = "شهروندها"

    elif winner_type == ROLE_SPY:
        add_score_to_team(game_code, ROLE_SPY, SCORE_SPY)
        score_text = f"جاسوس‌ها هر کدام {SCORE_SPY} امتیاز گرفتند."
        winner_text = "جاسوس‌ها"

    elif winner_type == ROLE_MISLED:
        add_score_to_team(game_code, ROLE_MISLED, SCORE_MISLED)
        score_text = f"گمراه‌ها هر کدام {SCORE_MISLED} امتیاز گرفتند."
        winner_text = "گمراه‌ها"

    elif winner_type == WINNER_SPY_MISLED:
        add_score_to_multiple_teams(
            game_code,
            {
                ROLE_SPY: SCORE_SPY,
                ROLE_MISLED: SCORE_MISLED,
            }
        )
        score_text = f"جاسوس‌ها {SCORE_SPY} امتیاز و گمراه‌ها {SCORE_MISLED} امتیاز گرفتند."
        winner_text = "جاسوس‌ها و گمراه‌ها"

    else:
        score_text = ""
        winner_text = winner_type

    end_current_game(game_code)

    send_message(
        chat_id,
        f"بازی تمام شد.\n\n"
        f"برنده: {winner_text}\n"
        f"دلیل: {reason_text}\n\n"
        f"{score_text}"
    )

    return {"ok": True, "game_finished": True, "winner": winner_type}


def evaluate_win_conditions(game_code, chat_id):
    counts = count_alive_roles(game_code)
    citizens = counts[ROLE_CITIZEN]
    spies = counts[ROLE_SPY]
    misleds = counts[ROLE_MISLED]

    if spies == 0 and misleds == 0 and citizens > 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_CITIZEN,
            "همه جاسوس‌ها و گمراه‌ها حذف شدند."
        )

    if citizens == 0 and spies > 0 and misleds > 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            WINNER_SPY_MISLED,
            "هیچ شهروند زنده‌ای در بازی باقی نمانده است."
        )

    if citizens == 0 and spies > 0 and misleds == 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_SPY,
            "هیچ شهروند زنده‌ای در بازی باقی نمانده است."
        )

    if citizens == 0 and misleds > 0 and spies == 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_MISLED,
            "هیچ شهروند زنده‌ای در بازی باقی نمانده است."
        )

    return {"ok": False, "message": "بازی هنوز ادامه دارد."}


def start_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند فعالی وجود ندارد."}

    alive_players = get_alive_players(game_code)
    if len(alive_players) < 2:
        return {"ok": False, "error": "بازیکن زنده کافی برای رأی‌گیری وجود ندارد."}

    set_round_status(current_round["id"], ROUND_STATUS_VOTING)
    set_game_round_status(game_code, ROUND_STATUS_VOTING)
    clear_round_votes(current_round["id"])

    send_message(
        chat_id,
        "مرحله رأی‌گیری شروع شد.\n"
        "اگر همه رأی بدهند، نتیجه خودکار مشخص می‌شود.\n"
        "اگر همه رأی ندادند، مدیر می‌تواند رأی‌گیری را تمام کند."
    )

    return {"ok": True, "round_id": current_round["id"]}


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


def build_vote_result(votes):
    vote_count = {}
    for vote in votes:
        target_id = vote["target_id"]
        vote_count[target_id] = vote_count.get(target_id, 0) + 1

    max_votes = max(vote_count.values())
    top_targets = [target_id for target_id, cnt in vote_count.items() if cnt == max_votes]
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
        return {"ok": False, "error": "بازیکن حذف‌شده پیدا نشد."}

    if eliminated_player["role"] == ROLE_SPY:
        current_round = get_current_round(game_code)
        if not current_round:
            return {"ok": False, "error": "راند پیدا نشد."}

        set_round_pending_spy(current_round["id"], eliminated_user_id)
        set_round_status(current_round["id"], ROUND_STATUS_AWAITING_SPY_GUESS)
        set_game_round_status(game_code, ROUND_STATUS_AWAITING_SPY_GUESS)

        send_message(
            chat_id,
            f"{eliminated_player['display_name']} حذف شد.\n"
            "او جاسوس بود، اما یک فرصت دارد کلمه اصلی شهروندها را حدس بزند."
        )
        send_message(
            eliminated_user_id,
            "شما حذف شده‌اید و جاسوس هستید.\n"
            "الان فرصت دارید کلمه اصلی شهروندها را برای ربات بفرستید."
        )

        return {
            "ok": True,
            "awaiting_spy_guess": True,
            "spy_user_id": eliminated_user_id
        }

    mark_player_dead(game_code, eliminated_user_id)

    send_message(
        chat_id,
        f"بازیکن {eliminated_player['display_name']} حذف شد.\n"
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
        "بازی هنوز ادامه دارد.\n"
        "دوباره درباره کلمه صحبت کنید و سپس مدیر رأی‌گیری بعدی را شروع کند."
    )

    return {"ok": True, "eliminated_user_id": eliminated_user_id}


def finish_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    votes = get_round_votes(current_round["id"])
    if not votes:
        return {"ok": False, "error": "هیچ رأیی ثبت نشده است."}

    vote_count, max_votes, top_targets = build_vote_result(votes)

    if len(top_targets) > 1:
        tie_break_level = current_round["tie_break_level"] or 0

        if tie_break_level == 0:
            return start_tie_voting_round(game_code, chat_id, top_targets)

        return start_admin_tie_resolution(game_code, chat_id, top_targets)

    return resolve_elimination_and_continue(game_code, chat_id, top_targets[0])


def start_tie_voting_round(game_code, chat_id, target_user_ids):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    clear_round_votes(current_round["id"])
    set_round_tie_state(
        current_round["id"],
        1,
        target_user_ids,
        ROUND_STATUS_TIE_VOTING
    )
    set_game_round_status(game_code, ROUND_STATUS_TIE_VOTING)

    players = []
    for user_id in target_user_ids:
        player = get_player_by_user_id(game_code, user_id)
        if player:
            players.append(player["display_name"])

    names_text = "، ".join(players) if players else "چند بازیکن"

    send_message(
        chat_id,
        f"رأی‌گیری مساوی شد.\n"
        f"بین این بازیکن‌ها دوباره رأی‌گیری می‌شود:\n{names_text}"
    )

    return {"ok": True, "tie_targets": target_user_ids, "tie_break_level": 1}


def start_admin_tie_resolution(game_code, chat_id, target_user_ids):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    set_round_tie_state(
        current_round["id"],
        2,
        target_user_ids,
        ROUND_STATUS_AWAITING_ADMIN_TIE_RESOLUTION
    )
    set_game_round_status(game_code, ROUND_STATUS_AWAITING_ADMIN_TIE_RESOLUTION)

    players = []
    for user_id in target_user_ids:
        player = get_player_by_user_id(game_code, user_id)
        if player:
            players.append(player["display_name"])

    names_text = "، ".join(players) if players else "چند بازیکن"

    send_message(
        chat_id,
        f"رأی‌گیری دوباره هم مساوی شد.\n"
        f"مدیر باید بعد از سنگ کاغذ قیچی حضوری، فرد حذف‌شده را از بین این افراد انتخاب کند:\n{names_text}"
    )

    return {"ok": True, "awaiting_admin_tie_resolution": True, "tie_targets": target_user_ids}


def admin_select_tie_loser(game_code, chat_id, selected_user_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    target_ids = json_loads(current_round["tie_target_data"], default=[])
    if selected_user_id not in target_ids:
        return {"ok": False, "error": "این بازیکن جزو افراد مساوی نیست."}

    set_round_pending_elimination(current_round["id"], selected_user_id)

    player = get_player_by_user_id(game_code, selected_user_id)
    if not player:
        return {"ok": False, "error": "بازیکن پیدا نشد."}

    return {
        "ok": True,
        "needs_confirmation": True,
        "selected_user_id": selected_user_id,
        "display_name": player["display_name"]
    }


def confirm_admin_selected_tie_loser(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    selected_user_id = current_round["pending_elimination_user_id"]
    if not selected_user_id:
        return {"ok": False, "error": "بازیکن انتخاب‌شده‌ای برای حذف ثبت نشده است."}

    return resolve_elimination_and_continue(game_code, chat_id, selected_user_id)


def cancel_admin_selected_tie_loser(game_code):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    set_round_pending_elimination(current_round["id"], None)
    return {"ok": True}


def process_spy_guess(game_code, chat_id, spy_user_id, guessed_word):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    pending_spy_user_id = current_round["pending_spy_user_id"]
    if pending_spy_user_id != spy_user_id:
        return {"ok": False, "error": "در حال حاضر نوبت حدس این کاربر نیست."}

    guessed_word = (guessed_word or "").strip()
    correct_word = (current_round["word1"] or "").strip()

    if guessed_word and guessed_word == correct_word:
        send_message(
            chat_id,
            f"جاسوس کلمه را درست حدس زد: {correct_word}\n"
            "جاسوس‌ها فوراً برنده شدند."
        )
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_SPY,
            "جاسوسِ حذف‌شده کلمه اصلی شهروندها را درست حدس زد."
        )

    mark_player_dead(game_code, spy_user_id)

    spy_player = get_player_by_user_id(game_code, spy_user_id)
    spy_name = spy_player["display_name"] if spy_player else str(spy_user_id)

    send_message(
        chat_id,
        f"جاسوس حذف‌شده نتوانست کلمه را درست حدس بزند.\n"
        f"حدس ثبت‌شده: {guessed_word if guessed_word else 'بدون پاسخ'}\n"
        f"نقش بازیکن حذف‌شده: جاسوس\n"
        f"نام بازیکن: {spy_name}"
    )

    result = evaluate_win_conditions(game_code, chat_id)
    if result.get("ok"):
        return result

    end_round(current_round["id"])
    set_game_round_status(game_code, ROUND_STATUS_SPEAKING)

    send_message(
        chat_id,
        "بازی هنوز ادامه دارد.\n"
        "دوباره درباره کلمه صحبت کنید و سپس مدیر رأی‌گیری بعدی را شروع کند."
    )

    return {"ok": True, "spy_guess_correct": False}


def force_end_spy_guess(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    spy_user_id = current_round["pending_spy_user_id"]
    if not spy_user_id:
        return {"ok": False, "error": "جاسوس منتظر حدسی ثبت نشده است."}

    return process_spy_guess(game_code, chat_id, spy_user_id, "")


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
