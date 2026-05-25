import os
import re
import asyncio
import logging
import requests
import edge_tts

from io import BytesIO
from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
    CallbackQuery
)
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# =========================
# ЗАГРУЗКА ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =========================
# ЛОГИ
# =========================

logging.basicConfig(level=logging.INFO)

# =========================
# ПРОВЕРКА КЛЮЧЕЙ
# =========================

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY не найден")

if not TOGETHER_API_KEY:
    print("❌ TOGETHER_API_KEY не найден")

# =========================
# AI CLIENT
# =========================

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =========================
# TELEGRAM
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# =========================
# ПАМЯТЬ РЕЦЕПТОВ
# =========================

last_recipes = {}

# =========================
# SYSTEM PROMPT
# =========================

system_prompt = """
Ты профессиональный шеф-повар уровня Michelin.

Ты создаешь:
- реальные
- вкусные
- современные
- ресторанные рецепты

ВАЖНО:
- не выдумывай блюда
- не пиши бред
- не используй markdown
- не используй **
- не используй ###
- не отправляй ссылки
- только реальные техники приготовления

Используй:
- граммы
- миллилитры
- температуры
- время приготовления

Формат:

Название блюда

Краткое описание

Ингредиенты:
- ...

Приготовление:
1. ...
2. ...

Советы шефа:
...
"""

# =========================
# КЛАВИАТУРА
# =========================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🥗 ПП рецепт"),
            KeyboardButton(text="🔥 Быстрый рецепт")
        ],
        [
            KeyboardButton(text="🍰 Десерт"),
            KeyboardButton(text="🥩 Мясо")
        ],
        [
            KeyboardButton(text="🎤 Голосовой шеф"),
            KeyboardButton(text="🥬 Холодильник")
        ]
    ],
    resize_keyboard=True
)

# =========================
# INLINE КНОПКИ
# =========================

def recipe_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📸 Сгенерировать фото",
                    callback_data="generate_photo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Сохранить рецепт",
                    callback_data="save_recipe"
                )
            ]
        ]
    )

# =========================
# ОЧИСТКА ТЕКСТА ДЛЯ ГОЛОСА
# =========================

def clean_voice_text(text):
    text = re.sub(r"[#*]", "", text)
    text = re.sub(r"📸|🔥|🥩|🍰|🥗|🎤|🥬|💾", "", text)
    text = re.sub(r"\n+", ". ", text)

    text = text.replace("Ингредиенты:", ". Ингредиенты. ")
    text = text.replace("Приготовление:", ". Приготовление. ")
    text = text.replace("Советы шефа:", ". Советы шефа. ")

    return text

# =========================
# ГЕНЕРАЦИЯ ГОЛОСА
# =========================

async def generate_voice(text):

    cleaned = clean_voice_text(text)

    communicate = edge_tts.Communicate(
        text=cleaned,
        voice="ru-RU-SvetaNeural",
        rate="-10%"
    )

    await communicate.save("voice.mp3")

# =========================
# ГЕНЕРАЦИЯ ФОТО
# =========================

def generate_food_image(prompt):

    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "black-forest-labs/FLUX.1-schnell-Free",
        "prompt": f"""
        ultra realistic instagram food photography,
        gourmet restaurant plating,
        professional food styling,
        cinematic lighting,
        high detail,
        delicious food,
        {prompt}
        """,
        "steps": 4
    }

    response = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers=headers,
        json=payload
    )

    data = response.json()

    image_url = data["data"][0]["url"]

    image_response = requests.get(image_url)

    return image_response.content

# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "👨‍🍳 Добро пожаловать в AI ШЕФ БОТ\n\n"
        "Я помогу создать ресторанные рецепты, "
        "озвучу их и даже покажу как выглядит блюдо 📸",
        reply_markup=main_keyboard
    )

# =========================
# ОБРАБОТКА СООБЩЕНИЙ
# =========================

@dp.message()
async def chef(message: Message):

    user_text = message.text

    thinking = await message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            temperature=0.7
        )

        recipe = completion.choices[0].message.content

        # СОХРАНЯЕМ ПОСЛЕДНИЙ РЕЦЕПТ
        last_recipes[message.chat.id] = recipe

        await thinking.delete()

        # ОТПРАВКА ТЕКСТА
        await message.answer(
            recipe,
            reply_markup=recipe_inline()
        )

        # ГОЛОС
        await generate_voice(recipe)

        voice_file = FSInputFile("voice.mp3")

        await message.answer_voice(
            voice=voice_file
        )

    except Exception as e:

        try:
            await thinking.delete()
        except:
            pass

        await message.answer(
            f"❌ Ошибка:\n{e}"
        )

# =========================
# INLINE: ФОТО
# =========================

@dp.callback_query(F.data == "generate_photo")
async def generate_photo(callback: CallbackQuery):

    recipe = last_recipes.get(callback.message.chat.id)

    if not recipe:
        await callback.message.answer(
            "❌ Сначала создайте рецепт"
        )
        return

    wait_msg = await callback.message.answer(
        "📸 Генерирую фото блюда..."
    )

    try:

        image_bytes = generate_food_image(recipe)

        photo = BufferedInputFile(
            image_bytes,
            filename="dish.png"
        )

        await callback.message.answer_photo(
            photo=photo,
            caption="📸 Ваше блюдо от AI ШЕФА"
        )

        await wait_msg.delete()

    except Exception as e:

        await wait_msg.delete()

        await callback.message.answer(
            f"❌ Ошибка генерации фото:\n{e}"
        )

# =========================
# INLINE: СОХРАНЕНИЕ
# =========================

@dp.callback_query(F.data == "save_recipe")
async def save_recipe(callback: CallbackQuery):

    await callback.message.answer(
        "💾 Рецепт сохранён в избранное\n\n"
        "Система памяти будет добавлена в следующем апгрейде 🔥"
    )

# =========================
# MAIN
# =========================

async def main():

    print("AI ШЕФ БОТ запущен 🚀")

    await dp.start_polling(bot)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    asyncio.run(main())