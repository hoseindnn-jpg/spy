import random
from datetime import datetime

from db import get_db
from telegram_api import send_message, edit_message_reply_markup, answer_callback_query


ROLE_CITIZEN = "citizen"
ROLE_SPY = "spy"
ROLE_MISLED = "misled"

GAME_STATUS_REGISTERING = "registering"
GAME_STATUS_PLAYING = "playing"

ROUND_STATUS_SPEAKING = "speaking"
ROUND_STATUS_VOTING = "voting"


ROLE_MAPPING = {
    3:  {ROLE_SPY: 0, ROLE_MISLED: 1, ROLE_CITIZEN: 2},
    4:  {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 2},
    5:  {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 3},
    6:  {ROLE_SPY: 1, ROLE_MISLED: 1, ROLE_CITIZEN: 4},
    7:  {ROLE_SPY: 1, ROLE_MISLED: 2, ROLE_CITIZEN: 4},
    8:  {ROLE_SPY: 1, ROLE_MISLED: 2, ROLE_CITIZEN: 5},
    9:  {ROLE_SPY: 2, ROLE_MISLED: 2, ROLE_CITIZEN: 5},
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
            "SELECT * FROM players WHERE game_code = ? AND is_alive = 1 ORDER BY id ASC",
            (game_code,)
        ).fetchall()


def get_player_by_user_id(game_code, user_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM players WHERE game_code = ? AND user_id = ?",
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


def get_word_pair_by_id(word_pair_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM word_pairs WHERE id = ?",
            (word_pair_id,)
        ).fetchone()


def get_random_word_pair():
    with get_db() as db:
        return db.execute(
            "SELECT * FROM word_pairs ORDER BY RANDOM() LIMIT 1"
        ).fetchone()


def increment_word_pair_used_count(word_pair_id):
    with get_db() as db:
        db.execute(
            "UPDATE word_pairs SET used_count = used_count + 1 WHERE id = ?",
            (word_pair_id,)
        )


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


def create_round(game_code, round_number, word_pair_id, status=ROUND_STATUS_SPEAKING):
    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO rounds (game_code, round_number, word_pair_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (game_code, round_number, word_pair_id, status, now_str())
        )
        return cursor.lastrowid


def set_round_status(round_id, status):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET status = ? WHERE id = ?",
            (status, round_id)
        )


def end_round(round_id):
    with get_db() as db:
        db.execute(
            "UPDATE rounds SET ended_at = ? WHERE id = ?",
            (now_str(), round_id)
        )


def clear_round_votes(round_id):
    with get_db() as db:
        db.execute(
            "DELETE FROM votes WHERE round_id = ?",
            (round_id,)
        )


def save_vote(round_id, voter_id, target_id):
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM votes WHERE round_id = ? AND voter_id = ?",
            (round_id, voter_id)
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE votes SET target_id = ?, voted_at = ? WHERE id = ?",
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


def count_alive_roles(game_code):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT role, COUNT(*) as cnt
            FROM players
            WHERE game_code = ? AND is_alive = 1
            GROUP BY role
            """,
            (game_code,)
        ).fetchall()

    result = {
        ROLE_CITIZEN: 0,
        ROLE_SPY: 0,
        ROLE_MISLED: 0
    }

    for row in rows:
        result[row["role"]] = row["cnt"]

    return result


def assign_roles(game_code):
    players = get_players(game_code)
    total_players = len(players)

    if total_players < 3 or total_players > 20:
        return {
            "ok": False,
            "error": "تعداد بازیکن‌ها باید بین ۳ تا ۲۰ نفر باشد."
        }

    if total_players not in ROLE_MAPPING:
        return {
            "ok": False,
            "error": "برای این تعداد بازیکن نقش‌بندی تعریف نشده است."
        }

    mapping = ROLE_MAPPING[total_players]

    roles = (
        [ROLE_SPY] * mapping[ROLE_SPY] +
        [ROLE_MISLED] * mapping[ROLE_MISLED] +
        [ROLE_CITIZEN] * mapping[ROLE_CITIZEN]
    )

    if len(roles) != total_players:
        return {
            "ok": False,
            "error": "تعداد نقش‌ها با تعداد بازیکن‌ها برابر نیست."
        }

    random.shuffle(roles)

    with get_db() as db:
        for player, role in zip(players, roles):
            db.execute(
                """
                UPDATE players
                SET role = ?, is_alive = 1
                WHERE id = ?
                """,
                (role, player["id"])
            )

    return {
        "ok": True,
        "mapping": mapping
    }


def send_roles_to_players(game_code):
    game = get_game(game_code)
    if not game:
        return {"ok": False, "error": "بازی پیدا نشد."}

    word_pair_id = game["word_pair_id"]
    word_pair = get_word_pair_by_id(word_pair_id)

    if not word_pair:
        return {"ok": False, "error": "کلمه‌های این راند پیدا نشد."}

    players = get_players(game_code)

    for player in players:
        role = player["role"]

        if role == ROLE_CITIZEN:
            text = (
                f"نقش شما: شهروند\n"
                f"کلمه شما: {word_pair['word1']}"
            )
        elif role == ROLE_MISLED:
            text = (
                f"نقش شما: گمراه\n"
                f"کلمه شما: {word_pair['word2']}"
            )
        elif role == ROLE_SPY:
            text = (
                "نقش شما: جاسوس\n"
                "شما کلمه‌ای دریافت نمی‌کنید."
            )
        else:
            text = "نقش شما نامشخص است."

        send_message(player["user_id"], text)

    return {"ok": True}


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
        return {"ok": False, "error": "هیچ جفت کلمه‌ای در دیتابیس وجود ندارد."}

    round_number = (game["round_number"] or 0) + 1

    set_game_round_info(
        game_code=game_code,
        round_number=round_number,
        word_pair_id=word_pair["id"],
        is_round_active=1
    )

    set_game_status(game_code, GAME_STATUS_PLAYING)
    reset_all_players_alive(game_code)

    round_id = create_round(
        game_code=game_code,
        round_number=round_number,
        word_pair_id=word_pair["id"],
        status=ROUND_STATUS_SPEAKING
    )

    increment_word_pair_used_count(word_pair["id"])

    send_roles_to_players(game_code)

    send_message(
        chat_id,
        f"راند {round_number} شروع شد.\n"
        f"نقش‌ها برای بازیکن‌ها ارسال شد.\n"
        f"مرحله فعلی: صحبت کردن"
    )

    return {
        "ok": True,
        "round_id": round_id,
        "round_number": round_number
    }


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
    set_game_status(game_code, GAME_STATUS_REGISTERING)


def finish_game_by_rule(game_code, chat_id, winner_type, reason_text):
    score_text = ""

    if winner_type == ROLE_CITIZEN:
        add_score_to_team(game_code, ROLE_CITIZEN, 2)
        score_text = "شهروندها هر کدام ۲ امتیاز گرفتند."

    elif winner_type == ROLE_SPY:
        add_score_to_team(game_code, ROLE_SPY, 6)
        score_text = "جاسوس‌ها هر کدام ۶ امتیاز گرفتند."

    elif winner_type == ROLE_MISLED:
        add_score_to_team(game_code, ROLE_MISLED, 10)
        score_text = "گمراه‌ها هر کدام ۱۰ امتیاز گرفتند."

    elif winner_type == "spy_misled":
        add_score_to_multiple_teams(game_code, {
            ROLE_SPY: 6,
            ROLE_MISLED: 10
        })
        score_text = "جاسوس‌ها ۶ امتیاز و گمراه‌ها ۱۰ امتیاز گرفتند."

    end_current_game(game_code)

    send_message(
        chat_id,
        f"بازی تمام شد.\n\n"
        f"برنده: {winner_type}\n"
        f"دلیل: {reason_text}\n\n"
        f"{score_text}"
    )

    return {"ok": True}


def evaluate_win_conditions(game_code, chat_id):
    counts = count_alive_roles(game_code)

    citizens = counts[ROLE_CITIZEN]
    spies = counts[ROLE_SPY]
    misleds = counts[ROLE_MISLED]

    # اگر جاسوسی نمانده باشد و گمراه هم نمانده باشد => شهروندها برنده
    if spies == 0 and misleds == 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_CITIZEN,
            "همه جاسوس‌ها و گمراه‌ها حذف شدند."
        )

    # اگر شهروندی نمانده باشد و جاسوس/گمراه باشند
    if citizens == 0 and spies > 0 and misleds > 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            "spy_misled",
            "شهروندی در بازی باقی نمانده است."
        )

    if citizens == 0 and spies > 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_SPY,
            "شهروندی در بازی باقی نمانده است."
        )

    if citizens == 0 and misleds > 0:
        return finish_game_by_rule(
            game_code,
            chat_id,
            ROLE_MISLED,
            "شهروندی در بازی باقی نمانده است."
        )

    return {"ok": False, "message": "بازی هنوز ادامه دارد."}


def start_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند فعالی وجود ندارد."}

    set_round_status(current_round["id"], ROUND_STATUS_VOTING)
    clear_round_votes(current_round["id"])

    alive_players = get_alive_players(game_code)
    if len(alive_players) < 2:
        return {"ok": False, "error": "بازیکن زنده کافی برای رأی‌گیری وجود ندارد."}

    send_message(
        chat_id,
        "مرحله رأی‌گیری شروع شد.\n"
        "بازیکن‌ها باید به فرد مشکوک رأی بدهند."
    )

    return {
        "ok": True,
        "round_id": current_round["id"]
    }


def finish_voting_round(game_code, chat_id):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    votes = get_round_votes(current_round["id"])
    if not votes:
        return {
            "ok": False,
            "error": "هیچ رأیی ثبت نشده است."
        }

    vote_count = {}
    for vote in votes:
        target_id = vote["target_id"]
        vote_count[target_id] = vote_count.get(target_id, 0) + 1

    max_votes = max(vote_count.values())
    top_targets = [target_id for target_id, cnt in vote_count.items() if cnt == max_votes]

    if len(top_targets) > 1:
        return start_tie_voting_round(game_code, chat_id, top_targets)

    eliminated_user_id = top_targets[0]

    with get_db() as db:
        db.execute(
            """
            UPDATE players
            SET is_alive = 0
            WHERE game_code = ? AND user_id = ?
            """,
            (game_code, eliminated_user_id)
        )

    eliminated_player = get_player_by_user_id(game_code, eliminated_user_id)
    if eliminated_player:
        send_message(
            chat_id,
            f"بازیکن {eliminated_player['display_name']} حذف شد.\n"
            f"نقش او: {eliminated_player['role']}"
        )
    else:
        send_message(chat_id, "یک بازیکن حذف شد.")

    result = evaluate_win_conditions(game_code, chat_id)
    if result.get("ok"):
        return result

    current_round = get_current_round(game_code)
    if current_round:
        end_round(current_round["id"])

    return {
        "ok": True,
        "eliminated_user_id": eliminated_user_id
    }


def start_tie_voting_round(game_code, chat_id, target_user_ids):
    current_round = get_current_round(game_code)
    if not current_round:
        return {"ok": False, "error": "راند پیدا نشد."}

    clear_round_votes(current_round["id"])

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

    return {
        "ok": True,
        "tie_targets": target_user_ids
    }


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
        role = player["role"]
        if role == ROLE_CITIZEN:
            role_fa = "شهروند"
        elif role == ROLE_SPY:
            role_fa = "جاسوس"
        elif role == ROLE_MISLED:
            role_fa = "گمراه"
        else:
            role_fa = role

        lines.append(f"- {player['display_name']}: {role_fa}")

    return "\n".join(lines)
