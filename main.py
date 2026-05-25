import os
import logging
import requests

from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
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
# LOGGING
# =========================================

logging.basicConfig(level=logging.INFO)

# =========================================
# CHECK TOKENS
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
# MEMORY
# =========================================

last_recipes = {}

saved_recipes = {}

# =========================================
# SYSTEM PROMPT
# =========================================

system_prompt = """
Ты профессиональный шеф-повар Michelin уровня.

Ты создаешь:
- современные ресторанные блюда
- красивые подачи
- реальные техники приготовления
- вкусные сочетания

НЕЛЬЗЯ:
- markdown
- **
- ###
- ссылки
- странные рецепты
- выдуманные ингредиенты

НУЖНО:
- понятный текст
- красивые описания
- реальные рецепты
- температуры
- граммовки
- советы шефа

Формат:

Название блюда

Описание блюда

Ингредиенты:
- ...

Приготовление:
1. ...
2. ...

Советы шефа:
...
"""

# =========================================
# MAIN KEYBOARD
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
            KeyboardButton(text="🥬 Холодильник"),
            KeyboardButton(text="💾 Избранное")
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
# IMAGE GENERATION
# =========================================

def generate_food_image(prompt):

    image_url = f"https://image.pollinations.ai/prompt/{prompt} gourmet food photography ultra realistic"

    response = requests.get(image_url)

    return response.content

# =========================================
# START
# =========================================

@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "👨‍🍳 Добро пожаловать в AI ШЕФ БОТ\n\n"
        "Я создаю ресторанные рецепты и фото блюд 📸",
        reply_markup=main_keyboard
    )

# =========================================
# FAVORITES
# =========================================

@dp.message(F.text == "💾 Избранное")
async def favorites(message: Message):

    recipes = saved_recipes.get(message.chat.id)

    if not recipes:

        await message.answer(
            "📭 У вас пока нет сохранённых рецептов"
        )

        return

    text = "💾 Ваши сохранённые рецепты:\n\n"

    for i, recipe in enumerate(recipes, start=1):

        title = recipe.split("\n")[0]

        text += f"{i}. {title}\n"

    await message.answer(text)

# =========================================
# FRIDGE MODE
# =========================================

@dp.message(F.text == "🥬 Холодильник")
async def fridge_mode(message: Message):

    await message.answer(
        "🥬 Напишите ингредиенты которые у вас есть.\n\n"
        "Например:\n"
        "курица, сливки, паста, шампиньоны"
    )

# =========================================
# MAIN CHEF
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
            temperature=0.8
        )

        recipe = completion.choices[0].message.content

        last_recipes[message.chat.id] = recipe

        await loading.delete()

        await message.answer(
            recipe,
            reply_markup=recipe_inline()
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
# GENERATE PHOTO
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

        try:
            await wait_msg.delete()
        except:
            pass

        await callback.message.answer(
            f"❌ Ошибка генерации фото:\n{e}"
        )

# =========================================
# SAVE RECIPE
# =========================================

@dp.callback_query(F.data == "save_recipe")
async def save_recipe(callback: CallbackQuery):

    recipe = last_recipes.get(
        callback.message.chat.id
    )

    if not recipe:

        await callback.message.answer(
            "❌ Нет рецепта для сохранения"
        )

        return

    if callback.message.chat.id not in saved_recipes:

        saved_recipes[callback.message.chat.id] = []

    saved_recipes[callback.message.chat.id].append(recipe)

    await callback.message.answer(
        "💾 Рецепт сохранён в избранное"
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
    import asyncio

    asyncio.run(main())