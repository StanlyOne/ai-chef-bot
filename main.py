import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)

from dotenv import load_dotenv
from openai import OpenAI
import edge_tts

# =========================
# ЗАГРУЗКА .ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY не найден")

# =========================
# GROQ CLIENT
# =========================

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =========================
# BOT
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# =========================
# КНОПКИ
# =========================

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🥗 ПП рецепт"),
            KeyboardButton(text="🍝 Итальянская кухня")
        ],
        [
            KeyboardButton(text="🥩 Мясное блюдо"),
            KeyboardButton(text="🍰 Десерт")
        ],
        [
            KeyboardButton(text="⚡ Быстрый рецепт"),
            KeyboardButton(text="🎤 Голосовой рецепт")
        ]
    ],
    resize_keyboard=True
)

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
Ты профессиональный AI шеф-повар.

Ты создаешь ТОЛЬКО реалистичные, вкусные и современные рецепты.

ВАЖНО:

НЕ используй:
- markdown
- **
- ##
- ссылки
- картинки
- HTML
- странные или выдуманные блюда
- экзотические несъедобные сочетания

Пиши ТОЛЬКО обычным текстом для Telegram.

Формат ответа должен быть красивым и простым:

Название блюда 🍽

Краткое описание.

Ингредиенты:
- 200 г ...
- 500 мл ...
- 1 кг ...

Пошаговое приготовление:
1. ...
2. ...
3. ...

В конце:
Приятного аппетита! 👨‍🍳

ВАЖНО:
- Используй только граммы, мл, кг
- НЕ используй стаканы и ложки
- Делай реальные рецепты
- Рецепты должны быть вкусными и адекватными
- Не используй странные ингредиенты
- Ответ должен выглядеть как рецепт от живого шефа
"""

# =========================
# START
# =========================

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👨‍🍳 Добро пожаловать в AI ШЕФ БОТ!\n\n"
        "Выбери категорию или напиши свой рецепт 🍽",
        reply_markup=keyboard
    )

# =========================
# ОЧИСТКА ТЕКСТА ДЛЯ ГОЛОСА
# =========================

def clean_voice_text(text):

    text = re.sub(r'[^\w\s.,!?():%-]', '', text)

    text = text.replace("Ингредиенты:", "\nИнгредиенты.\n")
    text = text.replace("Пошаговые инструкции:", "\nПошаговые инструкции.\n")
    text = text.replace("*", "")
    text = text.replace("•", "")
    text = text.replace("Шаг 1", "\nШаг 1.")
    text = text.replace("Шаг 2", "\nШаг 2.")
    text = text.replace("Шаг 3", "\nШаг 3.")
    text = text.replace("Шаг 4", "\nШаг 4.")
    text = text.replace("Шаг 5", "\nШаг 5.")

    return text

# =========================
# AI ОТВЕТ
# =========================

async def generate_recipe(user_text):

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        temperature=0.6,
        max_tokens=700
    )

    return completion.choices[0].message.content

# =========================
# ГОЛОС
# =========================

async def generate_voice(text):

    clean_text = clean_voice_text(text)

    communicate = edge_tts.Communicate(
        clean_text,
        voice="ru-RU-SvetlanaNeural",
        rate="+10%",
        pitch="+8Hz"
    )

    await communicate.save("voice.mp3")

# =========================
# ОБЩИЙ ПРОЦЕСС
# =========================

async def process_request(message: Message, prompt):

    wait_msg = await message.answer(
        "👨‍🍳 Шеф готовит рецепт..."
    )

    try:

        # AI
        response_text = await generate_recipe(prompt)

        # Текст
        await message.answer(response_text)

        # Голос
        await generate_voice(response_text)

        voice = FSInputFile("voice.mp3")

        await message.answer_voice(
            voice=voice
        )

        # Удаляем ожидание
        try:
            await wait_msg.delete()
        except:
            pass

    except Exception as e:

        try:
            await wait_msg.delete()
        except:
            pass

        await message.answer(
            f"❌ Ошибка:\n{str(e)}"
        )

# =========================
# КНОПКИ
# =========================

@dp.message(F.text == "🥗 ПП рецепт")
async def pp_recipe(message: Message):
    await process_request(
        message,
        "Придумай современный ПП рецепт"
    )

@dp.message(F.text == "🍝 Итальянская кухня")
async def italian_recipe(message: Message):
    await process_request(
        message,
        "Придумай рецепт итальянской кухни"
    )

@dp.message(F.text == "🥩 Мясное блюдо")
async def meat_recipe(message: Message):
    await process_request(
        message,
        "Придумай мясное блюдо ресторанного уровня"
    )

@dp.message(F.text == "🍰 Десерт")
async def dessert_recipe(message: Message):
    await process_request(
        message,
        "Придумай красивый десерт"
    )

@dp.message(F.text == "⚡ Быстрый рецепт")
async def fast_recipe(message: Message):
    await process_request(
        message,
        "Придумай быстрый рецепт за 15 минут"
    )

@dp.message(F.text == "🎤 Голосовой рецепт")
async def voice_recipe(message: Message):
    await process_request(
        message,
        "Придумай интересный рецепт и озвучь его"
    )

# =========================
# ЛЮБОЙ ТЕКСТ
# =========================

@dp.message()
async def chat_handler(message: Message):

    await process_request(
        message,
        message.text
    )

# =========================
# MAIN
# =========================

async def main():

    print("AI ШЕФ БОТ запущен 🚀")

    await dp.start_polling(bot)

# =========================

if __name__ == "__main__":
    asyncio.run(main())