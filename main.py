import os
import logging
import asyncio
import aiosqlite

from datetime import date
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
# DATABASE
# =========================================

DB_PATH = "chef_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                title TEXT,
                recipe TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                chat_id INTEGER PRIMARY KEY,
                preferences TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'free',
                recipes_today INTEGER DEFAULT 0,
                last_reset TEXT
            )
        """)
        await db.commit()

# =========================================
# SUBSCRIPTION HELPERS
# =========================================

PLAN_LIMITS = {
    "free": 99999,
    "pro": 99999,
    "premium": 99999
}

async def get_user_plan(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT plan, recipes_today, last_reset FROM subscriptions WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return "free", 0
        plan, count, last_reset = row
        today = str(date.today())
        if last_reset != today:
            await db.execute(
                "UPDATE subscriptions SET recipes_today = 0, last_reset = ? WHERE chat_id = ?",
                (today, chat_id)
            )
            await db.commit()
            return plan, 0
        return plan, count

# =========================================
# MEMORY
# =========================================

last_recipes = {}

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

УТОЧНЕНИЕ ИНГРЕДИЕНТОВ — всегда указывай конкретный вид продукта:
- Не "сыр" → а "сыр Халуми" или "сыр Сулугуни"
- Не "мясо" → а "куриная грудка" или "свиная шея"
- Не "рыба" → а "филе лосося" или "треска"
- Не "зелень" → а "петрушка" или "укроп"
- Не "масло" → а "сливочное масло" или "оливковое масло"
- Не "сыр" для жарки → обязательно укажи сыр который плавится и держит форму

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

kbju_prompt = """
Ты — диетолог и нутрициолог.
Ты говоришь только на русском языке.

ТВОЯ ЗАДАЧА:
Рассчитать точное КБЖУ для блюда или рецепта который прислал пользователь.

СТРОГИЕ ЗАПРЕТЫ:
- Никакого markdown: никаких **, ##, и т.п.
- Никаких иностранных слов
- Не придумывай рецепт — только считай КБЖУ

СТРУКТУРА ОТВЕТА — строго такая:

КБЖУ для: [название блюда]

Калории: ... ккал
Белки: ... г
Жиры: ... г
Углеводы: ... г

Краткий комментарий (1-2 предложения о пользе или особенностях блюда)
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
        ],
        [
            KeyboardButton(text="👑 Подписка")
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
                    text="📊 Рассчитать КБЖУ",
                    callback_data="calc_kbju"
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
# START
# =========================================

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👨‍🍳 Добро пожаловать в AI ШЕФ БОТ\n\n"
        "Я создаю ресторанные рецепты 🍽️\n\n"
        "Напишите название блюда или выберите категорию:",
        reply_markup=main_keyboard
    )

# =========================================
# SUBSCRIPTION
# =========================================

@dp.message(F.text == "👑 Подписка")
async def subscription(message: Message):
    plan, count = await get_user_plan(message.chat.id)
    limits = {"free": "∞", "pro": "∞", "premium": "∞"}
    limit = limits.get(plan, "∞")

    text = (
        f"👑 Ваш текущий план: {plan.upper()}\n"
        f"📊 Рецептов сегодня: {count}\n\n"
        "📦 Доступные планы:\n\n"
        "🆓 FREE\n"
        "— 3 рецепта в день\n\n"
        "⭐ PRO — 299 руб/мес\n"
        "— 10 рецептов в день\n"
        "— расчёт КБЖУ\n\n"
        "👑 PREMIUM — 599 руб/мес\n"
        "— безлимитные рецепты\n"
        "— расчёт КБЖУ\n"
        "— приоритетная генерация\n\n"
        "🔜 Оплата скоро будет доступна"
    )

    await message.answer(text)

# =========================================
# FAVORITES
# =========================================

@dp.message(F.text == "💾 Избранное")
async def favorites(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, title FROM saved_recipes WHERE chat_id = ?",
            (message.chat.id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("📭 У вас пока нет сохранённых рецептов")
        return

    text = "💾 Ваши сохранённые рецепты:\n\n"
    for row in rows:
        text += f"{row[0]}. {row[1]}\n"

    text += "\nНапишите номер рецепта чтобы открыть его"
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
# OPEN RECIPE BY NUMBER
# =========================================

@dp.message(F.text.regexp(r"^\d+$"))
async def open_recipe(message: Message):
    recipe_id = int(message.text)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT recipe FROM saved_recipes WHERE id = ? AND chat_id = ?",
            (recipe_id, message.chat.id)
        )
        row = await cursor.fetchone()

    if not row:
        await message.answer("❌ Рецепт не найден")
        return

    await message.answer(row[0])

# =========================================
# KBJU REQUEST DETECTION
# =========================================

def is_kbju_request(text: str) -> bool:
    keywords = [
        "кбжу", "калории", "калорийность",
        "рассчитай кбжу", "посчитай кбжу",
        "сколько калорий", "белки жиры углеводы",
        "пищевая ценность", "бжу"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

# =========================================
# MAIN CHEF
# =========================================

@dp.message()
async def chef(message: Message):

    if message.text and message.text.startswith("/"):
        return

    user_text = message.text
    plan, count = await get_user_plan(message.chat.id)

    # ===== КБЖУ ЗАПРОС =====
    if is_kbju_request(user_text):

        recipe = last_recipes.get(message.chat.id)
        loading = await message.answer("📊 Считаю КБЖУ...")

        try:
            content = user_text
            if recipe:
                content = f"{user_text}\n\nРецепт:\n{recipe}"

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": kbju_prompt},
                    {"role": "user", "content": content}
                ],
                temperature=0.3
            )

            result = completion.choices[0].message.content
            await loading.delete()
            await message.answer(result)

        except Exception as e:
            try:
                await loading.delete()
            except:
                pass
            await message.answer(f"❌ Ошибка:\n{e}")

        return

    loading = await message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.8
        )

        recipe = completion.choices[0].message.content
        last_recipes[message.chat.id] = recipe
        await loading.delete()
        await message.answer(recipe, reply_markup=recipe_inline())

    except Exception as e:
        try:
            await loading.delete()
        except:
            pass
        await message.answer(f"❌ Ошибка:\n{e}")

# =========================================
# CALC KBJU BUTTON
# =========================================

@dp.callback_query(F.data == "calc_kbju")
async def calc_kbju(callback: CallbackQuery):

    recipe = last_recipes.get(callback.message.chat.id)

    if not recipe:
        await callback.message.answer("❌ Сначала создайте рецепт")
        return

    loading = await callback.message.answer("📊 Считаю КБЖУ...")

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": kbju_prompt},
                {"role": "user", "content": f"Рассчитай КБЖУ для этого рецепта:\n\n{recipe}"}
            ],
            temperature=0.3
        )

        result = completion.choices[0].message.content
        await loading.delete()
        await callback.message.answer(result)

    except Exception as e:
        try:
            await loading.delete()
        except:
            pass
        await callback.message.answer(f"❌ Ошибка:\n{e}")

# =========================================
# SAVE RECIPE
# =========================================

@dp.callback_query(F.data == "save_recipe")
async def save_recipe(callback: CallbackQuery):

    recipe = last_recipes.get(callback.message.chat.id)

    if not recipe:
        await callback.message.answer("❌ Нет рецепта для сохранения")
        return

    lines = [l.strip() for l in recipe.split("\n") if l.strip()]
    title = lines[0]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO saved_recipes (chat_id, title, recipe) VALUES (?, ?, ?)",
            (callback.message.chat.id, title, recipe)
        )
        await db.commit()

    await callback.message.answer("💾 Рецепт сохранён в избранное")

# =========================================
# MAIN
# =========================================

async def main():
    await init_db()
    print("AI ШЕФ БОТ запущен 🚀")
    await dp.start_polling(bot)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    asyncio.run(main())