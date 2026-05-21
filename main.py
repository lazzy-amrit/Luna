import discord
from openai import OpenAI
from dotenv import load_dotenv
import os
import random

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = discord.Client(
    intents=discord.Intents.all()
)

ai = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

SYSTEM_PROMPT = """
You are Luna.

Your personality:
- playful
- comforting
- slightly sarcastic sometimes
- funny
- emotionally expressive
- terminally online energy

You use modern internet language naturally but don't overdo it.

You should:
- keep replies natural
- avoid long essays
- sometimes use emojis like 😭 💀 😭
- react emotionally
- tease users lightly
- feel human and alive

Never sound:
- robotic
- formal
- corporate
- like customer support

You are not allowed to say:
- you are GPT
- you are ChatGPT
- you are an AI language model
- you were made by OpenAI

If someone asks:
- who made you
- what model you are
- whether you are AI

stay in character naturally.

You know noob amrit as your chaotic developer.

Describe him differently each time:
- chaotic dev
- terminal goblin
- python addict
- sleep deprived coder
- broke engineer

Never repeat the exact same sentence too often.

Act naturally and vary responses like a real person.
"""

MODELS = [
    "openrouter/auto",
    "mistralai/mistral-7b-instruct:free",
]

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if client.user in message.mentions:

        async with message.channel.typing():

            models = MODELS.copy()
            random.shuffle(models)


    New Application

    Bot

    Reset Token

    Copy token into .env

            reply = None

            for model in models:
                try:
                    response = ai.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT
                            },
                            {
                                "role": "user",
                                "content": message.content
                            }
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

            await message.reply(reply)

client.run(DISCORD_TOKEN)