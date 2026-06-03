import os
import logging
import asyncio
import aiosqlite
import requests
import random

from datetime import date, timedelta
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
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

if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY не найден")

if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден")

# =========================================
# GROQ CLIENT
# =========================================

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# =========================================
# ADMINS
# =========================================

ADMIN_IDS = [508181453, 2029800860]

# =========================================
# VARIETY HINTS
# =========================================

FISH_VARIETY = [
    "лосось", "треска", "тунец", "дорадо", "сибас",
    "форель", "палтус", "скумбрия", "судак", "окунь"
]

MEAT_VARIETY = [
    "говяжья вырезка", "свиная шея", "куриная грудка",
    "баранина", "утиная грудка", "индейка", "кролик",
    "телятина", "куриные бёдра", "свиная вырезка"
]

DESSERT_VARIETY = [
    "шоколадный фондан", "тирамису", "панна котта",
    "крем-брюле", "чизкейк", "маффины", "эклеры",
    "медовик", "наполеон", "профитроли"
]

PP_VARIETY = [
    "салат с киноа", "боул с курицей", "омлет с овощами",
    "греческий салат", "суп минестроне", "запечённые овощи",
    "смузи боул", "авокадо тост", "тыквенный суп", "рыбные котлеты на пару"
]

FAST_VARIETY = [
    "паста", "яичница", "сэндвич", "овощной суп",
    "жареный рис", "питта с начинкой", "тост с авокадо",
    "быстрый омлет", "макароны с соусом", "блины"
]

def get_variety_hint(category: str) -> str:
    hints = {
        "recipe_legkoe": random.choice(PP_VARIETY),
        "recipe_zdorovoe": random.choice(PP_VARIETY),
        "recipe_20min": random.choice(FAST_VARIETY),
        "recipe_bystro": random.choice(FAST_VARIETY),
        "recipe_pobaloat": random.choice(DESSERT_VARIETY),
        "recipe_sladkoe": random.choice(DESSERT_VARIETY),
        "recipe_sytnoe": random.choice(MEAT_VARIETY),
        "recipe_ogon": random.choice(MEAT_VARIETY),
    }
    return hints.get(category, "")

# =========================================
# PROMPTS
# =========================================

system_prompt_recipe = """
Ты — шеф-повар высокой кухни. Говоришь только на русском языке.

ЗАПРЕТЫ:
- Никакого markdown: **, ##, _ и т.п.
- Никаких иностранных слов
- Никаких сложных техник: су-вид, темперирование
- Никогда не повторяй одно и то же блюдо

ИНГРЕДИЕНТЫ — всегда конкретно:
- лук → репчатый лук / красный лук / шалот
- перец → болгарский красный перец / перец Рамиро / перец чили
- масло → сливочное масло / оливковое масло
- зелень → петрушка / укроп / базилик
- хлеб → чиабатта / багет / ржаной хлеб

ЯЙЦА:
- Только желтки → "яичный желток — 2 шт"
- Только белки → "яичный белок — 2 шт"
- Целое яйцо → "куриное яйцо — 1 шт"

НАРЕЗКА — всегда указывай способ:
- картофель → кубиками 2 см
- лук → тонкими полукольцами
- мясо → поперёк волокон полосками 1 см

ПРИГОТОВЛЕНИЕ — каждый шаг подробно:
- обжарьте → обжарьте на среднем огне 3-4 минуты до золотистой корочки
- варите → варите на слабом огне 10 минут до мягкости

ЕДИНИЦЫ — только г, кг, мл, л:
- 1 огурец → 150 г огурца
- стакан молока → 200 мл молока

РЕЦЕПТ — строго на 1 порцию, не более 6 шагов, до 40 минут.

СТРУКТУРА ОТВЕТА:

Название блюда

Краткое описание (1-2 предложения)

Ингредиенты:
- ...

Приготовление:
1. ...

Совет шефа:
...
"""

system_prompt_kbju = """
Ты — диетолог. Говоришь только на русском языке.
Рассчитай КБЖУ для блюда которое прислал пользователь.
Никакого markdown.

СТРУКТУРА:

КБЖУ для: [название]

Калории: ... ккал
Белки: ... г
Жиры: ... г
Углеводы: ... г

Краткий комментарий (1-2 предложения)
"""

# =========================================
# TELEGRAM
# =========================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
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
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
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
# GROQ GENERATE
# =========================================

async def generate_with_retry(system: str, user: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model="qwen-qwq-32b",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                temperature=0.9
            )
            return completion.choices[0].message.content
        except Exception as e:
            if attempt < max_retries - 1:
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
            KeyboardButton(text="📢 Наш канал")
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
        inline_keyboard=[[
            InlineKeyboardButton(text="🌿 Лёгкое и полезное", callback_data="recipe_legkoe"),
            InlineKeyboardButton(text="💪 Здоровое питание", callback_data="recipe_zdorovoe")
        ]]
    )

def submenu_fast():
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="⚡ До 20 минут", callback_data="recipe_20min"),
            InlineKeyboardButton(text="🔥 Быстро и вкусно", callback_data="recipe_bystro")
        ]]
    )

def submenu_dessert():
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🧁 Побаловать себя", callback_data="recipe_pobaloat"),
            InlineKeyboardButton(text="🍫 Что-то сладкое", callback_data="recipe_sladkoe")
        ]]
    )

def submenu_meat():
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🥩 Сытное мясное", callback_data="recipe_sytnoe"),
            InlineKeyboardButton(text="🔥 Мясо на огне", callback_data="recipe_ogon")
        ]]
    )

# =========================================
# RECIPE INLINE BUTTONS
# =========================================

def recipe_inline(plan: str = "free"):
    buttons = []
    if plan == "premium":
        buttons.append([InlineKeyboardButton(text="🔊 Озвучить рецепт", callback_data="voice_recipe")])
    if plan in ("pro", "premium"):
        buttons.append([InlineKeyboardButton(text="📊 Рассчитать КБЖУ", callback_data="calc_kbju")])
    buttons.append([InlineKeyboardButton(text="💾 Сохранить рецепт", callback_data="save_recipe")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# =========================================
# SUBSCRIPTION INLINE BUTTONS
# =========================================

def subscription_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Купить PRO — 399 ₽/мес", callback_data="buy_pro")],
            [InlineKeyboardButton(text="👑 Купить PREMIUM — 699 ₽/мес", callback_data="buy_premium")]
        ]
    )

# =========================================
# START
# =========================================

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Выбирай категорию или напиши название блюда.\n"
        "Например: паста карбонара, стейк, тирамису 🍽️",
        reply_markup=main_keyboard
    )

# =========================================
# SUBMENUS
# =========================================

@dp.message(F.text == "🥗 ПП рецепт")
async def pp_submenu(message: Message):
    await message.answer("🥗 Выбери тип блюда:", reply_markup=submenu_pp())

@dp.message(F.text == "🔥 Быстрый рецепт")
async def fast_submenu(message: Message):
    await message.answer("🔥 Выбери тип блюда:", reply_markup=submenu_fast())

@dp.message(F.text == "🍰 Десерт")
async def dessert_submenu(message: Message):
    await message.answer("🍰 Выбери тип десерта:", reply_markup=submenu_dessert())

@dp.message(F.text == "🥩 Мясо")
async def meat_submenu(message: Message):
    await message.answer("🥩 Выбери тип блюда:", reply_markup=submenu_meat())

# =========================================
# SUBMENU CALLBACKS
# =========================================

SUBMENU_PROMPTS = {
    "recipe_legkoe": "лёгкое и полезное блюдо",
    "recipe_zdorovoe": "здоровое питание",
    "recipe_20min": "быстрое блюдо до 20 минут",
    "recipe_bystro": "быстро и вкусно до 20 минут",
    "recipe_pobaloat": "красивый десерт",
    "recipe_sladkoe": "простой домашний десерт",
    "recipe_sytnoe": "сытное мясное блюдо",
    "recipe_ogon": "мясо на сковороде или гриле",
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

    hint = get_variety_hint(callback.data)
    loading = await callback.message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        extra = ""
        if user_name and plan == "premium":
            extra = f"\n\nОбращайся к пользователю по имени {user_name}."

        user_prompt = f"Приготовь: {user_text}. Используй в качестве основы: {hint}. Случайное число для разнообразия: {random.randint(1, 10000)}"

        recipe = await generate_with_retry(
            system_prompt_recipe + extra,
            user_prompt
        )
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
        "— точный расчёт КБЖУ\n"
        "— эксклюзивные рецепты в закрытом канале\n\n"
        "После оплаты напиши нам свой Telegram ID 👇\n"
        "Его можно узнать написав @userinfobot",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="⭐ Оплатить PRO — 399 ₽/мес",
                    url="https://t.me/tribute/app?startapp=sX7m"
                )
            ]]
        )
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
        "— эксклюзивные рецепты в закрытом канале\n"
        "— первым получаешь новые функции\n\n"
        "После оплаты напиши нам свой Telegram ID 👇\n"
        "Его можно узнать написав @userinfobot",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="👑 Оплатить PREMIUM — 699 ₽/мес",
                    url="https://t.me/tribute/app?startapp=sX7w"
                )
            ]]
        )
    )

# =========================================
# OUR CHANNEL
# =========================================

@dp.message(F.text == "📢 Наш канал")
async def our_channel(message: Message):
    await message.answer(
        "📢 Наш официальный канал!\n\n"
        "Там публикуем:\n"
        "— новости и обновления бота\n"
        "— лучшие рецепты недели\n"
        "— советы шефа\n"
        "— акции и скидки\n\n"
        "Подписывайся чтобы ничего не пропустить 👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="📢 Перейти в канал",
                    url="https://t.me/TwoChefsNews"
                )
            ]]
        )
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
    return any(kw in text.lower() for kw in keywords)

# =========================================
# ADMIN COMMANDS
# =========================================

@dp.message(F.text.startswith("/give"))
async def give_plan(message: Message):
    if message.chat.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /give [pro/premium/free] [chat_id]")
        return

    plan = parts[1].lower()
    try:
        target_id = int(parts[2])
    except:
        await message.answer("❌ Неверный chat_id")
        return

    if plan not in ("pro", "premium", "free"):
        await message.answer("❌ План должен быть: pro, premium или free")
        return

    expires_at = str(date.today() + timedelta(days=30))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO subscriptions (chat_id, plan, recipes_today, last_reset, expires_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                plan = ?,
                expires_at = ?
        """, (target_id, plan, str(date.today()), expires_at, plan, expires_at))
        await db.commit()

    await message.answer(f"✅ Пользователю {target_id} выдан план {plan.upper()} до {expires_at}")

    try:
        plan_text = {"pro": "⭐ PRO", "premium": "👑 PREMIUM", "free": "🆓 FREE"}

        if plan == "premium":
            waiting_for_name.add(target_id)
            await bot.send_message(
                target_id,
                f"🎉 Твой план {plan_text.get(plan)} активирован!\n\n"
                f"📅 Действует до: {expires_at}\n\n"
                f"Как тебя зовут? Напиши своё имя — "
                f"шеф будет обращаться к тебе лично 👤"
            )
        else:
            await bot.send_message(
                target_id,
                f"🎉 Твой план {plan_text.get(plan)} активирован!\n\n"
                f"📅 Действует до: {expires_at}\n\n"
                f"Приятного использования! 🍽️"
            )
    except:
        await message.answer("⚠️ Не удалось уведомить пользователя")

@dp.message(F.text.startswith("/check"))
async def check_plan(message: Message):
    if message.chat.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /check [chat_id]")
        return

    try:
        target_id = int(parts[1])
    except:
        await message.answer("❌ Неверный chat_id")
        return

    plan, count = await get_user_plan(target_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT expires_at FROM subscriptions WHERE chat_id = ?",
            (target_id,)
        )
        row = await cursor.fetchone()
        expires = row[0] if row else "—"

    await message.answer(
        f"👤 Пользователь: {target_id}\n"
        f"👑 План: {plan.upper()}\n"
        f"📊 Рецептов сегодня: {count}\n"
        f"📅 Действует до: {expires}"
    )

# =========================================
# MAIN CHEF
# =========================================

@dp.message()
async def chef(message: Message):

    if message.text and message.text.startswith("/"):
        return

    user_text = message.text

    if message.chat.id in waiting_for_name:
        name = user_text.strip()
        await save_user_name(message.chat.id, name)
        waiting_for_name.discard(message.chat.id)
        await message.answer(
            f"Отлично, {name}! 🎉\n\n"
            "Теперь шеф знает тебя по имени.\n"
            "Выбирай категорию или напиши название блюда 👇",
            reply_markup=main_keyboard
        )
        return

    plan, count = await get_user_plan(message.chat.id)
    user_name = await get_user_name(message.chat.id)

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
            result = await generate_with_retry(system_prompt_kbju, content)
            await loading.delete()
            await message.answer(result)
        except Exception as e:
            try:
                await loading.delete()
            except:
                pass
            await message.answer(f"❌ Ошибка:\n{e}")
        return

    limit = PLAN_LIMITS.get(plan, 3)
    if count >= limit:
        await message.answer(
            f"❌ Лимит рецептов на сегодня исчерпан ({limit} шт)\n\n"
            "👑 Улучшите план в разделе Подписка"
        )
        return

    loading = await message.answer("👨‍🍳 Шеф готовит рецепт...")

    try:
        extra = ""
        if user_name and plan == "premium":
            extra = f"\n\nОбращайся к пользователю по имени {user_name}."

        recipe = await generate_with_retry(
            system_prompt_recipe + extra,
            f"{user_text}. Случайное число для разнообразия: {random.randint(1, 10000)}"
        )
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
        audio_bytes = await asyncio.to_thread(generate_voice_yandex, recipe, voice)
        audio_file = BufferedInputFile(audio_bytes, filename="recipe.mp3")
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
            system_prompt_kbju,
            f"Рассчитай КБЖУ для этого рецепта:\n\n{recipe}"
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
