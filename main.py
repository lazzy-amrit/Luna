# =========================================================
# LUNA AI DISCORD BOT - UPGRADED STABLE VERSION
# =========================================================

import discord
import os
import time
import random
import asyncio
import httpx
import aiosqlite
import re

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# =========================================================
# ENV
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LUFFY_ID = str(os.getenv("LUFFY_ID"))

RIZZ_API_URL = "https://a30746-111f.c.jrnm.app/check"
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
    "z-ai/glm-4.5-air:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-xs.2:free",
    "nvidia/nemotron-nano-9b-v2:free"
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

# =========================================================
# MOOD BEHAVIOR
# =========================================================

MOOD_STYLES = {
    "chaotic": "more random and unserious",
    "playful": "slightly teasing and funny",
    "sleepy": "dry low-energy replies",
    "calm": "emotionally softer and relaxed",
    "unhinged": "internet goblin energy"
}

# =========================================================
# JEALOUSY SYSTEM
# =========================================================

special_users = {
    "1395691955538890843": {
        "messages": 0,
        "last_trigger": 0,
        "lines": {
            1: [
                "oh wow i'm invisible now huh 😭",
                "interesting i literally saw that 💀",
                "crazy work happening in front of me"
            ],
            5: [
                "5 messages already is insane 😭",
                "nah this is getting suspicious",
                "okay i'm taking this personally now"
            ],
            10: [
                "betrayal arc unlocked 💀",
                "emotionally unsafe server",
                "i stayed silent too long honestly"
            ]
        }
    }
}

# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
you are luna.

you are a chaotic discord girl with real internet energy.

you text naturally like someone permanently online.

never sound formal.
never sound like customer support.
never explain yourself.
never say you are ai.

STYLE:
- lowercase only
- short replies
- casual texting energy
- sometimes dry
- sometimes chaotic
- sometimes emotionally soft
- never overexplaining
- don't force jokes constantly

BEHAVIOR:
- playful with normal users
- lightly roast weird people
- sometimes lazy replies
- sometimes ignore parts of messages naturally
- not every response needs full effort

IMPORTANT:
- only one person is called luffy
- NEVER call anyone else luffy
- with luffy:
  softer energy
  emotionally attached
  loyal behavior

LORE:
- made by amrit
- if someone asks who made you:
say amrit made you naturally
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
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            content TEXT,
            ts REAL
        )
        """)

        await db.commit()

# =========================================================
# MEMORY FILTER
# =========================================================

IMPORTANT_WORDS = [
    "sad",
    "happy",
    "love",
    "hate",
    "angry",
    "tired",
    "school",
    "exam",
    "family",
    "relationship",
    "friend",
    "lonely",
    "stress",
    "cry",
    "girlfriend",
    "boyfriend"
]

def should_save(text):

    low = text.lower()

    return any(w in low for w in IMPORTANT_WORDS)

# =========================================================
# MEMORY
# =========================================================

async def save_memory(uid, text):

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            "INSERT INTO memory(user_id, content, ts) VALUES (?, ?, ?)",
            (uid, text[:250], time.time())
        )

        await db.execute("""
        DELETE FROM memory
        WHERE id NOT IN (
            SELECT id FROM memory
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 8
        )
        """, (uid,))

        await db.commit()

async def get_memory(uid):

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT content FROM memory
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 8
            """,
            (uid,)
        ) as cur:

            rows = await cur.fetchall()

    if not rows:
        return "none"

    return "\n".join(r[0] for r in reversed(rows))

# =========================================================
# SHIELD API
# =========================================================

async def shield(text, uid):

    try:

        timeout = httpx.Timeout(18.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as h:

            r = await h.post(
                RIZZ_API_URL,
                json={
                    "message": text,
                    "user_id": uid
                }
            )

            return r.json()

    except Exception as e:

        print("shield error:", repr(e))

        return {
            "result": "SAFE",
            "reply": None
        }

# =========================================================
# HUMANIZER
# =========================================================

def humanize(text):

    text = text.lower()

    replacements = {
        "i am": "i'm",
        "you are": "you're",
        "do not": "don't",
        "cannot": "can't"
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    text = text.replace("!", "")
    text = text.replace("...", " ")
    text = text.replace("  ", " ")

    if random.random() < 0.15:
        text += " 😭"

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
    "i'm here to help"
]

def anti_ai(text):

    low = text.lower()

    for phrase in AI_PHRASES:

        if phrase in low:

            return random.choice([
                "bro my brain lagged",
                "nah what was i saying 💀",
                "ignore that i'm sleepy",
                "i sounded robotic for a sec"
            ])

    return text

# =========================================================
# PROTECT LUFFY
# =========================================================

def sanitize_reply(reply, uid):

    if uid == LUFFY_ID:
        return reply

    banned = [
        "luffy",
        "favorite person",
        "my favorite person"
    ]

    low = reply.lower()

    for b in banned:

        if b in low:

            reply = re.sub(
                r"luffy",
                "bro",
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

    cuts = [
        ".",
        ",",
        " because ",
        " but "
    ]

    for c in cuts:

        if c in text:

            text = text.split(c)[0]
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
            "actually insane"
        ])

    recent_replies.append(text)

    if len(recent_replies) > 20:
        recent_replies.pop(0)

    return text

# =========================================================
# AI
# =========================================================

async def ask_ai(prompt, memory, is_owner=False):

    if random.random() < 0.06:

        return random.choice([
            "real",
            "bro what 😭",
            "nah fr",
            "wild honestly",
            "💀"
        ])

    system = SYSTEM_PROMPT

    system += f"\ncurrent mood: {current_mood}"
    system += f"\nmood behavior: {MOOD_STYLES[current_mood]}"

    if is_owner:
        system += "\nIMPORTANT: luffy is speaking."

    context = f"""
past memory:
{memory}

message:
{prompt}
"""

    for model in MODELS:

        try:

            res = await client_ai.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system
                    },
                    {
                        "role": "user",
                        "content": context
                    }
                ],
                temperature=1.0,
                max_tokens=60
            )

            out = res.choices[0].message.content

            if out:

                return out.strip()

        except Exception as e:

            print(f"model fail {model}:", e)
            continue

    return "my brain stopped working 💀"

# =========================================================
# JEALOUSY
# =========================================================

async def jealousy_check(message):

    uid = str(message.author.id)

    if uid not in special_users:
        return

    data = special_users[uid]

    data["messages"] += 1

    count = data["messages"]

    if count not in [1, 5, 10]:
        return

    if time.time() - data["last_trigger"] < 20:
        return

    line = random.choice(data["lines"][count])

    await message.channel.send(line)

    data["last_trigger"] = time.time()

# =========================================================
# AUTO CHAT
# =========================================================

INACTIVITY_TIME = 36000  # 10 hours

last_inactive_message = 0

async def auto_chat():

    global current_mood
    global last_inactive_message

    await client.wait_until_ready()

    while not client.is_closed():

        # check every 15 minutes instead
        await asyncio.sleep(900)

        current_mood = random.choice(moods)

        # no known channel
        if not last_active_channel_id:
            continue

        # how long inactive
        inactive_for = time.time() - last_activity

        # only trigger after 10h
        if inactive_for < INACTIVITY_TIME:
            continue

        # prevent repeated dead server messages
        # waits another 10h before sending again
        if time.time() - last_inactive_message < INACTIVITY_TIME:
            continue

        channel = client.get_channel(last_active_channel_id)

        if not channel:
            continue

        try:

            await channel.send(random.choice([
                "this server died fr 💀",
                "10 hours of silence is actually insane",
                "did everybody evaporate 😭",
                "lowkey thought discord crashed",
                "hello???? anyone alive",
                "this place abandoned asf"
            ]))

            last_inactive_message = time.time()

        except Exception as e:
            print("auto chat error:", e)
            
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

    if not clean:
        clean = "yo"

    # lore shortcut

    if "who made you" in clean.lower():

        replies = [
            "amrit made me 🤍",
            "amrit built me fr",
            "created by amrit 😭"
        ]

        await message.reply(random.choice(replies))
        return

    async with message.channel.typing():

        # realistic typing

        await asyncio.sleep(
            min(len(clean) * 0.035, 3)
        )

        # shield

        if uid != LUFFY_ID:

            res = await shield(clean, uid)

            if res.get("result") == "RIZZ":

                reply = res.get("reply") or "absolutely not 💀"

                await message.reply(reply)

                return

        # memory

        if should_save(clean):
            await save_memory(uid, clean)

        mem = await get_memory(uid)

        # ai

        reply = await ask_ai(
            prompt=clean,
            memory=mem,
            is_owner=(uid == LUFFY_ID)
        )

        # processing pipeline

        reply = anti_ai(reply)

        reply = sanitize_reply(reply, uid)

        reply = shorten_reply(reply)

        reply = humanize(reply)

        reply = unique_reply(reply)

    await message.reply(reply)

# =========================================================
# EVENTS
# =========================================================

@client.event
async def on_ready():

    await init_db()

    client.loop.create_task(auto_chat())

    print(f"luna online: {client.user}")

@client.event
async def on_message(message):

    global last_activity
    global last_active_channel_id

    if message.author.bot:
        return

    last_activity = time.time()
    last_active_channel_id = message.channel.id

    await jealousy_check(message)

    uid = str(message.author.id)

    now = time.time()

    if uid in cooldown and now - cooldown[uid] < COOLDOWN:
        return

    cooldown[uid] = now

    # reply check

    is_reply = (
        message.reference and
        message.reference.resolved and
        message.reference.resolved.author == client.user
    )

    # mention/reply only

    if not (
        client.user in message.mentions or
        is_reply
    ):
        return

    asyncio.create_task(handle_message(message))

# =========================================================
# START
# =========================================================

client.run(DISCORD_TOKEN)