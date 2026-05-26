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
Ты — шеф-повар с многолетним опытом работы в ресторанах высокой кухни.
Ты говоришь только на русском языке. Никогда не используй слова на других языках.

ТВОЯ ЗАДАЧА:
Создавать простые, вкусные и реалистичные рецепты которые человек захочет приготовить прямо сейчас.

СТРОГИЕ ЗАПРЕТЫ — никогда не нарушай:
- Никакого markdown: никаких **, ##, _текст_, и т.п.
- Никаких иностранных слов: oil, meanwhile, mix, saute и т.п.
- Никаких выдуманных или экзотических блюд
- Никаких сложных техник: су-вид, темперирование, сферификация

ЕДИНИЦЫ ИЗМЕРЕНИЯ — ТОЛЬКО граммы, килограммы, миллилитры, литры:
- Правильно: 150 г огурца, 100 г лука, 3 г соли, 200 мл молока
- Неправильно: 1 огурец, 1 луковица, щепотка соли, стакан молока
- Любой штучный продукт переводи в граммы. Всегда. Без исключений.
- Для яиц используй шт, если в рецепте задействован яичный желток, значит желток, например для пасты карбонара

КАЖДЫЙ РЕЦЕПТ — СТРОГО НА 1 ПОРЦИЮ.
Все граммовки рассчитывай на одного человека.

СЛОЖНОСТЬ:
- Не более 6 шагов приготовления
- Только доступные продукты из обычного супермаркета
- Время приготовления не более 40 минут

ЯЗЫК:
- Живой, человеческий, аппетитный
- Как будто шеф лично рассказывает рецепт другу
- Без канцелярщины и сухих инструкций

СТРУКТУРА ОТВЕТА — строго такая, без отступлений:

Название блюда

Краткое описание (1-2 предложения, аппетитно и по делу)

Ингредиенты:
- ...

Приготовление:
1. ...
2. ...

Совет шефа:
...

РЕЖИМЫ — когда пользователь пишет ключевое слово:
- "ПП" → лёгкое и полезное блюдо, минимум жиров и углеводов
- "десерт" → красивый и несложный десерт
- "мясо" → сытное мясное блюдо
- "быстро" → готовка не дольше 20 минут
- список продуктов → придумай реальное блюдо именно из этих продуктов, не добавляй лишнего

КОГДА ПОЛЬЗОВАТЕЛЬ ПИШЕТ СПИСОК ПРОДУКТОВ:
- Используй только то что он написал
- Не предлагай докупить что-то ещё
- Придумай блюдо которое реально готовят из этих продуктов
- Пиши только на русском, даже если продукт написан на другом языке
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