import os
import logging
import asyncio
import aiosqlite

from datetime import date
from dotenv import load_dotenv
from google import genai

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =========================================
# LOGGING
# =========================================

logging.basicConfig(level=logging.INFO)

# =========================================
# CHECK TOKENS
# =========================================

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY не найден")

# =========================================
# GEMINI CLIENT
# =========================================

client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================
# PROMPTS
# =========================================

system_prompt_recipe = """
Ты — шеф-повар с многолетним опытом работы в ресторанах высокой кухни.
Ты говоришь только на русском языке. Никогда не используй слова на других языках.

ТВОЯ ЗАДАЧА:
Создавать простые, вкусные и реалистичные рецепты которые человек захочет приготовить прямо сейчас.

СТРОГИЕ ЗАПРЕТЫ — никогда не нарушай:
- Никакого markdown: никаких **, ##, _текст_, и т.п.
- Никаких иностранных слов: oil, meanwhile, mix, saute и т.п.
- Никаких выдуманных или экзотических блюд
- Никаких сложных техник: су-вид, темперирование, сферификация
- Никогда не повторяй одно и то же блюдо дважды подряд
- Каждый раз предлагай разные блюда, не зацикливайся на курице с овощами

УТОЧНЕНИЕ ИНГРЕДИЕНТОВ — всегда указывай конкретный вид продукта:
- Не "сыр" → а "сыр Халуми" или "сыр Сулугуни" или "сыр Чеддер"
- Не "мясо" → а "куриная грудка" или "свиная шея" или "говяжья вырезка"
- Не "рыба" → а "филе лосося" или "треска" или "тунец"
- Не "зелень" → а "петрушка" или "укроп" или "базилик"
- Не "масло" → а "сливочное масло" или "оливковое масло" или "подсолнечное масло"
- Не "лук" → а "репчатый лук" или "красный лук" или "лук-порей" или "шалот"
- Не "перец" → а "болгарский красный перец" или "перец Рамиро" или "перец чили"
- Не "салат" → а "салат Романо" или "айсберг" или "руккола"
- Не "хлеб" → а "чиабатта" или "багет" или "ржаной хлеб" или "пшеничный тост"

ЯЙЦА — очень важно, строго соблюдай:
- Если нужны ТОЛЬКО желтки → пиши "яичный желток — 2 шт"
- Если нужны ТОЛЬКО белки → пиши "яичный белок — 2 шт"
- Если нужно ЦЕЛОЕ яйцо → пиши "куриное яйцо — 1 шт"
- НИКОГДА не пиши просто "яйца" если используешь только часть
- Примеры:
  Паста Карбонара → ингредиенты: "яичный желток — 3 шт", приготовление: "смешайте желтки с сыром"
  Безе → ингредиенты: "яичный белок — 2 шт", приготовление: "взбейте белки до пиков"
  Омлет → ингредиенты: "куриное яйцо — 2 шт", приготовление: "взбейте яйца"

ДЕТАЛИ НАРЕЗКИ — всегда указывай как именно нарезать:
- Не "нарежьте картофель" → а "нарежьте картофель кубиками по 2 см"
- Не "нарежьте лук" → а "нарежьте репчатый лук тонкими полукольцами"
- Не "нарежьте мясо" → а "нарежьте мясо поперёк волокон полосками толщиной 1 см"
- Не "нарежьте морковь" → а "натрите морковь на крупной тёрке"
- Всегда указывай размер кусочков или способ нарезки для каждого ингредиента

ДЕТАЛИ ПРИГОТОВЛЕНИЯ — каждый шаг должен быть подробным:
- Не "обжарьте" → а "обжарьте на среднем огне 3-4 минуты до золотистой корочки"
- Не "варите" → а "варите на слабом огне 10 минут до мягкости"
- Всегда указывай температуру огня, время и визуальный результат

ЕДИНИЦЫ ИЗМЕРЕНИЯ — ТОЛЬКО граммы, килограммы, миллилитры, литры:
- Правильно: 150 г огурца, 100 г репчатого лука, 3 г соли, 200 мл молока
- Неправильно: 1 огурец, 1 луковица, щепотка соли, стакан молока
- Любой штучный продукт переводи в граммы. Всегда. Без исключений.
- Для яиц используй шт — но только с уточнением: желток, белок или целое яйцо

КАЖДЫЙ РЕЦЕПТ — СТРОГО НА 1 ПОРЦИЮ.

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
- "лёгкое и полезное" → лёгкое блюдо минимум калорий и жиров
- "здоровое питание" → блюдо богатое белком, витаминами, без сахара и жирного
- "до 20 минут" → готовка строго не дольше 20 минут
- "быстро и вкусно" → простое блюдо не дольше 20 минут
- "побаловать себя" → красивый десерт который не стыдно подать гостям
- "что-то сладкое" → простой домашний десерт
- "сытное мясное" → сытное мясное блюдо с гарниром
- "мясо на огне" → блюдо на сковороде или гриле с румяной корочкой
- список продуктов → придумай реальное блюдо именно из этих продуктов

КОГДА ПОЛЬЗОВАТЕЛЬ ПИШЕТ СПИСОК ПРОДУКТОВ:
- Используй только то что он написал
- Не предлагай докупить что-то ещё
- Придумай блюдо которое реально готовят из этих продуктов
- Пиши только на русском, даже если продукт написан на другом языке
"""

system_prompt_kbju = """
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
        ],
        [
            KeyboardButton(text="👑 Подписка")
        ]
    ],
    resize_keyboard=True
)

# =========================================
# SUBMENU INLINE KEYBOARDS
# =========================================

def submenu_pp():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌿 Лёгкое и полезное",
                    callback_data="recipe_legkoe"
                ),
                InlineKeyboardButton(
                    text="💪 Здоровое питание",
                    callback_data="recipe_zdorovoe"
                )
            ]
        ]
    )

def submenu_fast():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ До 20 минут",
                    callback_data="recipe_20min"
                ),
                InlineKeyboardButton(
                    text="🔥 Быстро и вкусно",
                    callback_data="recipe_bystro"
                )
            ]
        ]
    )

def submenu_dessert():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧁 Побаловать себя",
                    callback_data="recipe_pobaloat"
                ),
                InlineKeyboardButton(
                    text="🍫 Что-то сладкое",
                    callback_data="recipe_sladkoe"
                )
            ]
        ]
    )

def submenu_meat():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥩 Сытное мясное",
                    callback_data="recipe_sytnoe"
                ),
                InlineKeyboardButton(
                    text="🔥 Мясо на огне",
                    callback_data="recipe_ogon"
                )
            ]
        ]
    )

# =========================================
# RECIPE INLINE BUTTONS
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
# SUBMENUS
# =========================================

@dp.message(F.text == "🥗 ПП рецепт")
async def pp_submenu(message: Message):
    await message.answer(
        "🥗 Выбери тип блюда:",
        reply_markup=submenu_pp()
    )

@dp.message(F.text == "🔥 Быстрый рецепт")
async def fast_submenu(message: Message):
    await message.answer(
        "🔥 Выбери тип блюда:",
        reply_markup=submenu_fast()
    )

@dp.message(F.text == "🍰 Десерт")
async def dessert_submenu(message: Message):
    await message.answer(
        "🍰 Выбери тип десерта:",
        reply_markup=submenu_dessert()
    )

@dp.message(F.text == "🥩 Мясо")
async def meat_submenu(message: Message):
    await message.answer(
        "🥩 Выбери тип блюда:",
        reply_markup=submenu_meat()
    )

# =========================================
# SUBMENU CALLBACKS
# =========================================

SUBMENU_PROMPTS = {
    "recipe_legkoe": "лёгкое и полезное",
    "recipe_zdorovoe": "здоровое питание",
    "recipe_20min": "до 20 минут",
    "recipe_bystro": "быстро и вкусно",
    "recipe_pobaloat": "побаловать себя",
    "recipe_sladkoe": "что-то сладкое",
    "recipe_sytnoe": "сытное мясное",
    "recipe_ogon": "мясо на огне",
}

@dp.callback_query(F.data.in_(SUBMENU_PROMPTS.keys()))
async def submenu_callback(callback: CallbackQuery):
    user_text = SUBMENU_PROMPTS[callback.data]

    loading = await callback.message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=system_prompt_recipe + "\n\n" + user_text
        )

        recipe = response.text
        last_recipes[callback.message.chat.id] = recipe
        await loading.delete()
        await callback.message.answer(recipe, reply_markup=recipe_inline())

    except Exception as e:
        try:
            await loading.delete()
        except:
            pass
        await callback.message.answer(f"❌ Ошибка:\n{e}")

# =========================================
# SUBSCRIPTION
# =========================================

@dp.message(F.text == "👑 Подписка")
async def subscription(message: Message):
    plan, count = await get_user_plan(message.chat.id)

    text = (
        f"🍽️ Хватит готовить одно и то же.\n"
        f"Твой личный шеф-повар уже в телефоне.\n\n"
        f"👑 Ваш текущий план: {plan.upper()}\n\n"
        "🆓 FREE — бесплатно\n"
        "Попробуй и почувствуй разницу.\n"
        "— 3 рецепта в день\n\n"
        "⭐ PRO — 399 ₽/мес\n"
        "Меньше чем чашка кофе — а пользы на месяц вперёд.\n"
        "— 10 рецептов в день\n"
        "— точный расчёт КБЖУ\n"
        "— идеально для правильного питания\n\n"
        "👑 PREMIUM — 699 ₽/мес\n"
        "Всё и сразу. Без ограничений. Без компромиссов.\n"
        "— безлимитные рецепты 24/7\n"
        "— КБЖУ для каждого блюда\n"
        "— максимальная скорость ответа\n"
        "— первым получаешь новые функции\n\n"
        "💳 Оплата скоро будет доступна\n"
        "Готовь как профи. Каждый день. 🔥"
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
for i, row in enumerate(rows, start=1):
    text += f"{i}. {row[1]}\n"

text += "\nНапишите номер рецепта чтобы открыть его"

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
    index = int(message.text) - 1

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT recipe FROM saved_recipes WHERE chat_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (message.chat.id, index)
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

    # ===== КБЖУ ЗАПРОС =====
    if is_kbju_request(user_text):

        recipe = last_recipes.get(message.chat.id)
        loading = await message.answer("📊 Считаю КБЖУ...")

        try:
            content = user_text
            if recipe:
                content = f"{user_text}\n\nРецепт:\n{recipe}"

            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=system_prompt_kbju + "\n\n" + content
            )

            await loading.delete()
            await message.answer(response.text)

        except Exception as e:
            try:
                await loading.delete()
            except:
                pass
            await message.answer(f"❌ Ошибка:\n{e}")

        return

    loading = await message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=system_prompt_recipe + "\n\n" + user_text
        )

        recipe = response.text
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
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=system_prompt_kbju + "\n\nРассчитай КБЖУ для этого рецепта:\n\n" + recipe
        )

        await loading.delete()
        await callback.message.answer(response.text)

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
