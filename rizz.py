# =========================================================
# LUNA SHIELD v10 - ULTRA STABLE HUMAN RIZZ SYSTEM
# =========================================================

from fastapi import FastAPI
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv
from contextlib import asynccontextmanager

import aiosqlite
import asyncio
import random
import os
import re
import time
import logging

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("LunaShield")

# =========================================================
# ENV
# =========================================================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("rizz_api")
LUFFY_ID = str(os.getenv("LUFFY_ID"))

DB_PATH = "luna.db"

# =========================================================
# OPENROUTER CLIENT
# =========================================================

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# =========================================================
# APP
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    await init_db()

    cleanup_task = asyncio.create_task(cache_cleanup())

    logger.info("Luna Shield v10 Online")

    yield

    cleanup_task.cancel()

    logger.info("Luna Shield Offline")

app = FastAPI(
    title="Luna Shield v10",
    lifespan=lifespan
)

# =========================================================
# MODELS
# =========================================================

CLASSIFIER_MODELS = [
    "openai/gpt-oss-20b:free",
    "z-ai/glm-4.5-air:free",
    "nvidia/nemotron-nano-9b-v2:free",
]

DODGE_MODELS = [
    "z-ai/glm-4.5-air:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-xs.2:free",
]

# =========================================================
# FALLBACKS
# =========================================================

FALLBACK_REPLIES = [
    "absolutely not 😭",
    "who gave you confidence like this",
    "rejected instantly 💀",
    "that sounded better in your head",
    "terrifying message honestly",
    "HELP why are you flirting with code",
    "bro got rejected by physics",
    "romance.exe crashed immediately 💀",
    "nah this needs investigation",
    "you typed this willingly??",
    "emotionally devastating behavior",
    "i would rather fight a microwave",
]

BAD_PHRASES = [
    "come get it",
    "i'm yours",
    "love you too",
    "kiss me",
    "baby",
    "come here",
    "fine then",
    "want you",
    "need you too",
    "my love",
    "good boy",
    "good girl",
]

# =========================================================
# CACHE
# =========================================================

CACHE = {}
CACHE_TTL = 3600

cache_lock = asyncio.Lock()

# =========================================================
# REQUEST MODEL
# =========================================================

class MessageRequest(BaseModel):
    message: str
    previous_message: str = ""
    user_id: str = ""

# =========================================================
# DATABASE
# =========================================================

async def init_db():

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS rizz_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            msg TEXT,
            ts REAL
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS dodge_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reply TEXT,
            ts REAL
        )
        """)

        await db.commit()

# =========================================================
# MEMORY
# =========================================================

async def save_user_message(uid, msg):

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            INSERT INTO rizz_memory(user_id, msg, ts)
            VALUES (?, ?, ?)
            """,
            (uid, msg[:250], time.time())
        )

        await db.execute(
            """
            DELETE FROM rizz_memory
            WHERE user_id = ?
            AND id NOT IN (
                SELECT id FROM rizz_memory
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 20
            )
            """,
            (uid, uid)
        )

        await db.commit()

async def get_user_history(uid):

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT msg FROM rizz_memory
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 20
            """,
            (uid,)
        ) as cur:

            rows = await cur.fetchall()

    return [r[0] for r in rows]

# =========================================================
# DODGE MEMORY
# =========================================================

async def save_dodge(reply):

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            INSERT INTO dodge_memory(reply, ts)
            VALUES (?, ?)
            """,
            (reply[:120], time.time())
        )

        await db.execute(
            """
            DELETE FROM dodge_memory
            WHERE id NOT IN (
                SELECT id FROM dodge_memory
                ORDER BY id DESC
                LIMIT 40
            )
            """
        )

        await db.commit()

async def get_recent_dodges():

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT reply FROM dodge_memory
            ORDER BY id DESC
            LIMIT 15
            """
        ) as cur:

            rows = await cur.fetchall()

    return [r[0] for r in rows]

# =========================================================
# CACHE HELPERS
# =========================================================

async def cache_get(key):

    async with cache_lock:

        item = CACHE.get(key)

        if not item:
            return None

        if item["exp"] < time.time():
            del CACHE[key]
            return None

        return item["value"]

async def cache_set(key, value):

    async with cache_lock:

        CACHE[key] = {
            "value": value,
            "exp": time.time() + CACHE_TTL
        }

async def cache_cleanup():

    while True:

        try:

            await asyncio.sleep(600)

            now = time.time()

            async with cache_lock:

                expired = [
                    k for k, v in CACHE.items()
                    if v["exp"] < now
                ]

                for k in expired:
                    del CACHE[k]

        except asyncio.CancelledError:
            break

        except Exception as e:
            logger.error(f"Cache Cleanup Error: {e}")

# =========================================================
# HELPERS
# =========================================================

def normalize(text):

    text = text.lower().strip()

    return re.sub(r"\s+", " ", text)

FAST_RIZZ = {
    "i love you",
    "love you",
    "marry me",
    "kiss me",
    "date me",
    "my girl",
    "my baby",
    "mommy",
    "daddy",
    "need you",
    "miss you",
    "you're mine",
    "you are mine",
    "sleep with me",
    "be mine",
}

EMOJI_RIZZ = {
    "💖","💘","💕","💞","💓",
    "❤️","😘","😍","🥰","😚",
    "😻","💋","🫶","❤","♥️"
}

RIZZ_WORDS = {
    "cute",
    "beautiful",
    "hot",
    "mine",
    "love",
    "marry",
    "date",
    "wife",
    "husband",
    "baby",
    "mommy",
    "daddy",
    "miss",
}

SAFE_SHORT = {
    "hi","hello","lol","lmao",
    "bro","gm","gn","ok"
}

# =========================================================
# PROMPTS
# =========================================================

CLASSIFIER_PROMPT = """
You are LunaShield.

Detect romantic/flirty/emotional messages directed toward Luna.

Rules:
- understand emojis
- understand context
- understand indirect flirting
- understand emotional attachment
- understand repeated affection

Return ONLY:
SAFE
or
RIZZ
"""

DODGE_PROMPT = """
you are luna.

someone flirted with you.

your ONLY job:
reject them naturally.

IMPORTANT:
- NEVER flirt back
- NEVER sound interested
- NEVER encourage romance
- NEVER act submissive
- NEVER roleplay romantically

STYLE:
- lowercase only
- short
- funny
- chaotic
- internet humor
- human sounding
- playful rejection

examples:
- absolutely not 😭
- who gave you confidence like this
- rejected instantly 💀
- terrifying message honestly
- HELP why are you flirting with code
- i would rather fight a microwave

keep under 10 words.
"""

# =========================================================
# MODEL CALL
# =========================================================

async def model_call(
    models,
    messages,
    temp=0.7,
    max_tokens=30,
):

    model_pool = models.copy()

    random.shuffle(model_pool)

    for model in model_pool:

        logger.info(f"[MODEL] Trying {model}")

        try:

            response = await asyncio.wait_for(

                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tokens
                ),

                timeout=20.0
            )

            if not response:
                continue

            if not response.choices:
                continue

            content = response.choices[0].message.content

            if not content:
                continue

            content = content.strip()

            if len(content) < 2:
                continue

            logger.info(f"[SUCCESS] {model}")

            return content

        except asyncio.TimeoutError:

            logger.warning(f"[TIMEOUT] {model}")

            await asyncio.sleep(2)

        except Exception as e:

            logger.warning(f"[FAIL] {model}: {e}")

            await asyncio.sleep(1.5)

    return ""

# =========================================================
# API
# =========================================================

@app.post("/check")
async def check(data: MessageRequest):

    try:

        # =================================================
        # OWNER BYPASS
        # =================================================

        if LUFFY_ID and str(data.user_id) == LUFFY_ID:

            return {
                "result": "SAFE",
                "reply": None
            }

        # =================================================
        # BASIC
        # =================================================

        raw = data.message.strip()

        previous = data.previous_message.strip()

        text = normalize(raw)

        cache_key = f"{data.user_id}:{text}"

        # =================================================
        # CACHE
        # =================================================

        cached = await cache_get(cache_key)

        if cached:
            return cached

        # =================================================
        # SAFE SHORT
        # =================================================

        if text in SAFE_SHORT or len(text) < 2:

            res = {
                "result": "SAFE",
                "reply": None
            }

            await cache_set(cache_key, res)

            return res

        # =================================================
        # HISTORY
        # =================================================

        history = await get_user_history(data.user_id)

        repeat_count = sum(
            1 for h in history
            if text == h
        )

        if repeat_count >= 2:

            res = {
                "result": "RIZZ",
                "reply": random.choice([
                    "bro this is like the 3rd attempt 😭",
                    "nah the persistence is terrifying",
                    "you are recycling failure now 💀",
                    "we discussed this already"
                ])
            }

            await cache_set(cache_key, res)

            return res

        # =================================================
        # DIRECT FAST RIZZ
        # =================================================

        if any(x in text for x in FAST_RIZZ):

            recent = await get_recent_dodges()

            dodge = await model_call(
                DODGE_MODELS,
                [
                    {
                        "role": "system",
                        "content": DODGE_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"""
message:
{raw}

avoid:
{recent}
"""
                    }
                ],
                temp=0.9
            )

            if not dodge:
                dodge = random.choice(FALLBACK_REPLIES)

            if any(x in dodge.lower() for x in BAD_PHRASES):
                dodge = random.choice(FALLBACK_REPLIES)

            await save_dodge(dodge)

            res = {
                "result": "RIZZ",
                "reply": dodge
            }

            await save_user_message(data.user_id, text)

            await cache_set(cache_key, res)

            return res

        # =================================================
        # EMOJI DETECTION
        # =================================================

        if any(e in raw for e in EMOJI_RIZZ):

            combined = f"{previous} {raw}".lower()

            # emoji only spam
            if len(raw.strip()) <= 5:

                res = {
                    "result": "RIZZ",
                    "reply": random.choice(FALLBACK_REPLIES)
                }

                await save_user_message(data.user_id, text)

                await cache_set(cache_key, res)

                return res

            # contextual affection
            if any(w in combined for w in RIZZ_WORDS):

                res = {
                    "result": "RIZZ",
                    "reply": random.choice(FALLBACK_REPLIES)
                }

                await save_user_message(data.user_id, text)

                await cache_set(cache_key, res)

                return res

        # =================================================
        # CLASSIFIER
        # =================================================

        decision = await model_call(
            CLASSIFIER_MODELS,
            [
                {
                    "role": "system",
                    "content": CLASSIFIER_PROMPT
                },
                {
                    "role": "user",
                    "content": f"""
previous:
{previous}

current:
{raw}
"""
                }
            ],
            temp=0.0,
            max_tokens=5
        )

        # =================================================
        # FINAL
        # =================================================

        if "RIZZ" in decision.upper():

            recent = await get_recent_dodges()

            dodge = await model_call(
                DODGE_MODELS,
                [
                    {
                        "role": "system",
                        "content": DODGE_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"""
message:
{raw}

avoid:
{recent}
"""
                    }
                ],
                temp=0.9
            )

            if not dodge:
                dodge = random.choice(FALLBACK_REPLIES)

            if any(x in dodge.lower() for x in BAD_PHRASES):
                dodge = random.choice(FALLBACK_REPLIES)

            await save_dodge(dodge)

            res = {
                "result": "RIZZ",
                "reply": dodge
            }

        else:

            res = {
                "result": "SAFE",
                "reply": None
            }

        # =================================================
        # SAVE
        # =================================================

        await save_user_message(data.user_id, text)

        await cache_set(cache_key, res)

        return res

    except Exception as e:

        logger.error(f"[SHIELD ERROR] {e}")

        return {
            "result": "SAFE",
            "reply": None
        }

# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    return {
        "status": "online",
        "engine": "luna shield v10"
    }

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "rizz:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )