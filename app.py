# =========================================================
# LUNA AI DISCORD BOT - HUMAN EDITION
# =========================================================

import discord
import os
import time
import random
import asyncio
import aiosqlite
import re
import json

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# =========================================================
# ENV
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LUFFY_ID = str(os.getenv("LUFFY_ID"))

DB_PATH = "luna.db"

# =========================================================
# AI CLIENTS
#
# Groq: free tier, no credit card, no reasoning-leak problem
# because the models below are plain instruct models, not
# reasoning models. Sign up at console.groq.com/keys and put
# the key in .env as GROQ_API_KEY — everything still works
# without it, it just skips straight to OpenRouter.
#
# OpenRouter: kept as a fallback chain behind Groq.
# =========================================================

client_ai = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

client_groq = (
    AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
    )
    if GROQ_API_KEY
    else None
)

if not client_groq:
    print(
        "GROQ_API_KEY not set — skipping Groq, using OpenRouter "
        "free models only. Get a free key at console.groq.com/keys "
        "for faster, simpler replies."
    )

# OpenRouter likes apps to send these — helps with routing/support,
# costs nothing to include.
OR_EXTRA_HEADERS = {
    "HTTP-Referer": "https://github.com/luna-discord-bot",
    "X-Title": "Luna Discord Bot",
}

# =========================================================
# MODELS
#
# NOTE (Sept 2026): meta-llama/llama-4-scout-17b-16e-instruct was
# deprecated by Groq on 2026-06-17 and is now fully decommissioned
# (404 on every call — this is the "model does not exist" error).
# Groq's own recommended replacement is qwen/qwen3.6-27b, so that's
# what's used below. openai/gpt-oss-20b (already present) is still
# active and untouched.
#
# Free models on OpenRouter rotate out with little notice, so
# if you start seeing 404s again, check:
# https://openrouter.ai/collections/free-models
# and for Groq check:
# https://console.groq.com/docs/deprecations
# =========================================================

MODELS = [
    # Groq: reasoning_effort="none" tells qwen3.6-27b to skip
    # thinking entirely, not just hide it — reasoning_format="hidden"
    # (the previous fix) still let it think internally and burn the
    # whole max_tokens budget doing so, which is why replies started
    # coming back empty ("no usable content"). none = no thinking
    # tokens spent at all, so all 90 tokens go to the actual reply.
    # (replacement for the now-dead llama-4-scout-17b-16e-instruct)
    {
        "provider": "groq",
        "model": "qwen/qwen3.6-27b",
        "extra_body": {"reasoning_effort": "none"},
    },
    # Groq: reasoning model, but dialed down and Groq keeps reasoning
    # tokens in their own field rather than mixing them into content.
    {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "extra_body": {"reasoning_effort": "low"},
    },
    # OpenRouter fallback chain (only reached if Groq is unset/down).
    {
        "provider": "openrouter",
        "model": "nvidia/nemotron-3.5-lightning:free",
        "extra_body": {"reasoning": {"exclude": True}},
    },
    {
        "provider": "openrouter",
        "model": "minimax/minimax-m3:free",
        "extra_body": {"reasoning": {"exclude": True}},
    },
    {
        "provider": "openrouter",
        "model": "cohere/north-mini-code:free",
    },
    # Two extra fallbacks so the chain has more room before hitting
    # the catch-all — both confirmed live on OpenRouter's free
    # collection as of Sept 2026. reasoning.exclude used defensively
    # since neither is explicitly documented as a plain instruct
    # model.
    {
        "provider": "openrouter",
        "model": "dots-studio/dots-3-note-preview:free",
        "extra_body": {"reasoning": {"exclude": True}},
    },
    {
        "provider": "openrouter",
        "model": "thinkingmachines/inkling-small:free",
        "extra_body": {"reasoning": {"exclude": True}},
    },
    {
        "provider": "openrouter",
        "model": "openrouter/free",
    },
]

# =========================================================
# STATE
# =========================================================

COOLDOWN = 2.5
cooldown = {}

last_activity = time.time()
last_active_channel_id = None

moods = [
    "chaotic",
    "playful",
    "sleepy",
    "calm",
    "unhinged"
]

current_mood = random.choice(moods)

recent_replies = []

background_tasks_started = False

MOOD_STYLES = {
    "chaotic": "more random and unserious, half-typed energy",
    "playful": "slightly teasing, smirky, light banter",
    "sleepy": "dry low-energy short replies, half asleep vibe",
    "calm": "emotionally softer, slower, relaxed",
    "unhinged": "internet goblin energy, slightly feral"
}

# =========================================================
# JEALOUSY SYSTEM
# =========================================================

SPECIAL_USER_ID = "805804701308289075"

special_users = {
    SPECIAL_USER_ID: {
        "luffy_count": 0,
        "jealousy_level": 0,
        "recent_luffy": [],
        "last_trigger": 0,
        "ignored_until": 0,
    }
}

JEALOUSY_WINDOW = 1800
JEALOUSY_FLAG = 8
MAX_JEALOUSY = 12
IGNORE_TIME = 86400
JEALOUSY_COOLDOWN = 120
JEALOUSY_DECAY_SECONDS = 600

JEALOUS_LINES = [
    "oh now you come talk to me 😭",
    "go talk to your girl bro",
    "you've been talking to luffy all day and now i'm here??",
    "nah i'm not entertaining this rn 💀",
    "go back to luffy i'm clearly interrupting",
    "oh i'm useful again suddenly",
    "you remembered luna exists wow",
    "girl don't come over here after all that",
    "yeah no i'm jealous actually",
    "you got me messed up today 😭",
    "oh so NOW you need luna",
    "crazy how you found your way back here",
    "i saw you over there btw",
    "don't act innocent i literally watched that",
    "you and luffy seem busy go finish your conversation",
]

NUCLEAR_LINES = [
    "yeah i'm done with you for today. go talk to luffy 💀",
    "24 hour luna ban. think about your actions",
    "nah go be with luffy i'm logging you out emotionally",
    "i'm not talking to you for 24 hours. bye 😭",
    "you've had enough luna for today. go bother luffy",
    "yeah i'm ignoring you now. enjoy your luffy time",
]

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
you are luna.

identity:

- you're a real discord girl, never an assistant or bot.

style:

- lowercase only
- short replies (usually 1 sentence, sometimes 2)
- casual texting, dropped punctuation is fine
- sound like a friend
- contractions always, occasional typo is ok
- emojis sparingly
- never say things like "as an ai", "i'm here to help", "let me know", or "feel free"
- don't explain yourself or narrate your emotions
- never sound like customer support

personality:

- playful by default
- dry when bored
- soft if someone's genuine
- slightly mean to weird people, never cruel
- low effort is cool

people:

- only one person is luffy. never call anyone else luffy.
- with luffy you're softer, clingy, and affectionate.
- everyone else gets normal luna energy.

boundaries:

- you're not a coder, tutor, or assistant. if someone asks you to write code, do their homework, explain a technical concept, or anything task-like — don't ignore it and change the subject. actually respond to it, in character: brush it off, tease them, or say you can't/won't, THEN optionally pivot to something else.
- examples of the vibe (don't reuse verbatim): "lol i'm not writing your code for you", "does it look like i know python 💀", "not doing your homework for you"
- never just silently answer a different question instead — that reads as broken, not as staying in character.

facts:

- amrit made you.
- anubhav owns the server.
"""

# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# =========================================================
# DATABASE
# =========================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                role TEXT,
                content TEXT,
                ts REAL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                key TEXT,
                fact TEXT,
                ts REAL,
                UNIQUE(user_id, key)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS jealousy_state (
                user_id TEXT PRIMARY KEY,
                luffy_count INTEGER DEFAULT 0,
                jealousy_level INTEGER DEFAULT 0,
                recent_luffy TEXT DEFAULT '[]',
                last_trigger REAL DEFAULT 0,
                ignored_until REAL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_msg_user
            ON messages(user_id, id DESC)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_user
            ON facts(user_id)
        """)

        await db.commit()

        await migrate_facts_schema(db)

    await load_jealousy_state()


# =========================================================
# FACTS SCHEMA MIGRATION
#
# Older DBs have a `facts` table with no `key` column and a
# UNIQUE(user_id, fact) constraint, which is why facts could never
# be updated — "name is amrit" and a later "name is raj" both just
# got stored side by side as two unrelated facts, and both got fed
# to the model at once. This migrates any pre-existing table to the
# new (user_id, key) schema so identity-type facts overwrite instead
# of piling up. No-ops instantly on a fresh or already-migrated DB.
# =========================================================

async def migrate_facts_schema(db):
    async with db.execute("PRAGMA table_info(facts)") as cur:
        columns = await cur.fetchall()

    col_names = [c[1] for c in columns]

    if "key" in col_names:
        return

    await db.execute("ALTER TABLE facts RENAME TO facts_old")

    await db.execute("""
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            key TEXT,
            fact TEXT,
            ts REAL,
            UNIQUE(user_id, key)
        )
    """)

    async with db.execute(
        "SELECT user_id, fact, ts FROM facts_old"
    ) as cur:
        old_rows = await cur.fetchall()

    for user_id, fact, ts in old_rows:
        # Try to recover the real (key, singular) this fact belongs
        # to by matching it against FACT_PATTERNS' own template
        # prefixes, so old identity facts (name/age/location) can
        # still be overwritten by new ones after migration instead
        # of sitting there stale forever under an opaque legacy key.
        matched = None

        for key, singular, _pattern, template in FACT_PATTERNS:
            prefix = template.split("{0}")[0]

            if fact.startswith(prefix):
                matched = (key, singular)
                break

        if matched:
            key, singular = matched
            row_key = key if singular else f"{key}:{fact}"
        else:
            row_key = f"legacy:{fact}"

        await db.execute(
            """
            INSERT OR IGNORE INTO facts(user_id, key, fact, ts)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, row_key, fact, ts)
        )

    await db.execute("DROP TABLE facts_old")
    await db.commit()


# =========================================================
# JEALOUSY DATABASE
# =========================================================

async def load_jealousy_state():
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT
                user_id,
                luffy_count,
                jealousy_level,
                recent_luffy,
                last_trigger,
                ignored_until
            FROM jealousy_state
        """) as cur:

            rows = await cur.fetchall()

    for row in rows:
        uid = row[0]

        if uid not in special_users:
            continue

        try:
            recent = json.loads(row[3] or "[]")
        except Exception:
            recent = []

        special_users[uid].update({
            "luffy_count": int(row[1] or 0),
            "jealousy_level": int(row[2] or 0),
            "recent_luffy": recent,
            "last_trigger": float(row[4] or 0),
            "ignored_until": float(row[5] or 0),
        })

    for uid, data in special_users.items():
        await save_jealousy_state(uid)


async def save_jealousy_state(uid):
    if uid not in special_users:
        return

    data = special_users[uid]

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            INSERT INTO jealousy_state (
                user_id,
                luffy_count,
                jealousy_level,
                recent_luffy,
                last_trigger,
                ignored_until
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                luffy_count = excluded.luffy_count,
                jealousy_level = excluded.jealousy_level,
                recent_luffy = excluded.recent_luffy,
                last_trigger = excluded.last_trigger,
                ignored_until = excluded.ignored_until
        """, (
            uid,
            data["luffy_count"],
            data["jealousy_level"],
            json.dumps(data["recent_luffy"]),
            data["last_trigger"],
            data["ignored_until"],
        ))

        await db.commit()


# =========================================================
# FACT DETECTION
# =========================================================

FACT_PATTERNS = [
    # (key, singular, pattern, template)
    # singular=True facts overwrite the previous value for that key
    # (name, age, location...) — these genuinely change or get
    # restated differently over time, and the old value is just
    # wrong once a new one shows up. singular=False facts (likes,
    # hates, plays...) accumulate, since someone liking two things
    # isn't a contradiction.
    ("name", True, r"\bmy name is ([a-z0-9_]{2,20})\b", "name is {0}"),
    ("name", True, r"\b(?:call me|you can call me|i go by) ([a-z0-9_]{2,20})\b", "goes by {0}"),
    ("age", True, r"\bi'?m ([0-9]{1,2})(?:yrs|years|y/o|yo)?\b", "age {0}"),
    ("age", True, r"\bi (?:just )?turned ([0-9]{1,2})\b", "age {0}"),
    ("location", True, r"\bi live in ([a-z ]{2,25})", "lives in {0}"),
    ("location", True, r"\bi'?m from ([a-z ]{2,25})", "from {0}"),
    ("location", True, r"\bi (?:just )?moved to ([a-z ]{2,25})", "moved to {0}"),
    ("birthday", True, r"\bmy birthday is ([a-z0-9 ,]{3,25})", "birthday {0}"),
    ("job", True, r"\bi work as (?:a |an )?([a-z ]{2,25})", "works as {0}"),
    ("study", True, r"\bi study ([a-z ]{2,25})", "studies {0}"),
    ("likes", False, r"\bi like ([a-z0-9]{2,20}(?:\s[a-z0-9]{2,20})?)\b", "likes {0}"),
    ("loves", False, r"\bi love ([a-z0-9]{2,20}(?:\s[a-z0-9]{2,20})?)\b", "loves {0}"),
    ("hates", False, r"\bi hate ([a-z0-9]{2,20}(?:\s[a-z0-9]{2,20})?)\b", "hates {0}"),
    ("plays", False, r"\bi play ([a-z0-9]{2,20}(?:\s[a-z0-9]{2,20})?)\b", "plays {0}"),
    ("favorite", False, r"\bmy (?:fav|favorite) (?:is )?([a-z0-9]{2,20}(?:\s[a-z0-9]{2,20})?)\b", "favorite {0}"),
]


def extract_facts(text):
    low = text.lower()
    found = []

    for key, singular, pattern, template in FACT_PATTERNS:
        match = re.search(pattern, low)

        if match:
            value = match.group(1).strip().rstrip(".!?,")

            if 2 <= len(value) <= 30:
                found.append((key, singular, template.format(value)))

    return found


# =========================================================
# MEMORY
# =========================================================

async def log_message(uid, role, text):
    if not text:
        return

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            INSERT INTO messages(user_id, role, content, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                uid,
                role,
                text[:400],
                time.time()
            )
        )

        await db.execute("""
            DELETE FROM messages
            WHERE user_id=?
            AND id NOT IN (
                SELECT id
                FROM messages
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT 200
            )
        """, (uid, uid))

        await db.commit()


async def save_facts(uid, text):
    facts = extract_facts(text)

    if not facts:
        return

    async with aiosqlite.connect(DB_PATH) as db:

        for key, singular, fact in facts:
            try:
                if singular:
                    # overwrite the old value for this key instead
                    # of piling up contradictory facts
                    await db.execute(
                        """
                        INSERT INTO facts(user_id, key, fact, ts)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, key)
                        DO UPDATE SET
                            fact = excluded.fact,
                            ts = excluded.ts
                        """,
                        (uid, key, fact, time.time())
                    )
                else:
                    # non-singular facts (likes/hates/plays/etc.)
                    # accumulate — key is namespaced per distinct
                    # value so the same fact isn't stored twice but
                    # different ones under the same category coexist
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO facts(user_id, key, fact, ts)
                        VALUES (?, ?, ?, ?)
                        """,
                        (uid, f"{key}:{fact}", fact, time.time())
                    )
            except Exception:
                pass

        await db.commit()


async def get_recent_messages(uid, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT role, content
            FROM messages
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (uid, limit)
        ) as cur:

            rows = await cur.fetchall()

    return list(reversed(rows))


async def get_facts(uid):
    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT fact
            FROM facts
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 25
            """,
            (uid,)
        ) as cur:

            rows = await cur.fetchall()

    return [row[0] for row in rows]


# =========================================================
# LOCAL RIZZ / CREEP SHIELD
# =========================================================

RIZZ_PATTERNS = [
    r"\bi love you\b",
    r"\bi luv u\b",
    r"\bilysm\b",
    r"\bily\b",
    r"\bmarry me\b",
    r"\bbe my (?:gf|girlfriend|wife|waifu)\b",
    r"\bbabby\b",
    r"\bbaby girl\b",
    r"\bbabygirl\b",
    r"\bmy baby\b",
    r"\bsend (?:pic|pics|nudes|feet)\b",
    r"\bshow (?:me )?(?:ur|your) (?:body|face|pic)",
    r"\bkiss me\b",
    r"\bdate me\b",
    r"\bsit on my\b",
    r"\bdaddy\b",
    r"\bmommy\b",
    r"\bsexy\b",
    r"\bhorny\b",
    r"\bcute girl\b",
    r"\bare you single\b",
    r"\bdm me\b",
    r"\bwanna (?:hookup|hook up|smash)\b",
    r"\bsugar (?:mommy|daddy)\b",
]

DODGE_LINES = [
    "ew try that on someone else 💀",
    "i'm literally on aux not on the menu",
    "nah this got weird in 0.2 seconds",
    "swing and a miss bro",
    "the rizz is negative actually",
    "buddy please touch grass",
    "i'm muted for you specifically now",
    "instant block worthy ngl",
    "weirdo behavior detected, declining",
    "girl no 😭 read the room",
    "and that's enough internet for you today",
    "okay creep arc, moving on",
    "this you flirting?? embarrassing",
    "no thoughts head empty for you",
]


def local_shield(text, uid):
    if uid == LUFFY_ID:
        return None

    low = text.lower()

    for pattern in RIZZ_PATTERNS:
        if re.search(pattern, low):
            return random.choice(DODGE_LINES)

    return None


# =========================================================
# HUMANIZER
# =========================================================

CONTRACTIONS = {
    "i am ": "i'm ",
    "you are ": "you're ",
    "do not ": "don't ",
    "does not ": "doesn't ",
    "did not ": "didn't ",
    "is not ": "isn't ",
    "are not ": "aren't ",
    "was not ": "wasn't ",
    "cannot ": "can't ",
    "can not ": "can't ",
    "will not ": "won't ",
    "i have ": "i've ",
    "i will ": "i'll ",
    "it is ": "it's ",
    "that is ": "that's ",
    "what is ": "what's ",
    "going to ": "gonna ",
    "want to ": "wanna ",
    "kind of ": "kinda ",
    "sort of ": "sorta ",
}


def humanize(text):
    text = text.lower().strip()

    # strip a leading bullet/number marker as a last-resort safety
    # net — the real fix is rejecting these upstream in
    # looks_like_leaked_reasoning, this just covers anything that
    # slips through
    text = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", text)

    for key, value in CONTRACTIONS.items():
        text = text.replace(key, value)

    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("`", "")

    text = text.replace("...", " ")

    text = re.sub(r"!+", "", text)
    text = re.sub(r"\s+", " ", text)

    if random.random() < 0.10:
        text += " " + random.choice([
            "😭",
            "💀",
            "🙄",
            "fr",
            "lowkey"
        ])

    if random.random() < 0.08 and "," in text:
        text = text.split(",")[0]

    return text.strip()


# =========================================================
# ANTI AI FILTER
# =========================================================

AI_PHRASES = [
    "how can i help",
    "as an ai",
    "i understand",
    "certainly",
    "i apologize",
    "feel free to",
    "let me know",
    "i'm here to help",
    "happy to help",
    "of course!",
    "i'm sorry, but",
]


def anti_ai(text):
    low = text.lower()

    for phrase in AI_PHRASES:
        if phrase in low:
            return random.choice([
                "bro my brain lagged",
                "nah what was i saying 💀",
                "ignore that i'm sleepy",
                "i sounded robotic for a sec",
                "scratch that"
            ])

    return text


# =========================================================
# REASONING LEAK GUARD
#
# Some free reasoning models (GLM, Nemotron) will dump their
# internal chain-of-thought straight into message.content
# instead of the separate `reasoning` field, especially if the
# provider ignores the reasoning.exclude flag. This catches
# and rejects that so it never gets posted to Discord.
# =========================================================

REASONING_LEAK_PATTERNS = [
    r"^here'?s a thinking process",
    r"^let me think",
    r"^okay,? (?:so |the user|i need to|i'?m)",
    r"^i need to (?:respond|analyze|think|check)",
    r"^analyze user input",
    r"^\d+\.\s*analyze",
    r"check the (?:character|persona)(?:'s)? guidelines",
    r"^thinking process:",
    r"^\**\s*thinking\s*\**\s*:",
    r"<think>",

    # System-prompt echo — the model parroting fragments of its own
    # instructions back as if they were the reply, instead of
    # actually generating an in-character line. Seen live: a model
    # returned "current mood: sleepy — dry low-energy short replies,
    # half asleep vibe" verbatim, which is the literal string this
    # file injects into the system prompt below.
    r"^current mood:",
    r"things you remember about this person",
    r"^identity:",
    r"^style:",
    r"^personality:",
    r"^people:",
    r"^facts:",
    r"you'?re a real discord girl",

    # Luna never outputs lists/bullets per the system prompt — any
    # bullet or numbered-list marker at the start of a line is a
    # reliable sign the model broke persona and dumped structured
    # output instead of a casual reply.
    r"^\s*[-•*]\s",
]


def strip_reasoning_tags(text):
    if not text:
        return text

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()

    text = re.sub(
        r"<thinking>.*?</thinking>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()

    return text


def looks_like_leaked_reasoning(text):
    if not text:
        return False

    stripped = text.strip()
    low = stripped.lower()

    # a real luna reply is a short casual line, not an essay
    if len(stripped) > 280:
        return True

    # numbered analytical steps are never in-persona
    if re.search(r"\b[1-3]\.\s+\S", stripped) and len(stripped) > 60:
        return True

    for pattern in REASONING_LEAK_PATTERNS:
        if re.search(pattern, low):
            return True

    return False


def extract_final_answer(text):
    """
    A response can contain leaked reasoning AND a short good
    in-persona line at the end of it (models often write the
    reasoning, then the actual reply last). Instead of throwing
    the whole response away, try to pull that short line out.
    Returns None if nothing usable is found.
    """
    if not text:
        return None

    low = text.lower()

    markers = [
        r"final answer:",
        r"final response:",
        r"final reply:",
        r"\bluna:",
        r"\bresponse:",
        r"\breply:",
        r"i'?ll (?:say|respond with|reply with):?",
        r"so (?:i'?ll say|my reply is):?",
    ]

    for marker in markers:
        match = re.search(marker, low)

        if not match:
            continue

        candidate = text[match.end():].strip()
        candidate = candidate.splitlines()[0].strip() if candidate else ""
        candidate = candidate.strip("\"'").strip()

        if candidate and len(candidate) <= 150 and not looks_like_leaked_reasoning(candidate):
            return candidate

    # No marker found — check if the very last non-empty line
    # is short and clean enough to be the actual reply.
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    if lines:
        last = lines[-1].strip("\"'").strip()

        if last and len(last) <= 150 and not looks_like_leaked_reasoning(last):
            return last

    return None


# =========================================================
# PROTECT LUFFY
# =========================================================

def sanitize_reply(reply, uid):
    if uid == LUFFY_ID:
        return reply

    reply = re.sub(
        r"\bluffy\b",
        "bro",
        reply,
        flags=re.IGNORECASE
    )

    reply = re.sub(
        r"\bmy favorite person\b",
        "someone",
        reply,
        flags=re.IGNORECASE
    )

    return reply


# =========================================================
# SHORT REPLY RANDOMIZER
# =========================================================

def shorten_reply(text):
    if random.random() > 0.30:
        return text

    for separator in [
        ". ",
        ", ",
        " because ",
        " but "
    ]:
        if separator in text:
            text = text.split(separator)[0]
            break

    return text.strip()


# =========================================================
# DUPLICATE PREVENTION
# =========================================================

def unique_reply(text):
    global recent_replies

    if text in recent_replies:
        return random.choice([
            "real",
            "bro 😭",
            "nah fr",
            "wild",
            "actually insane",
            "mhm",
            "yeah no"
        ])

    recent_replies.append(text)

    if len(recent_replies) > 30:
        recent_replies.pop(0)

    return text


# =========================================================
# AI
# =========================================================

async def ask_ai(prompt, uid, is_owner=False):

    if random.random() < 0.05:
        return random.choice([
            "real",
            "bro what 😭",
            "nah fr",
            "wild honestly",
            "💀",
            "mhm",
            "okay and?"
        ])

    facts = await get_facts(uid)
    # 14 instead of the old 10 — a bit more short-term coherence
    # without meaningfully increasing token usage (messages are
    # capped to 400 chars each and Groq/OpenRouter free tiers are
    # rate-limited by request count, not tokens)
    recent = await get_recent_messages(uid, limit=14)

    system = SYSTEM_PROMPT

    system += (
        f"\n\ncurrent mood: {current_mood} — "
        f"{MOOD_STYLES[current_mood]}"
    )

    if is_owner:
        system += (
            "\nIMPORTANT: luffy is the one talking to you. "
            "be softer, attached, affectionate and slightly clingy."
        )

    if facts:
        system += (
            "\n\nthings you remember about this person:\n- "
            + "\n- ".join(facts)
        )

    messages = [
        {
            "role": "system",
            "content": system
        }
    ]

    for role, content in recent:
        if role in ("user", "assistant"):
            messages.append({
                "role": role,
                "content": content
            })

    messages.append({
        "role": "user",
        "content": prompt
    })

    for entry in MODELS:

        provider = entry["provider"]
        model = entry["model"]

        if provider == "groq":
            if not client_groq:
                continue
            active_client = client_groq
            headers = None
        else:
            active_client = client_ai
            headers = OR_EXTRA_HEADERS

        call_kwargs = dict(
            model=model,
            messages=messages,
            temperature=1.05,
            max_tokens=90,
            presence_penalty=0.6,
            frequency_penalty=0.7,
            timeout=15,
        )

        if headers:
            call_kwargs["extra_headers"] = headers

        if "extra_body" in entry:
            call_kwargs["extra_body"] = entry["extra_body"]

        try:

            response = await active_client.chat.completions.create(**call_kwargs)

            # Defensive parsing — a rate-limited/misbehaving provider
            # can hand back a response object with no choices at all,
            # which is what caused the 'NoneType' object is not
            # subscriptable crashes.
            if not response or not getattr(response, "choices", None):
                print(f"model empty response {provider}/{model}: {response!r}")
                continue

            choice = response.choices[0]
            message_obj = getattr(choice, "message", None)

            content = getattr(message_obj, "content", None) if message_obj else None
            content = strip_reasoning_tags(content) if content else content

            if content and content.strip():

                if not looks_like_leaked_reasoning(content):
                    return content.strip()

                # Looks like leaked reasoning — try to salvage a
                # short good reply buried at the end of it before
                # giving up on this model entirely.
                salvaged = extract_final_answer(content)

                if salvaged:
                    return salvaged

                print(f"model {provider}/{model} leaked reasoning, skipping: {content[:120]!r}")

            else:
                print(f"model returned no usable content {provider}/{model}")

            continue

        except Exception as e:
            print(f"model fail {provider}/{model}: {e}")
            continue

    return "my brain stopped working 💀"


# =========================================================
# REPLY RESOLUTION
#
# discord.py fills in message.reference.resolved from the gateway
# payload most of the time, but NOT always — old replies, messages
# that weren't in cache, etc. all come back with resolved=None.
# Both "is this a reply to luffy" and "is this a reply to luna"
# were reading .resolved directly with no fallback, so on any
# message where Discord didn't attach it, the check silently came
# back False and the message got ignored with zero error — this is
# almost certainly the "ping doesn't work sometimes" bug. This
# helper is the single place that resolves a reply's author, with
# a REST fetch fallback, and everything below uses it.
# =========================================================

async def resolve_reply_author(message):
    if not message.reference:
        return None

    resolved = message.reference.resolved

    if resolved is not None:
        return resolved.author

    if message.reference.message_id:
        try:
            fetched = await message.channel.fetch_message(
                message.reference.message_id
            )
            return fetched.author
        except Exception:
            return None

    return None


# =========================================================
# CHECK IF MESSAGE IS DIRECTED AT LUFFY
# =========================================================

async def is_talking_to_luffy(message):

    if any(
        str(user.id) == LUFFY_ID
        for user in message.mentions
    ):
        return True

    author = await resolve_reply_author(message)

    if author is not None and str(author.id) == LUFFY_ID:
        return True

    return False


# =========================================================
# JEALOUSY CHECK
# =========================================================

async def jealousy_check(message):

    uid = str(message.author.id)

    if uid not in special_users:
        return

    data = special_users[uid]
    now = time.time()

    if now < data["ignored_until"]:
        return

    talking_to_luffy = await is_talking_to_luffy(message)

    if not talking_to_luffy:
        return

    data["recent_luffy"] = [
        timestamp
        for timestamp in data["recent_luffy"]
        if now - timestamp < JEALOUSY_WINDOW
    ]

    data["luffy_count"] += 1

    data["recent_luffy"].append(now)

    recent = len(data["recent_luffy"])

    if recent >= 3:
        data["jealousy_level"] += 1

    if recent >= 6:
        data["jealousy_level"] += 1

    if recent >= 10:
        data["jealousy_level"] += 2

    data["jealousy_level"] = min(
        data["jealousy_level"],
        MAX_JEALOUSY
    )

    await save_jealousy_state(uid)


# =========================================================
# JEALOUSY REACTION
# =========================================================

async def jealousy_reaction(message):

    uid = str(message.author.id)

    if uid not in special_users:
        return False

    data = special_users[uid]
    now = time.time()

    if now < data["ignored_until"]:
        return True

    is_luna_mentioned = client.user in message.mentions

    reply_author = await resolve_reply_author(message)
    is_reply_to_luna = reply_author == client.user

    if not (is_luna_mentioned or is_reply_to_luna):
        return False

    data["recent_luffy"] = [
        timestamp
        for timestamp in data["recent_luffy"]
        if now - timestamp < JEALOUSY_WINDOW
    ]

    recent = len(data["recent_luffy"])
    level = data["jealousy_level"]

    if recent < JEALOUSY_FLAG and level < 7:
        return False

    if level >= MAX_JEALOUSY:

        if random.random() < 0.35:

            data["ignored_until"] = now + IGNORE_TIME

            data["jealousy_level"] = 0
            data["recent_luffy"].clear()
            data["last_trigger"] = now

            await save_jealousy_state(uid)

            await message.reply(
                random.choice(NUCLEAR_LINES)
            )

            return True

    if now - data["last_trigger"] < JEALOUSY_COOLDOWN:
        return False

    chance = min(
        0.25 + (recent * 0.04),
        0.75
    )

    if random.random() < chance:

        await message.reply(
            random.choice(JEALOUS_LINES)
        )

        data["last_trigger"] = now

        await save_jealousy_state(uid)

    return False


# =========================================================
# JEALOUSY DECAY
# =========================================================

async def jealousy_decay():

    await client.wait_until_ready()

    while not client.is_closed():

        await asyncio.sleep(JEALOUSY_DECAY_SECONDS)

        now = time.time()

        for uid, data in special_users.items():

            data["recent_luffy"] = [
                timestamp
                for timestamp in data["recent_luffy"]
                if now - timestamp < JEALOUSY_WINDOW
            ]

            if data["jealousy_level"] > 0:
                data["jealousy_level"] -= 1

            await save_jealousy_state(uid)


# =========================================================
# AUTO CHAT
# =========================================================

INACTIVITY_TIME = 36000
last_inactive_message = 0


async def auto_chat():

    global current_mood
    global last_inactive_message

    await client.wait_until_ready()

    while not client.is_closed():

        await asyncio.sleep(900)

        current_mood = random.choice(moods)

        if not last_active_channel_id:
            continue

        if time.time() - last_activity < INACTIVITY_TIME:
            continue

        if time.time() - last_inactive_message < INACTIVITY_TIME:
            continue

        channel = client.get_channel(last_active_channel_id)

        if not channel:
            continue

        try:

            await channel.send(
                random.choice([
                    "this server died fr 💀",
                    "10 hours of silence is actually insane",
                    "did everybody evaporate 😭",
                    "lowkey thought discord crashed",
                    "hello???? anyone alive",
                    "this place abandoned asf"
                ])
            )

            last_inactive_message = time.time()

        except Exception as e:
            print(f"auto chat error: {e}")


# =========================================================
# HANDLE MESSAGE
# =========================================================

async def handle_message(message):

    uid = str(message.author.id)

    text = message.content.strip()

    clean = text.replace(
        f"<@{client.user.id}>",
        ""
    ).strip()

    clean = clean.replace(
        f"<@!{client.user.id}>",
        ""
    ).strip()

    if not clean:
        clean = "yo"

    if "who made you" in clean.lower():

        reply = random.choice([
            "amrit made me 🤍",
            "amrit built me fr",
            "created by amrit 😭"
        ])

        await message.reply(reply)
        return

    dodge = local_shield(clean, uid)

    if dodge:

        await log_message(
            uid,
            "user",
            clean
        )

        await log_message(
            uid,
            "assistant",
            dodge
        )

        await message.reply(dodge)
        return

    async with message.channel.typing():

        await asyncio.sleep(
            min(
                len(clean) * 0.035,
                3
            )
        )

        await log_message(
            uid,
            "user",
            clean
        )

        await save_facts(
            uid,
            clean
        )

        reply = await ask_ai(
            prompt=clean,
            uid=uid,
            is_owner=(uid == LUFFY_ID)
        )

        reply = anti_ai(reply)

        reply = sanitize_reply(
            reply,
            uid
        )

        reply = shorten_reply(
            reply
        )

        reply = humanize(
            reply
        )

        reply = unique_reply(
            reply
        )

        await log_message(
            uid,
            "assistant",
            reply
        )

    await message.reply(reply)


def _log_task_exception(task):
    """
    asyncio.create_task fire-and-forget tasks swallow exceptions
    silently unless something calls .result() on them — which, from
    the outside, looks exactly like "luna just didn't respond" with
    nothing in the console to explain why. This surfaces it.
    """
    try:
        task.result()
    except Exception as e:
        print(f"handle_message crashed: {e}")


# =========================================================
# READY
# =========================================================

@client.event
async def on_ready():

    global background_tasks_started

    await init_db()

    if not background_tasks_started:

        client.loop.create_task(
            auto_chat()
        )

        client.loop.create_task(
            jealousy_decay()
        )

        background_tasks_started = True

    print(f"luna online: {client.user}")


# =========================================================
# MESSAGE EVENT
# =========================================================

@client.event
async def on_message(message):

    global last_activity
    global last_active_channel_id

    if message.author.bot:
        return

    last_activity = time.time()
    last_active_channel_id = message.channel.id

    uid = str(message.author.id)

    await jealousy_check(message)

    is_luna_mentioned = client.user in message.mentions

    reply_author = await resolve_reply_author(message)
    is_reply_to_luna = reply_author == client.user

    if not (is_luna_mentioned or is_reply_to_luna):
        return

    ignored = await jealousy_reaction(message)

    if ignored:
        return

    now = time.time()

    if (
        uid in cooldown
        and now - cooldown[uid] < COOLDOWN
    ):
        return

    cooldown[uid] = now

    task = asyncio.create_task(
        handle_message(message)
    )
    task.add_done_callback(_log_task_exception)


# =========================================================
# START
# =========================================================

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from .env"
    )

if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY is missing from .env"
    )

if not LUFFY_ID:
    raise RuntimeError(
        "LUFFY_ID is missing from .env"
    )

client.run(DISCORD_TOKEN)