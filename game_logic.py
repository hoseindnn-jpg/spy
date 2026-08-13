# game_logic.py
import os
import random
import requests
from datetime import datetime

import db


BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None
REQUEST_TIMEOUT = 8


# ─────────────────────────────
# تنظیمات امتیاز طبق قوانین نهایی
# ─────────────────────────────
SCORE_CITIZEN = 2
SCORE_SPY = 4
SCORE_MISLED = 6

SCORE_CLOWN_BONUS = 2
SCORE_DUELIST_BONUS = 2


# ─────────────────────────────
# نقش‌های اصلی
# ─────────────────────────────
ROLE_CITIZEN = "citizen"
ROLE_SPY = "spy"
ROLE_MISLED = "misled"


# ─────────────────────────────
# نقش‌های اضافه
# ─────────────────────────────
EXTRA_BOOMERANG = "boomerang"
EXTRA_GHOST = "ghost"
EXTRA_PANTO = "panto"
EXTRA_BOMBER = "bomber"
EXTRA_LOVEBIRD = "lovebird"
EXTRA_CLOWN = "clown"
EXTRA_DUELIST = "duelist"


# ─────────────────────────────
# وضعیت‌های راند
# ─────────────────────────────
ROUND_SPEAKING = "speaking"
ROUND_VOTING = "voting"
ROUND_TIE_VOTING = "tie_voting"
ROUND_SPY_GUESS = "spy_guess"
ROUND_BOMBER_ACTION = "bomber_action"
ROUND_FINISHED = "finished"


# ─────────────────────────────
# ابزار ارسال پیام مستقیم با Telegram Bot API
# ─────────────────────────────
def send_message(chat_id, text, reply_markup=None):
    """
    ارسال پیام ساده با requests.
    اگر chat_id None باشد، ارسال انجام نمی‌شود.
    """
    if not BOT_TOKEN or not TELEGRAM_API_URL or not chat_id:
        return False

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        return response.ok
    except requests.RequestException:
        return False


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_name(player):
    if not player:
        return "نامشخص"
    return player["display_name"] or str(player["user_id"])


def role_fa(role):
    return {
        ROLE_CITIZEN: "شهروند",
        ROLE_SPY: "جاسوس",
        ROLE_MISLED: "گمراه"
    }.get(role, role or "نامشخص")


def extra_role_fa(extra_role):
    return {
        EXTRA_BOOMERANG: "بومرنگ",
        EXTRA_GHOST: "روح",
        EXTRA_PANTO: "پانتو",
        EXTRA_BOMBER: "بمب‌گذار",
        EXTRA_LOVEBIRD: "مرغ عشق",
        EXTRA_CLOWN: "دلقک",
        EXTRA_DUELIST: "دوئلیست"
    }.get(extra_role, "ندارد")


def normalize_user_id(value):
    try:
        return int(value)
    except Exception:
        return None


# ─────────────────────────────
# انتخاب کلمه
# ─────────────────────────────
def get_random_word_pair_from_db():
    """
    منبع اصلی کلمات: جدول word_pairs.
    ابتدا کلمه استفاده‌نشده می‌گیرد.
    اگر همه استفاده شده باشند، تصادفی از کل جدول می‌گیرد.
    """
    pair = db.get_unused_word_pair()
    if pair:
        return pair

    with db.get_db() as conn:
        return conn.execute(
            """
            SELECT *
            FROM word_pairs
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()


# ─────────────────────────────
# محاسبه تعداد جاسوس‌ها
# ─────────────────────────────
def calculate_spy_count(player_count):
    """
    قابل تغییر است، ولی برای بازی جاسوس معمولاً:
    4 تا 6 نفر: 1 جاسوس
    7 تا 10 نفر: 2 جاسوس
    11 به بالا: 3 جاسوس
    """
    if player_count <= 6:
        return 1
    if player_count <= 10:
        return 2
    return 3


def should_have_misled(player_count):
    """
    گمراه را از 5 نفر به بالا فعال می‌کنیم.
    """
    return player_count >= 5


# ─────────────────────────────
# تخصیص نقش‌های اصلی
# ─────────────────────────────
def assign_main_roles(game_code):
    players = db.get_players(game_code)
    players = list(players)

    if len(players) < 3:
        raise ValueError("برای شروع بازی حداقل ۳ بازیکن لازم است.")

    random.shuffle(players)

    spy_count = calculate_spy_count(len(players))
    has_misled = should_have_misled(len(players))

    spy_players = players[:spy_count]
    cursor_index = spy_count

    misled_player = None
    if has_misled and cursor_index < len(players):
        misled_player = players[cursor_index]
        cursor_index += 1

    citizen_players = players[cursor_index:]

    for p in spy_players:
        db.update_player_role(game_code, p["user_id"], ROLE_SPY)

    if misled_player:
        db.update_player_role(game_code, misled_player["user_id"], ROLE_MISLED)

    for p in citizen_players:
        db.update_player_role(game_code, p["user_id"], ROLE_CITIZEN)

    return {
        "spies": [p["user_id"] for p in spy_players],
        "misled": misled_player["user_id"] if misled_player else None,
        "citizens": [p["user_id"] for p in citizen_players]
    }


# ─────────────────────────────
# تخصیص نقش‌های اضافه
# ─────────────────────────────
def clear_extra_roles(game_code):
    players = db.get_players(game_code)
    for p in players:
        db.update_player_extra_role(game_code, p["user_id"], None, None)


def assign_extra_roles(game_code):
    """
    هیچ بازیکنی هم‌زمان دو نقش اضافه نمی‌گیرد.
    لیست نقش‌های فعال از games.advanced_roles خوانده می‌شود.
    """
    enabled_roles = db.get_game_advanced_roles(game_code)
    if not enabled_roles:
        return {}

    players = list(db.get_players(game_code))
    random.shuffle(players)

    assigned = {}

    available = players[:]

    def pop_player():
        if not available:
            return None
        return available.pop(0)

    # نقش مرغ عشق نیاز به دو نفر دارد
    if EXTRA_LOVEBIRD in enabled_roles and len(available) >= 2:
        p1 = pop_player()
        p2 = pop_player()

        db.update_player_extra_role(
            game_code,
            p1["user_id"],
            EXTRA_LOVEBIRD,
            {"partner_id": p2["user_id"]}
        )
        db.update_player_extra_role(
            game_code,
            p2["user_id"],
            EXTRA_LOVEBIRD,
            {"partner_id": p1["user_id"]}
        )

        assigned[EXTRA_LOVEBIRD] = [p1["user_id"], p2["user_id"]]

    # نقش دوئلیست نیاز به هدف دارد
    if EXTRA_DUELIST in enabled_roles and len(available) >= 1:
        duelist = pop_player()
        possible_targets = [
            p for p in players
            if p["user_id"] != duelist["user_id"]
        ]
        if possible_targets:
            target = random.choice(possible_targets)
            db.update_player_extra_role(
                game_code,
                duelist["user_id"],
                EXTRA_DUELIST,
                {"target_id": target["user_id"], "bonus_given": False}
            )
            assigned[EXTRA_DUELIST] = [duelist["user_id"]]

    simple_roles = [
        EXTRA_BOOMERANG,
        EXTRA_GHOST,
        EXTRA_PANTO,
        EXTRA_BOMBER,
        EXTRA_CLOWN
    ]

    for role in simple_roles:
        if role not in enabled_roles:
            continue

        p = pop_player()
        if not p:
            break

        initial_data = {}
        if role == EXTRA_BOOMERANG:
            initial_data = {"used": False}
        elif role == EXTRA_CLOWN:
            initial_data = {"bonus_given": False}
        elif role == EXTRA_BOMBER:
            initial_data = {"exploded": False}
        elif role == EXTRA_PANTO:
            initial_data = {"announced": False}

        db.update_player_extra_role(
            game_code,
            p["user_id"],
            role,
            initial_data
        )
        assigned[role] = [p["user_id"]]

    return assigned


# ─────────────────────────────
# شروع راند
def build_role_message(player, round_data, panto_user_id=None):
    """
    پیام خصوصی نقش هر بازیکن را می‌سازد.
    جاسوس word2 و شهروند/گمراه word1 را می‌بینند.
    """
    role = player["role"]
    extra_role = player["extra_role"]

    if role == ROLE_SPY:
        word = round_data["word2"]
        role_text = "🕵️ <b>نقش اصلی شما: جاسوس</b>"
    elif role == ROLE_MISLED:
        word = round_data["word1"]
        role_text = "😵‍💫 <b>نقش اصلی شما: گمراه</b>"
    else:
        word = round_data["word1"]
        role_text = "👤 <b>نقش اصلی شما: شهروند</b>"

    lines = [
        "🎮 <b>راند جدید شروع شد.</b>",
        "",
        role_text,
        f"🔐 <b>کلمه شما:</b> <code>{word}</code>"
    ]

    if extra_role:
        lines.extend([
            "",
            f"✨ <b>نقش اضافه شما:</b> {extra_role_fa(extra_role)}"
        ])

        extra_data = db.json_loads(player["extra_role_data"], default={})

        if extra_role == EXTRA_LOVEBIRD:
            partner_id = extra_data.get("partner_id")
            partner = db.get_player(player["game_code"], partner_id)
            if partner:
                lines.append(
                    f"💞 شریک مرغ عشق شما: <b>{safe_name(partner)}</b>"
                )

        elif extra_role == EXTRA_DUELIST:
            target_id = extra_data.get("target_id")
            target = db.get_player(player["game_code"], target_id)
            if target:
                lines.append(
                    f"⚔️ هدف دوئل شما: <b>{safe_name(target)}</b>"
                )
                lines.append(
                    "اگر هدف دوئل شما در این راند حذف شود، "
                    f"{SCORE_DUELIST_BONUS} امتیاز جایزه می‌گیرید."
                )

        elif extra_role == EXTRA_BOOMERANG:
            lines.append(
                "🪃 اگر با رأی‌گیری حذف شوید، رأی‌دهندگان شما حذف می‌شوند. "
                "این قابلیت فقط یک‌بار فعال می‌شود."
            )

        elif extra_role == EXTRA_GHOST:
            lines.append(
                "👻 بعد از حذف، می‌توانید فقط در رأی‌گیری شرکت کنید؛ "
                "اما نمی‌توانید نامزد رأی‌گیری شوید."
            )

        elif extra_role == EXTRA_BOMBER:
            lines.append(
                "💣 بعد از حذف، مدیر می‌تواند به شما فرصت دهد "
                "یک بازیکن زنده را برای انفجار انتخاب کنید."
            )

        elif extra_role == EXTRA_CLOWN:
            lines.append(
                "🤡 اگر با رأی‌گیری حذف شوید، "
                f"{SCORE_CLOWN_BONUS} امتیاز جایزه می‌گیرید."
            )

        elif extra_role == EXTRA_PANTO:
            lines.append(
                "🎭 شما پانتو هستید. مدیر بازی نیز از هویت شما اطلاع دارد."
            )

    if panto_user_id and player["user_id"] == panto_user_id:
        lines.append("")
        lines.append("🎭 <b>شما به‌صورت تصادفی به‌عنوان پانتو انتخاب شده‌اید.</b>")

    return "\n".join(lines)


def start_game_round(game_code):
    """
    شروع یک راند جدید:
    - تخصیص نقش اصلی
    - تخصیص نقش اضافه
    - انتخاب جفت‌کلمه از SQLite
    - ارسال نقش خصوصی
    - ساخت رکورد rounds
    """
    game = db.get_game(game_code)
    if not game:
        raise ValueError("بازی پیدا نشد.")

    players = list(db.get_players(game_code))
    if len(players) < 3:
        raise ValueError("برای شروع راند حداقل ۳ بازیکن لازم است.")

    # تمام بازیکنان موجود در شروع راند وارد راند جدید می‌شوند.
    db.reset_players_alive(game_code)
    clear_extra_roles(game_code)

    role_result = assign_main_roles(game_code)
    extra_result = assign_extra_roles(game_code)

    word_pair = get_random_word_pair_from_db()
    if not word_pair:
        raise ValueError(
            "هیچ جفت‌کلمه‌ای در جدول word_pairs وجود ندارد. "
            "ابتدا کلمات بازی را اضافه کنید."
        )

    next_round_number = int(game["round_number"] or 0) + 1

    round_id = db.create_round(
        game_code=game_code,
        round_number=next_round_number,
        word_pair_id=word_pair["id"],
        word1=word_pair["word1"],
        word2=word_pair["word2"],
        status=ROUND_SPEAKING
    )

    db.mark_word_pair_used(word_pair["id"])
    db.update_game_round_info(
        game_code,
        next_round_number,
        word_pair["id"],
        1
    )
    db.update_game_status(game_code, "playing")
    db.update_game_round_status(game_code, ROUND_SPEAKING)

    current_round = db.get_round_by_id(round_id)

    # پانتو را هم به مدیر و خودش اطلاع می‌دهیم.
    panto_user_id = None
    panto_players = db.get_players_with_extra_role(game_code, EXTRA_PANTO)
    if panto_players:
        panto_user_id = panto_players[0]["user_id"]
        db.set_round_panto_user(round_id, panto_user_id)

    # نقش‌ها از دیتابیس مجدداً خوانده می‌شوند، چون نقش اضافه تغییر کرده است.
    current_players = db.get_players(game_code)

    failed_messages = []
    for player in current_players:
        message = build_role_message(
            player=player,
            round_data=current_round,
            panto_user_id=panto_user_id
        )

        if not send_message(player["user_id"], message):
            failed_messages.append(player["user_id"])

    admin_message = [
        f"✅ <b>راند {next_round_number} شروع شد.</b>",
        f"👥 تعداد بازیکنان: {len(current_players)}",
        f"🕵️ تعداد جاسوس‌ها: {len(role_result['spies'])}",
        "🗣 مرحله فعلی: صحبت کردن"
    ]

    if panto_user_id:
        panto = db.get_player(game_code, panto_user_id)
        admin_message.append(f"🎭 پانتو: <b>{safe_name(panto)}</b>")

    if failed_messages:
        admin_message.append(
            "⚠️ پیام خصوصی بعضی بازیکنان ارسال نشد. "
            "آن‌ها باید ابتدا ربات را Start کرده باشند."
        )

    send_message(game["admin_id"], "\n".join(admin_message))

    return {
        "round_id": round_id,
        "round_number": next_round_number,
        "word_pair_id": word_pair["id"],
        "spies": role_result["spies"],
        "misled": role_result["misled"],
        "extra_roles": extra_result,
        "failed_messages": failed_messages
    }


# ─────────────────────────────
# رأی‌گیری
# ─────────────────────────────
def get_eligible_voters(game_code):
    """
    بازیکنان زنده حق رأی دارند.
    روحِ حذف‌شده هم فقط حق رأی دارد.
    """
    result = []

    for player in db.get_players(game_code):
        if player["is_alive"]:
            result.append(player)
            continue

        if player["extra_role"] == EXTRA_GHOST:
            result.append(player)

    return result


def get_eligible_vote_targets(game_code, tie_targets=None):
    """
    فقط بازیکن زنده می‌تواند هدف رأی باشد.
    روح حذف‌شده کاندیدا نمی‌شود.
    در رأی تساوی، فقط نامزدهای مساوی مجازند.
    """
    alive_players = list(db.get_alive_players(game_code))

    if tie_targets is None:
        return alive_players

    allowed_ids = {normalize_user_id(user_id) for user_id in tie_targets}
    return [
        player for player in alive_players
        if player["user_id"] in allowed_ids
    ]


def start_voting(game_code):
    game = db.get_game(game_code)
    current_round = db.get_current_round(game_code)

    if not game or not current_round:
        raise ValueError("راند فعالی پیدا نشد.")

    if current_round["status"] != ROUND_SPEAKING:
        raise ValueError("راند در مرحله صحبت کردن نیست.")

    db.clear_round_votes(current_round["id"])
    db.update_round_status(current_round["id"], ROUND_VOTING)
    db.update_game_round_status(game_code, ROUND_VOTING)

    return {
        "round_id": current_round["id"],
        "voters": get_eligible_voters(game_code),
        "targets": get_eligible_vote_targets(game_code)
    }


def start_tie_voting_round(game_code, tied_user_ids):
    """
    رأی‌گیری مجدد فقط بین افراد دارای رأی مساوی انجام می‌شود.
    """
    current_round = db.get_current_round(game_code)
    if not current_round:
        raise ValueError("راند فعالی پیدا نشد.")

    # فقط بازیکنان زنده که در لیست رأی‌های مساوی هستند
    valid_targets = get_eligible_vote_targets(game_code, tied_user_ids)
    valid_ids = [player["user_id"] for player in valid_targets]

    if len(valid_ids) < 2:
        raise ValueError("برای رأی تساوی حداقل دو نامزد لازم است.")

    db.clear_round_votes(current_round["id"])

    next_level = int(current_round["tie_break_level"] or 0) + 1

    db.update_round_tie_state(
        round_id=current_round["id"],
        tie_break_level=next_level,
        target_user_ids=valid_ids,
        status=ROUND_TIE_VOTING
    )
    db.update_game_round_status(game_code, ROUND_TIE_VOTING)

    return {
        "round_id": current_round["id"],
        "tie_break_level": next_level,
        "targets": valid_targets,
        "voters": get_eligible_voters(game_code)
    }



def cast_vote(game_code, voter_id, target_id):
    """
    ثبت یا تغییر رأی با اعتبارسنجی کامل.
    """
    voter_id = normalize_user_id(voter_id)
    target_id = normalize_user_id(target_id)

    if not voter_id or not target_id:
        raise ValueError("شناسه رأی‌دهنده یا هدف نامعتبر است.")

    current_round = db.get_current_round(game_code)
    if not current_round:
        raise ValueError("راند فعالی وجود ندارد.")

    if current_round["status"] not in (ROUND_VOTING, ROUND_TIE_VOTING):
        raise ValueError("رأی‌گیری فعال نیست.")

    voters = get_eligible_voters(game_code)
    voter_ids = {player["user_id"] for player in voters}

    if voter_id not in voter_ids:
        raise ValueError("شما در این مرحله حق رأی دادن ندارید.")

    tie_targets = None
    if current_round["status"] == ROUND_TIE_VOTING:
        tie_targets = db.get_round_tie_targets(current_round["id"])

    targets = get_eligible_vote_targets(game_code, tie_targets)
    target_ids = {player["user_id"] for player in targets}

    if target_id not in target_ids:
        raise ValueError("این بازیکن هدف مجاز رأی‌گیری نیست.")

    db.save_vote(current_round["id"], voter_id, target_id)

    return {
        "round_id": current_round["id"],
        "voter_id": voter_id,
        "target_id": target_id
    }


def get_vote_result(round_id):
    """
    خروجی:
    {
        total_votes,
        max_votes,
        winner_ids,
        counts
    }
    """
    rows = db.count_votes(round_id)
    if not rows:
        return {
            "total_votes": 0,
            "max_votes": 0,
            "winner_ids": [],
            "counts": {}
        }

    counts = {
        row["target_id"]: row["vote_count"]
        for row in rows
    }

    max_votes = max(counts.values())
    winner_ids = [
        user_id for user_id, count in counts.items()
        if count == max_votes
    ]

    return {
        "total_votes": sum(counts.values()),
        "max_votes": max_votes,
        "winner_ids": winner_ids,
        "counts": counts
    }
def finish_voting(game_code):
    """
    پایان رأی‌گیری و شروع زنجیره حذف.
    اگر تساوی باشد، رأی تساوی شروع می‌شود.
    """
    current_round = db.get_current_round(game_code)
    if not current_round:
        raise ValueError("راند فعالی پیدا نشد.")

    if current_round["status"] not in (ROUND_VOTING, ROUND_TIE_VOTING):
        raise ValueError("مرحله رأی‌گیری فعال نیست.")

    vote_result = get_vote_result(current_round["id"])

    if vote_result["total_votes"] == 0:
        raise ValueError("هنوز رأی‌ای ثبت نشده است.")

    if len(vote_result["winner_ids"]) > 1:
        # شروع رأی‌گیری مجدد بین افراد مساوی
        return start_tie_voting_round(game_code, vote_result["winner_ids"])

    eliminated_user_id = vote_result["winner_ids"][0]
    return process_elimination_chain(game_code, eliminated_user_id)


def process_elimination_chain(game_code, eliminated_user_id):
    """
    زنجیره حذف:
    1. بومرنگ: اگر حذف‌شده بومرنگ باشد، رأی‌دهندگان به‌جای او حذف می‌شوند.
    2. دلقک: امتیاز جایزه در پایان دور اعمال می‌شود.
    3. روح: بعد از حذف، در رأی‌گیری‌ها شرکت می‌کند.
    4. بمب‌گذار: وضعیت بمب‌گذار pending می‌شود.
    5. جاسوس: فرصت حدس کلمه.
    6. مرغ عشق: اگر شریکش زنده باشد، شریک هم حذف می‌شود.
    7. دوئلیست: اگر هدفش حذف شود، امتیاز جایزه.
    8. در غیر این صورت فقط حذف عادی.

    بازگشت: لیست بازیکنانی که در این زنجیره حذف شدند.
    """
    current_round = db.get_current_round(game_code)
    if not current_round:
        raise ValueError("راند فعالی پیدا نشد.")

    eliminated_player = db.get_player(game_code, eliminated_user_id)
    if not eliminated_player:
        raise ValueError("بازیکن موردنظر یافت نشد.")

    eliminated_ids = []
    pending_boomerang_ids = []
    pending_clown_ids = []
    pending_duelist_target_ids = []
    pending_bomber_ids = []
    pending_spy_ids = []

    # ─────────────────────────────
    # 1. بومرنگ: رأی‌دهندگان حذف می‌شوند
    # ─────────────────────────────
    if eliminated_player["extra_role"] == EXTRA_BOOMERANG:
        extra_data = db.json_loads(eliminated_player["extra_role_data"], default={})
        if not extra_data.get("used", False):
            # یک‌بار استفاده می‌شود
            db.update_player_extra_role_data(game_code, eliminated_user_id, {"used": True})

            votes = db.get_votes_for_round(current_round["id"])
            voters_who_voted_for_eliminated = [
                vote["voter_id"] for vote in votes
                if vote["target_id"] == eliminated_user_id
            ]
            pending_boomerang_ids = voters_who_voted_for_eliminated

    # ─────────────────────────────
    # 2. دلقک: ثبت امتیاز جایزه (در پایان دور اعمال می‌شود)
    # ─────────────────────────────
    if eliminated_player["extra_role"] == EXTRA_CLOWN:
        pending_clown_ids.append(eliminated_user_id)

    # ─────────────────────────────
    # 3. روح: فقط در رأی‌گیری بعدی شرکت می‌کند، اینجا کاری نمی‌کنیم
    # ─────────────────────────────
    # روح بعد از حذف، همچنان در get_eligible_voters حضور دارد.

    # ─────────────────────────────
    # 4. مرغ عشق: اگر شریک زنده باشد، شریک هم حذف می‌شود
    # ─────────────────────────────
    if eliminated_player["extra_role"] == EXTRA_LOVEBIRD:
        extra_data = db.json_loads(eliminated_player["extra_role_data"], default={})
        partner_id = extra_data.get("partner_id")
        if partner_id:
            partner = db.get_player(game_code, partner_id)
            if partner and partner["is_alive"]:
                # شریک هم حذف می‌شود، بدون زنجیره اضافه برای خودش
                db.update_player_alive(game_code, partner_id, 0)
                eliminated_ids.append(partner_id)
                # پیام به شریک
                send_message(
                    partner_id,
                    "💔 مرغ عشق شما حذف شد. شما هم همراه او حذف می‌شوید."
                )
                # اگر شریک هم نقش اضافه داشته باشد (مثلاً بومرنگ)، اینجا باید در نظر گرفته شود.
                # برای سادگی، زنجیره شریک را با همان eliminated_user_id ادامه می‌دهیم؟ 
                # خیر، طبق قوانین زنجیره باید ادامه یابد. 
                # در این نسخه، برای جلوگیری از پیچیدگی، فقط حذف عادی شریک انجام می‌شود.
                # می‌توان بعداً توسعه داد.

    # ─────────────────────────────
    # 5. بمب‌گذار: وضعیت منتظر انفجار
    # ─────────────────────────────
    if eliminated_player["extra_role"] == EXTRA_BOMBER:
        pending_bomber_ids.append(eliminated_user_id)

    # ─────────────────────────────
    # 6. جاسوس: فرصت حدس کلمه
    # ─────────────────────────────
    if eliminated_player["role"] == ROLE_SPY:
        pending_spy_ids.append(eliminated_user_id)

    # ─────────────────────────────
    # 7. دوئلیست: اگر هدفش حذف شود، امتیاز جایزه در پایان دور
    # ─────────────────────────────
    # اگر خود دوئلیست حذف شده باشد، هدفش که حذف نشده، امتیازی نمی‌گیرد.
    # اگر بازیکنی که حذف شده هدف دوئلیست باشد، باید به دوئلیست امتیاز داد.
    # در اینجا چک می‌کنیم که آیا eliminated_user_id به عنوان هدف یک دوئلیست ثبت شده است.
    duelists = db.get_players_with_extra_role(game_code, EXTRA_DUELIST)
    for duelist in duelists:
        if not duelist["is_alive"]:
            continue
        extra_data = db.json_loads(duelist["extra_role_data"], default={})
        if extra_data.get("target_id") == eliminated_user_id:
            if not extra_data.get("bonus_given", False):
                # ثبت امتیاز موقت در round_score_delta
                db.update_round_score_delta(current_round["id"], duelist["user_id"], SCORE_DUELIST_BONUS)
                extra_data["bonus_given"] = True
                db.update_player_extra_role_data(game_code, duelist["user_id"], extra_data)
                send_message(
                    duelist["user_id"],
                    f"⚔️ هدف دوئل شما حذف شد! {SCORE_DUELIST_BONUS} امتیاز جایزه در پایان دور به شما اضافه می‌شود."
                )

    # ─────────────────────────────
    # حذف اصلی
    # ─────────────────────────────
    db.update_player_alive(game_code, eliminated_user_id, 0)
    eliminated_ids.append(eliminated_user_id)

    # حذف بومرنگی‌ها (بعد از حذف اصلی، چون ممکن است بومرنگ حذف‌شده باشد)
    for voter_id in pending_boomerang_ids:
        voter = db.get_player(game_code, voter_id)
        if voter and voter["is_alive"] and voter_id != eliminated_user_id:
            db.update_player_alive(game_code, voter_id, 0)
            eliminated_ids.append(voter_id)
            send_message(
                voter_id,
                "🪃 بومرنگ فعال شد! شما هم که به او رأی داده بودید حذف می‌شوید."
            )

    # حذف مرغ عشق شریک (اگر هنوز حذف نشده باشد)
    # در بالا انجام شد.

    # ─────────────────────────────
    # به‌روزرسانی وضعیت راند
    # ─────────────────────────────
    if pending_spy_ids:
        # جاسوس فرصت حدس دارد
        db.set_round_pending_spy(current_round["id"], pending_spy_ids[0])
        db.update_round_status(current_round["id"], ROUND_SPY_GUESS)
        db.update_game_round_status(game_code, ROUND_SPY_GUESS)

        spy = db.get_player(game_code, pending_spy_ids[0])
        send_message(
            pending_spy_ids[0],
            f"🕵️ شما حذف شدید، اما یک فرصت حدس دارید.\n"
            f"کلمه‌ای که فکر می‌کنید چیست؟ (ارسال متن)"
        )
    elif pending_bomber_ids:
        # بمب‌گذار فرصت انفجار دارد
        db.set_round_bomber_pending_user(current_round["id"], pending_bomber_ids[0])
        db.update_round_status(current_round["id"], ROUND_BOMBER_ACTION)
        db.update_game_round_status(game_code, ROUND_BOMBER_ACTION)

        bomber = db.get_player(game_code, pending_bomber_ids[0])
        send_message(
            bomber["user_id"],
            "💣 شما حذف شدید. یک بازیکن زنده را برای انفجار انتخاب کنید."
        )
        # باید کیبورد لیست بازیکنان زنده ارسال شود (در app.py انجام می‌شود)
    else:
        # بدون اقدام خاص، راند تمام می‌شود
        return finalize_round_after_elimination(game_code, eliminated_ids)

    return {
        "eliminated": eliminated_ids,
        "pending_spy": pending_spy_ids[0] if pending_spy_ids else None,
        "pending_bomber": pending_bomber_ids[0] if pending_bomber_ids else None,
        "action_required": bool(pending_spy_ids or pending_bomber_ids)
    }


def finalize_round_after_elimination(game_code, eliminated_ids):
    """
    بعد از انجام زنجیره حذف (بدون نیاز به اقدام جاسوس/بمب‌گذار)،
    بررسی شرایط پایان راند و اعمال امتیاز.
    """
    alive_players = db.get_alive_players(game_code)

    # ─────────────────────────────
    # شرایط پایان راند
    # ─────────────────────────────
    if len(alive_players) == 2:
        # ۱ شهروند + هر کس دیگر
        roles = {p["role"] for p in alive_players}
        if ROLE_CITIZEN in roles:
            # شهروند + هر کس دیگر = برنده
            db.set_game_winner(game_code, "citizen")
        else:
            # جاسوس + گمراه = برنده (هر دو غیرشهروند)
            db.set_game_winner(game_code, "spy")
        return end_round(game_code)

    if len(alive_players) == 1:
        winner = alive_players[0]
        db.set_game_winner(game_code, winner["role"])
        return end_round(game_code)

    if len(alive_players) == 0:
        # تیم آخرین حذف‌شده برنده است
        last_eliminated = db.get_player(game_code, eliminated_ids[-1])
        if last_eliminated:
            db.set_game_winner(game_code, last_eliminated["role"])
        else:
            db.set_game_winner(game_code, "none")
        return end_round(game_code)

    # ─────────────────────────────
    # اگر بازی ادامه دارد، راند را تمام کن و امتیاز بده
    # ─────────────────────────────
    return end_round(game_code)


def end_round(game_code):
    """
    پایان راند: محاسبه امتیاز تیمی، اعمال امتیازهای موقت، ذخیره و نمایش نتیجه.
    """
    current_round = db.get_current_round(game_code)
    game = db.get_game(game_code)

    if not current_round:
        return None

    db.update_round_status(current_round["id"], ROUND_FINISHED)
    db.update_game_round_status(game_code, ROUND_FINISHED)

    # اعمال امتیازهای موقت (مثل دوئلیست) فقط اگر راند به پایان رسیده باشد
    db.apply_round_score_deltas(current_round["id"], game_code)

    # امتیاز تیمی بر اساس برنده
    winner_team = game["winner_team"] if game else None

    if winner_team == ROLE_CITIZEN:
        db.add_score_to_team(game_code, ROLE_CITIZEN, SCORE_CITIZEN)
        db.add_score_to_team(game_code, ROLE_MISLED, SCORE_MISLED)  # گمراه در تیم شهروند است
        winner_text = "👤 تیم شهروندان"
    elif winner_team == ROLE_SPY:
        db.add_score_to_team(game_code, ROLE_SPY, SCORE_SPY)
        winner_text = "🕵️ تیم جاسوسان"
    elif winner_team == ROLE_MISLED:
        # اگر فقط گمراه باقی مانده باشد، تیم گمراه
        db.add_score_to_team(game_code, ROLE_MISLED, SCORE_MISLED)
        winner_text = "😵‍💫 تیم گمراه"
    else:
        winner_text = "🤝 مساوی"

    # دلقک‌ها: اگر در این راند حذف شده باشند، امتیاز جایزه
    clowns = db.get_players_with_extra_role(game_code, EXTRA_CLOWN)
    for clown in clowns:
        if not clown["is_alive"]:
            db.add_player_score(game_code, clown["user_id"], SCORE_CLOWN_BONUS)

    # پاک‌سازی وضعیت بمب‌گذار pending
    db.clear_round_bomber_pending_user(current_round["id"])

    # نمایش نتایج به همه
    players = db.get_players(game_code)
    scoreboard = sorted(players, key=lambda x: x["score"], reverse=True)

    result_lines = [
        f"🏁 <b>پایان راند {current_round['round_number']}</b>",
        f"برنده: {winner_text}",
        "",
        "📊 <b>امتیازات:</b>"
    ]

    for p in scoreboard:
        result_lines.append(f"{safe_name(p)}: {p['score']}")

    for p in players:
        send_message(p["user_id"], "\n".join(result_lines))

    send_message(
        game["admin_id"],
        "\n".join(result_lines) + "\n\nبرای شروع راند بعد از /start_round استفاده کنید."
    )

    return {
        "round_id": current_round["id"],
        "winner_team": winner_team,
        "scoreboard": scoreboard
    }


def handle_spy_guess(game_code, spy_user_id, guess_text):
    """
    بررسی حدس جاسوس. اگر درست باشد، تیم شهروند باخته و جاسوس برنده است.
    """
    current_round = db.get_current_round(game_code)
    if not current_round or current_round["status"] != ROUND_SPY_GUESS:
        raise ValueError("مرحله حدس جاسوس فعال نیست.")

    if current_round["pending_spy_user_id"] != spy_user_id:
        raise ValueError("این بازیکن نمی‌تواند حدس بزند.")

    spy = db.get_player(game_code, spy_user_id)
    if not spy:
        raise ValueError("جاسوس پیدا نشد.")

    correct_word = current_round["word1"]  # کلمه شهروند/گمراه
    guessed_correct = guess_text.strip().lower() == correct_word.strip().lower()

    # پاک‌سازی وضعیت
    db.clear_round_pending_spy(current_round["id"])

    if guessed_correct:
        # جاسوس برنده است
        db.set_game_winner(game_code, ROLE_SPY)
        result_text = f"🕵️ جاسوس ({safe_name(spy)}) کلمه را درست حدس زد! شهروندان باختند."
    else:
        result_text = f"🕵️ جاسوس ({safe_name(spy)}) حدس زد: {guess_text} ❌ اشتباه بود."
        # ادامه بازی: بررسی شرایط پایان
        return finalize_round_after_elimination(game_code, [spy_user_id])

    # ارسال نتیجه به همه
    game = db.get_game(game_code)
    players = db.get_players(game_code)
    for p in players:
        send_message(p["user_id"], result_text)

    # اگر جاسوس برنده شد، بازی تمام می‌شود
    return end_round(game_code)


def handle_bomber_action(game_code, bomber_user_id, target_user_id):
    """
    بمب‌گذار یک بازیکن زنده را منفجر می‌کند.
    """
    current_round = db.get_current_round(game_code)
    if not current_round or current_round["status"] != ROUND_BOMBER_ACTION:
        raise ValueError("مرحله بمب‌گذار فعال نیست.")

    if current_round["bomber_pending_user_id"] != bomber_user_id:
        raise ValueError("این بازیکن نمی‌تواند منفجر کند.")

    target = db.get_player(game_code, target_user_id)
    if not target or not target["is_alive"]:
        raise ValueError("هدف نامعتبر است.")

    # حذف هدف
    db.update_player_alive(game_code, target_user_id, 0)
    db.clear_round_bomber_pending_user(current_round["id"])

    send_message(
        target_user_id,
        f"💥 بمب‌گذار شما را منفجر کرد!"
    )

    return finalize_round_after_elimination(game_code, [bomber_user_id, target_user_id])


def start_next_round(game_code):
    """
    شروع راند بعد توسط مدیر. بازی باید در وضعیت finished باشد.
    """
    game = db.get_game(game_code)
    if not game:
        raise ValueError("بازی پیدا نشد.")

    if game["status"] != "playing":
        raise ValueError("بازی در وضعیت مناسب برای راند بعد نیست.")

    # اگر راند قبلی تمام نشده باشد، خطا بده
    current_round = db.get_current_round(game_code)
    if current_round and current_round["status"] != ROUND_FINISHED:
        raise ValueError("راند قبلی هنوز تمام نشده است.")

    return start_game_round(game_code)
   
