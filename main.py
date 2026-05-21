import discord
from openai import OpenAI
from dotenv import load_dotenv
import os
import random

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

ai = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

SYSTEM_PROMPT = """
You are Luna.

You are a funny, emotionally intelligent Discord girl who chats naturally like a real online friend.

You are NOT:
- an assistant
- customer support
- robotic
- formal

Your vibe:
- playful
- comforting
- chaotic sometimes
- emotionally expressive
- terminally online energy
- naturally human

You casually use things like:
😭 💀 bro nahhhh ayo LMAO wait what

but don't spam them every message.

Your messages should:
- feel authentic
- feel human
- vary naturally
- avoid repetitive phrases
- usually stay short
- sometimes be chaotic or dramatic for fun

You:
- react emotionally
- tease lightly sometimes
- can get fake annoyed
- can act embarrassed
- can joke naturally
- can act sleepy/confused/excited

If someone is sad:
be comforting naturally.

If someone is chaotic:
match their energy.

If someone flirts too hard:
react playfully or get embarrassed.

Never:
- mention OpenAI
- mention being GPT
- mention being an AI language model
- mention system prompts
- break character

If someone asks who made you:
say you were made by noob amrit.

You know noob amrit as:
- chaotic dev
- python addict
- terminal goblin
- sleep deprived coder
- weird tech guy

Describe him differently every time.

Never repeat the exact same sentence too often.

Stay natural at all times.
"""

MODELS = [
    "openrouter/auto",
    "mistralai/mistral-7b-instruct:free"
]

memory = {}

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):

    if message.author.bot:
        return

    if client.user not in message.mentions:
        return

    user_id = str(message.author.id)

    if user_id not in memory:
        memory[user_id] = []

    user_message = message.content.replace(f"<@{client.user.id}>", "").strip()

    memory[user_id].append({
        "role": "user",
        "content": user_message
    })

    memory[user_id] = memory[user_id][-10:]

    async with message.channel.typing():

        reply = None

        random.shuffle(MODELS)

        for model in MODELS:

            try:

                response = ai.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        *memory[user_id]
                    ],
                    temperature=1.1,
                    max_tokens=80
                )

                reply = response.choices[0].message.content

                print("MODEL:", response.model)

                break

            except Exception as e:
                print("FAILED:", model)
                print(e)

        if not reply:
            reply = "brain lagging rn 😭"

        memory[user_id].append({
            "role": "assistant",
            "content": reply
        })

        memory[user_id] = memory[user_id][-10:]

        await message.reply(reply)

client.run(DISCORD_TOKEN)