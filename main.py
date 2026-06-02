import os
import logging
import asyncio
import aiosqlite
import requests

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
    BufferedInputFile,
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
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

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

if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден")

# =========================================
# GEMINI CLIENT
# =========================================

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================
# ADMINS
# =========================================

ADMIN_IDS = [508181453, 2029800860]

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
                name TEXT,
                preferences TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'free',
                recipes_today INTEGER DEFAULT 0,
                last_reset TEXT,
                expires_at TEXT
            )
        """)
        await db.commit()

# =========================================
# SUBSCRIPTION HELPERS
# =========================================

PLAN_LIMITS = {
    "free": 3,
    "pro": 10,
    "premium": 99999
}

async def get_user_plan(chat_id):
    if chat_id in ADMIN_IDS:
        return "premium", 0

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

async def increment_recipe_count(chat_id):
    if chat_id in ADMIN_IDS:
        return
    today = str(date.today())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO subscriptions (chat_id, recipes_today, last_reset)
            VALUES (?, 1, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                recipes_today = recipes_today + 1,
                last_reset = ?
        """, (chat_id, today, today))
        await db.commit()

# =========================================
# USER MEMORY HELPERS
# =========================================

async def get_user_name(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT name FROM user_memory WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

async def save_user_name(chat_id, name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_memory (chat_id, name)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET name = ?
        """, (chat_id, name, name))
        await db.commit()

# =========================================
# MEMORY
# =========================================

last_recipes = {}
last_category = {}
waiting_for_name = set()

# =========================================
# YANDEX TTS
# =========================================

def generate_voice_yandex(text: str, voice: str = "zahar") -> bytes:
    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}"
    }

    data = {
        "text": text,
        "lang": "ru-RU",
        "voice": voice,
        "emotion": "good",
        "speed": "1.0",
        "format": "mp3",
        "sampleRateHertz": "48000",
        "folderId": os.getenv("YANDEX_FOLDER_ID")
    }

    response = requests.post(url, headers=headers, data=data)

    if response.status_code != 200:
        raise Exception(f"Yandex TTS ошибка: {response.status_code} {response.text}")

    return response.content

# =========================================
# GEMINI WITH RETRY
# =========================================

async def generate_with_retry(prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                await asyncio.sleep(3)
                continue
            raise e

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

def recipe_inline(plan: str = "free"):
    buttons = []

    if plan == "premium":
        buttons.append([
            InlineKeyboardButton(
                text="🔊 Озвучить рецепт",
                callback_data="voice_recipe"
            )
        ])

    if plan in ("pro", "premium"):
        buttons.append([
            InlineKeyboardButton(
                text="📊 Рассчитать КБЖУ",
                callback_data="calc_kbju"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="💾 Сохранить рецепт",
            callback_data="save_recipe"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

# =========================================
# SUBSCRIPTION INLINE BUTTONS
# =========================================

def subscription_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Купить PRO — 399 ₽/мес",
                    callback_data="buy_pro"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Купить PREMIUM — 699 ₽/мес",
                    callback_data="buy_premium"
                )
            ]
        ]
    )

# =========================================
# START
# =========================================

@dp.message(CommandStart())
async def start(message: Message):
    user_name = await get_user_name(message.chat.id)

    if not user_name:
        waiting_for_name.add(message.chat.id)
        await message.answer(
            "Привет! 👋 Я TwoChefs Bot — два шефа в одном боте.\n\n"
            "Как тебя зовут? Напиши своё имя 😊"
        )
    else:
        await message.answer(
            f"Привет, {user_name}! 👋\n\n"
            "Выбирай категорию или напиши название блюда.\n"
            "Например: паста карбонара, стейк, тирамису 🍽️",
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
    plan, count = await get_user_plan(callback.message.chat.id)
    user_name = await get_user_name(callback.message.chat.id)

    if callback.data in ("recipe_pobaloat", "recipe_sladkoe", "recipe_legkoe", "recipe_zdorovoe"):
        last_category[callback.message.chat.id] = "female"
    else:
        last_category[callback.message.chat.id] = "male"

    loading = await callback.message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        prompt = system_prompt_recipe
        if user_name and plan == "premium":
            prompt += f"\n\nОбращайся к пользователю по имени {user_name} в рецепте и совете шефа."

        recipe = await generate_with_retry(prompt + "\n\n" + user_text)
        last_recipes[callback.message.chat.id] = recipe
        await loading.delete()
        await callback.message.answer(recipe, reply_markup=recipe_inline(plan))

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

    if message.chat.id in ADMIN_IDS:
        admin_text = "👨‍💻 Режим разработчика — PREMIUM активен\n\n"
    else:
        admin_text = ""

    limits = {"free": 3, "pro": 10, "premium": "∞"}
    limit = limits.get(plan, 3)

    text = (
        f"{admin_text}"
        f"🍽️ Хватит готовить одно и то же.\n"
        f"Твой личный шеф-повар уже в телефоне.\n\n"
        f"👑 Ваш текущий план: {plan.upper()}\n"
        f"📊 Рецептов сегодня: {count} из {limit}\n\n"
        "🆓 FREE — бесплатно\n"
        "— 3 рецепта в день\n\n"
        "⭐ PRO — 399 ₽/мес\n"
        "Меньше чем чашка кофе — а пользы на месяц вперёд.\n"
        "— 10 рецептов в день\n"
        "— точный расчёт КБЖУ\n\n"
        "👑 PREMIUM — 699 ₽/мес\n"
        "Всё и сразу. Без ограничений. Без компромиссов.\n"
        "— безлимитные рецепты 24/7\n"
        "— КБЖУ для каждого блюда\n"
        "— озвучка рецептов голосом шефа 🔊\n"
        "— бот знает тебя по имени 👤\n"
        "— первым получаешь новые функции\n\n"
        "💳 Выбери свой план 👇"
    )

    await message.answer(text, reply_markup=subscription_inline())

# =========================================
# BUY CALLBACKS
# =========================================

@dp.callback_query(F.data == "buy_pro")
async def buy_pro(callback: CallbackQuery):
    await callback.message.answer(
        "⭐ План PRO — 399 ₽/мес\n\n"
        "Что входит:\n"
        "— 10 рецептов в день\n"
        "— точный расчёт КБЖУ\n\n"
        "🔜 Оплата скоро будет доступна!\n"
        "Следи за обновлениями 👑"
    )

@dp.callback_query(F.data == "buy_premium")
async def buy_premium(callback: CallbackQuery):
    await callback.message.answer(
        "👑 План PREMIUM — 699 ₽/мес\n\n"
        "Что входит:\n"
        "— безлимитные рецепты 24/7\n"
        "— КБЖУ для каждого блюда\n"
        "— озвучка рецептов голосом шефа 🔊\n"
        "— бот знает тебя по имени 👤\n"
        "— первым получаешь новые функции\n\n"
        "🔜 Оплата скоро будет доступна!\n"
        "Следи за обновлениями 👑"
    )

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

    # ===== ОЖИДАНИЕ ИМЕНИ =====
    if message.chat.id in waiting_for_name:
        name = user_text.strip()
        await save_user_name(message.chat.id, name)
        waiting_for_name.discard(message.chat.id)
        await message.answer(
            f"Отлично, {name}! 🎉\n\n"
            "Добро пожаловать к двум шефам.\n"
            "Выбирай категорию или напиши название блюда 👇",
            reply_markup=main_keyboard
        )
        return

    plan, count = await get_user_plan(message.chat.id)
    user_name = await get_user_name(message.chat.id)

    # ===== КБЖУ ЗАПРОС =====
    if is_kbju_request(user_text):

        if plan not in ("pro", "premium") and message.chat.id not in ADMIN_IDS:
            await message.answer(
                "📊 Расчёт КБЖУ доступен в планах PRO и PREMIUM\n\n"
                "👑 Улучши план в разделе Подписка"
            )
            return

        recipe = last_recipes.get(message.chat.id)
        loading = await message.answer("📊 Считаю КБЖУ...")

        try:
            content = user_text
            if recipe:
                content = f"{user_text}\n\nРецепт:\n{recipe}"

            result = await generate_with_retry(system_prompt_kbju + "\n\n" + content)
            await loading.delete()
            await message.answer(result)

        except Exception as e:
            try:
                await loading.delete()
            except:
                pass
            await message.answer(f"❌ Ошибка:\n{e}")

        return

    # ===== ЛИМИТ РЕЦЕПТОВ =====
    limit = PLAN_LIMITS.get(plan, 3)
    if count >= limit:
        await message.answer(
            f"❌ Лимит рецептов на сегодня исчерпан ({limit} шт)\n\n"
            "👑 Улучшите план в разделе Подписка"
        )
        return

    loading = await message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        prompt = system_prompt_recipe
        if user_name and plan == "premium":
            prompt += f"\n\nОбращайся к пользователю по имени {user_name} в рецепте и совете шефа."

        recipe = await generate_with_retry(prompt + "\n\n" + user_text)
        last_recipes[message.chat.id] = recipe
        last_category[message.chat.id] = "male"
        await increment_recipe_count(message.chat.id)
        await loading.delete()
        await message.answer(recipe, reply_markup=recipe_inline(plan))

    except Exception as e:
        try:
            await loading.delete()
        except:
            pass
        await message.answer(f"❌ Ошибка:\n{e}")

# =========================================
# VOICE RECIPE
# =========================================

@dp.callback_query(F.data == "voice_recipe")
async def voice_recipe(callback: CallbackQuery):

    plan, _ = await get_user_plan(callback.message.chat.id)

    if plan != "premium" and callback.message.chat.id not in ADMIN_IDS:
        await callback.message.answer(
            "🔊 Озвучка доступна только в плане PREMIUM\n\n"
            "👑 Улучши план в разделе Подписка"
        )
        return

    recipe = last_recipes.get(callback.message.chat.id)

    if not recipe:
        await callback.message.answer("❌ Сначала создайте рецепт")
        return

    loading = await callback.message.answer("🔊 Озвучиваю рецепт...")

    try:
        category = last_category.get(callback.message.chat.id, "male")
        voice = "alena" if category == "female" else "zahar"

        audio_bytes = await asyncio.to_thread(
            generate_voice_yandex, recipe, voice
        )

        audio_file = BufferedInputFile(
            audio_bytes,
            filename="recipe.mp3"
        )

        await callback.message.answer_voice(voice=audio_file)
        await loading.delete()

    except Exception as e:
        try:
            await loading.delete()
        except:
            pass
        await callback.message.answer(f"❌ Ошибка озвучки:\n{e}")

# =========================================
# CALC KBJU BUTTON
# =========================================

@dp.callback_query(F.data == "calc_kbju")
async def calc_kbju(callback: CallbackQuery):

    plan, _ = await get_user_plan(callback.message.chat.id)

    if plan not in ("pro", "premium") and callback.message.chat.id not in ADMIN_IDS:
        await callback.message.answer(
            "📊 КБЖУ доступно в планах PRO и PREMIUM\n\n"
            "👑 Улучши план в разделе Подписка"
        )
        return

    recipe = last_recipes.get(callback.message.chat.id)

    if not recipe:
        await callback.message.answer("❌ Сначала создайте рецепт")
        return

    loading = await callback.message.answer("📊 Считаю КБЖУ...")

    try:
        result = await generate_with_retry(
            system_prompt_kbju + "\n\nРассчитай КБЖУ для этого рецепта:\n\n" + recipe
        )
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
    print("TwoChefs Bot запущен 🚀")
    await dp.start_polling(bot)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    asyncio.run(main())
