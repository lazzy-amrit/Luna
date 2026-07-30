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
LUFFY_ID = str(os.getenv("LUFFY_ID"))

DB_PATH = "luna.db"

# =========================================================
# OPENROUTER
# =========================================================

client_ai = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# =========================================================
# MODELS
# =========================================================

MODELS = [
    "openai/gpt-oss-120b:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-m.1:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
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

# 30 minute window
JEALOUSY_WINDOW = 1800

# How many recent Luffy interactions become suspicious
JEALOUSY_FLAG = 8

# Maximum jealousy
MAX_JEALOUSY = 12

# 24 hours
IGNORE_TIME = 86400

# How often Luna can complain
JEALOUSY_COOLDOWN = 120

# How often jealousy naturally decreases
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
                fact TEXT,
                ts REAL,
                UNIQUE(user_id, fact)
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

    await load_jealousy_state()


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

    # Make sure special users have a DB row
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
    (r"\bmy name is ([a-z0-9_ ]{2,20})", "name is {0}"),
    (r"\bi'?m ([0-9]{1,2})(?:yrs|years|y/o|yo)?\b", "age {0}"),
    (r"\bi live in ([a-z ]{2,25})", "lives in {0}"),
    (r"\bi'?m from ([a-z ]{2,25})", "from {0}"),
    (r"\bmy birthday is ([a-z0-9 ,]{3,25})", "birthday {0}"),
    (r"\bi like ([a-z0-9 ]{2,30})", "likes {0}"),
    (r"\bi love ([a-z0-9 ]{2,30})", "loves {0}"),
    (r"\bi hate ([a-z0-9 ]{2,30})", "hates {0}"),
    (r"\bi play ([a-z0-9 ]{2,25})", "plays {0}"),
    (r"\bmy (?:fav|favorite) (?:is )?([a-z0-9 ]{2,25})", "favorite {0}"),
    (r"\bi work as (?:a |an )?([a-z ]{2,25})", "works as {0}"),
    (r"\bi study ([a-z ]{2,25})", "studies {0}"),
]


def extract_facts(text):
    low = text.lower()
    found = []

    for pattern, template in FACT_PATTERNS:
        match = re.search(pattern, low)

        if match:
            value = match.group(1).strip().rstrip(".!?,")

            if 2 <= len(value) <= 30:
                found.append(template.format(value))

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

        for fact in facts:
            try:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO facts(user_id, fact, ts)
                    VALUES (?, ?, ?)
                    """,
                    (
                        uid,
                        fact,
                        time.time()
                    )
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
    recent = await get_recent_messages(uid, limit=10)

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

    for model in MODELS:

        try:

            response = await client_ai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=1.05,
                max_tokens=70,
                presence_penalty=0.6,
                frequency_penalty=0.7,
            )

            output = response.choices[0].message.content

            if output:
                return output.strip()

        except Exception as e:
            print(f"model fail {model}: {e}")
            continue

    return "my brain stopped working 💀"


# =========================================================
# CHECK IF MESSAGE IS DIRECTED AT LUFFY
# =========================================================

async def is_talking_to_luffy(message):

    # Direct mention of Luffy
    if any(
        str(user.id) == LUFFY_ID
        for user in message.mentions
    ):
        return True

    # Direct reply to Luffy
    if message.reference:

        resolved = message.reference.resolved

        if resolved is not None:
            if str(resolved.author.id) == LUFFY_ID:
                return True

        # If Discord did not cache the referenced message,
        # try fetching it.
        if resolved is None and message.reference.message_id:

            try:
                referenced_message = await message.channel.fetch_message(
                    message.reference.message_id
                )

                if str(referenced_message.author.id) == LUFFY_ID:
                    return True

            except Exception:
                pass

    return False


# =========================================================
# JEALOUSY CHECK
# =========================================================

async def jealousy_check(message):

    uid = str(message.author.id)

    # Only monitor our special person
    if uid not in special_users:
        return

    data = special_users[uid]
    now = time.time()

    # If Luna is already ignoring them,
    # don't continue building jealousy.
    if now < data["ignored_until"]:
        return

    # ONLY count interaction with Luffy
    talking_to_luffy = await is_talking_to_luffy(message)

    if not talking_to_luffy:
        return

    # Remove old interactions
    data["recent_luffy"] = [
        timestamp
        for timestamp in data["recent_luffy"]
        if now - timestamp < JEALOUSY_WINDOW
    ]

    # Lifetime counter
    data["luffy_count"] += 1

    # Recent counter
    data["recent_luffy"].append(now)

    recent = len(data["recent_luffy"])

    # =====================================================
    # JEALOUSY GROWTH
    # =====================================================

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

    # =====================================================
    # 24 HOUR IGNORE
    # =====================================================

    if now < data["ignored_until"]:

        # Silent ignore
        return True

    # =====================================================
    # ONLY REACT WHEN THEY TALK TO LUNA
    # =====================================================

    is_luna_mentioned = client.user in message.mentions

    is_reply_to_luna = (
        message.reference
        and message.reference.resolved
        and message.reference.resolved.author == client.user
    )

    # If not talking to Luna, don't react
    if not (is_luna_mentioned or is_reply_to_luna):
        return False

    # =====================================================
    # CURRENT RECENT ACTIVITY
    # =====================================================

    data["recent_luffy"] = [
        timestamp
        for timestamp in data["recent_luffy"]
        if now - timestamp < JEALOUSY_WINDOW
    ]

    recent = len(data["recent_luffy"])
    level = data["jealousy_level"]

    # =====================================================
    # NOTHING TO BE JEALOUS ABOUT
    # =====================================================

    if recent < JEALOUSY_FLAG and level < 7:
        return False

    # =====================================================
    # NUCLEAR MODE
    # =====================================================

    if level >= MAX_JEALOUSY:

        # 35% chance to go nuclear
        if random.random() < 0.35:

            data["ignored_until"] = now + IGNORE_TIME

            # Reset active jealousy
            data["jealousy_level"] = 0
            data["recent_luffy"].clear()
            data["last_trigger"] = now

            await save_jealousy_state(uid)

            await message.reply(
                random.choice(NUCLEAR_LINES)
            )

            return True

    # =====================================================
    # NORMAL JEALOUSY
    # =====================================================

    if now - data["last_trigger"] < JEALOUSY_COOLDOWN:
        return False

    # More Luffy activity = higher chance
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

            # Remove old recent activity
            data["recent_luffy"] = [
                timestamp
                for timestamp in data["recent_luffy"]
                if now - timestamp < JEALOUSY_WINDOW
            ]

            # Slowly cool down
            if data["jealousy_level"] > 0:
                data["jealousy_level"] -= 1

            # Save persistent state
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

    # Also handle nickname-style mention
    clean = clean.replace(
        f"<@!{client.user.id}>",
        ""
    ).strip()

    if not clean:
        clean = "yo"

    # =====================================================
    # CREATOR
    # =====================================================

    if "who made you" in clean.lower():

        reply = random.choice([
            "amrit made me 🤍",
            "amrit built me fr",
            "created by amrit 😭"
        ])

        await message.reply(reply)
        return

    # =====================================================
    # LOCAL CREEP SHIELD
    # =====================================================

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

    # =====================================================
    # AI RESPONSE
    # =====================================================

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

    # Ignore bots
    if message.author.bot:
        return

    # Track activity
    last_activity = time.time()
    last_active_channel_id = message.channel.id

    uid = str(message.author.id)

    # =====================================================
    # JEALOUSY OBSERVER
    #
    # This happens BEFORE checking whether Luna was mentioned.
    #
    # Therefore:
    #
    # special user -> Luffy = counted
    # special user -> random person = ignored
    # special user -> Luna = not counted
    # =====================================================

    await jealousy_check(message)

    # =====================================================
    # IS THIS MESSAGE FOR LUNA?
    # =====================================================

    is_luna_mentioned = client.user in message.mentions

    is_reply_to_luna = (
        message.reference
        and message.reference.resolved
        and message.reference.resolved.author == client.user
    )

    if not (is_luna_mentioned or is_reply_to_luna):
        return

    # =====================================================
    # JEALOUSY REACTION
    #
    # If Luna is mad, she may react instead of answering
    # normally.
    # =====================================================

    ignored = await jealousy_reaction(message)

    if ignored:
        return

    # =====================================================
    # NORMAL COOLDOWN
    # =====================================================

    now = time.time()

    if (
        uid in cooldown
        and now - cooldown[uid] < COOLDOWN
    ):
        return

    cooldown[uid] = now

    # =====================================================
    # HANDLE AI IN BACKGROUND
    # =====================================================

    asyncio.create_task(
        handle_message(message)
    )


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