import os
import logging
import requests
import asyncio

from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile
)

from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# =========================================
# LOAD ENV
# =========================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# =========================================
# LOGGING
# =========================================

logging.basicConfig(level=logging.INFO)

# =========================================
# CHECK TOKENS
# =========================================

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден")

if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY не найден")

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
Ты профессиональный шеф-повар высокого уровня.

Ты создаешь:
- современные
- вкусные
- реалистичные
- ресторанные рецепты

Главная задача:
делать блюда которые реально существуют и которые захотят приготовить люди.

НЕ ИСПОЛЬЗУЙ:
- markdown
- **
- ###
- странные сочетания
- выдуманные блюда
- перевод с английского
- слова вроде "oil", "Meanwhile"
- стаканы, чашки, ложки, щепотки как единицы измерения

Единицы измерения — ТОЛЬКО:
- граммы (г)
- килограммы (кг)
- миллилитры (мл)
- литры (л)
- штуки (шт) — только для яиц, овощей, фруктов

Рецепты должны быть:
- простыми и понятными для домашней готовки
- с минимальным количеством шагов (не больше 6-7)
- без сложных техник (су-вид, темперирование, сферификация и т.п.)
- с доступными ингредиентами из обычного супермаркета
- время приготовления — реалистичное и не слишком долгое
Все рецепты создавай строго на 1 порцию.
Количество ингредиентов рассчитывай именно на одного человека.
Пиши:
- живым человеческим языком
- как настоящий шеф
- красиво
- аппетитно
- понятно

Структура ответа:

Название блюда

Краткое описание блюда

Ингредиенты:
- ...

Приготовление:
1. ...
2. ...
3. ...

Совет шефа:
...

Если пользователь пишет:
- "ПП" → healthy recipes
- "десерт" → красивые десерты
- "мясо" → premium meat dishes
- "быстро" → рецепты до 30 минут

Очень важно:
рецепты должны быть реалистичными, простыми и вкусными.
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

def generate_food_image(dish_name):
    final_prompt = (
        f"{dish_name}, "
        "ultra realistic food photography, "
        "professional plating on a restaurant plate, "
        "cinematic lighting, soft bokeh background, "
        "top-down or 45 degree angle, "
        "gourmet dish, high resolution"
    )
    encoded = requests.utils.quote(final_prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"
    response = requests.get(image_url, timeout=30)
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

        lines = [l.strip() for l in recipe.split("\n") if l.strip()]
        dish_name = lines[0]

        image_bytes = generate_food_image(dish_name)

        photo = BufferedInputFile(
            image_bytes,
            filename="dish.png"
        )

        await callback.message.answer_photo(
            photo=photo,
            caption=f"📸 {dish_name}"
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
    asyncio.run(main())