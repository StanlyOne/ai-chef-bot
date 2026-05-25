import os
import re
import asyncio
import logging
import requests
import edge_tts
import base64

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

# =========================================
# ENV
# =========================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# =========================================
# LOGS
# =========================================

logging.basicConfig(level=logging.INFO)

# =========================================
# ПРОВЕРКА КЛЮЧЕЙ
# =========================================

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY не найден")

if not TOGETHER_API_KEY:
    print("❌ TOGETHER_API_KEY не найден")

# =========================================
# GROQ CLIENT
# =========================================

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =========================================
# TELEGRAM
# =========================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

# =========================================
# ПАМЯТЬ
# =========================================

last_recipes = {}

# =========================================
# SYSTEM PROMPT
# =========================================

system_prompt = """
Ты профессиональный шеф-повар Michelin уровня.

Ты создаешь:
- современные
- реалистичные
- вкусные
- ресторанные рецепты

НЕЛЬЗЯ:
- придумывать странные блюда
- использовать markdown
- использовать **
- использовать ###
- отправлять ссылки
- писать бред

НУЖНО:
- реальные техники
- реальные температуры
- граммы
- время приготовления

Формат ответа:

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

# =========================================
# KEYBOARD
# =========================================

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

# =========================================
# INLINE BUTTONS
# =========================================

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

# =========================================
# CLEAN TEXT
# =========================================

def clean_voice_text(text):

    text = re.sub(r"[#*]", "", text)

    text = re.sub(
        r"📸|🔥|🥩|🍰|🥗|🎤|🥬|💾",
        "",
        text
    )

    text = text.replace(
        "Ингредиенты:",
        ". Ингредиенты. "
    )

    text = text.replace(
        "Приготовление:",
        ". Приготовление. "
    )

    text = text.replace(
        "Советы шефа:",
        ". Советы шефа. "
    )

    text = re.sub(r"\n+", ". ", text)

    return text

# =========================================
# VOICE
# =========================================

async def generate_voice(text):

    cleaned = clean_voice_text(text)

    communicate = edge_tts.Communicate(
        text=cleaned,
        voice="ru-RU-SvetaNeural",
        rate="-10%"
    )

    await communicate.save("voice.ogg")

# =========================================
# IMAGE GENERATION
# =========================================

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
        "steps": 4,
        "width": 1024,
        "height": 1024
    }

    response = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers=headers,
        json=payload
    )

    result = response.json()

    print(result)

    image_base64 = result["output"]["choices"][0]["image_base64"]

    return image_base64

# =========================================
# START
# =========================================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "👨‍🍳 Добро пожаловать в AI ШЕФ БОТ\n\n"
        "Я создаю ресторанные рецепты, "
        "озвучиваю их и генерирую фото блюд 📸",
        reply_markup=main_keyboard
    )

# =========================================
# MAIN HANDLER
# =========================================

@dp.message()
async def chef(message: Message):

    user_text = message.text

    loading = await message.answer(
        "👨‍🍳 Шеф готовит рецепт..."
    )

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

        last_recipes[message.chat.id] = recipe

        await loading.delete()

        # ТЕКСТ

        await message.answer(
            recipe,
            reply_markup=recipe_inline()
        )

        # ГОЛОС

        await generate_voice(recipe)

        voice_file = FSInputFile("voice.ogg")

        await message.answer_voice(
            voice=voice_file
        )

    except Exception as e:

        try:
            await loading.delete()
        except:
            pass

        await message.answer(
            f"❌ Ошибка:\n{e}"
        )

# =========================================
# PHOTO BUTTON
# =========================================

@dp.callback_query(F.data == "generate_photo")
async def generate_photo(callback: CallbackQuery):

    recipe = last_recipes.get(
        callback.message.chat.id
    )

    if not recipe:

        await callback.message.answer(
            "❌ Сначала создайте рецепт"
        )

        return

    wait_msg = await callback.message.answer(
        "📸 Генерирую фото блюда..."
    )

    try:

        image_base64 = generate_food_image(recipe)

        image_bytes = base64.b64decode(
            image_base64
        )

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

        try:
            await wait_msg.delete()
        except:
            pass

        await callback.message.answer(
            f"❌ Ошибка генерации фото:\n{e}"
        )

# =========================================
# SAVE BUTTON
# =========================================

@dp.callback_query(F.data == "save_recipe")
async def save_recipe(callback: CallbackQuery):

    await callback.message.answer(
        "💾 Рецепт сохранён в избранное\n\n"
        "Система памяти появится в следующем апгрейде 🔥"
    )

# =========================================
# MAIN
# =========================================

async def main():

    print("AI ШЕФ БОТ запущен 🚀")

    await dp.start_polling(bot)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    asyncio.run(main())