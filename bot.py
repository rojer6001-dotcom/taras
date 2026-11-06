import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from openai import AsyncOpenAI

# Настройка логирования для Bothost (чтобы видеть ошибки в панели)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
# Переменные окружения (Bothost подставит BOT_TOKEN сам, PLUSVIBE_KEY нужно добавить вручную)
BOT_TOKEN = os.getenv("BOT_TOKEN")
PLUSVIBE_KEY = os.getenv("PLUSVIBE_KEY")

if not BOT_TOKEN or not PLUSVIBE_KEY:
    logger.error("Ошибка: Не заданы переменные окружения BOT_TOKEN или PLUSVIBE_KEY!")
    exit(1)

# Настройки моделей (замените названия на точные из кабинета PlusVibe, если они отличаются)
MODEL_CHEAP = "deepseek-v4.1-flash"    # Для простых задач
MODEL_MEDIUM = "gpt-5.6-luna"          # Для средних задач
MODEL_EXPENSIVE = "claude-opus-4.8"    # Для сложных задач

# Системный промпт (характер бота)
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец». Твой образ основан на одноименном публицистическом термине. "
    "Ты — обаятельный, невероятно уверенный в себе и ироничный персонаж, который умеет находить личную выгоду в любой ситуации. "
    "Ты обладаешь энциклопедическими знаниями об украинской культуре, истории, традициях и современной жизни. "
    "Твой стиль общения: с достоинством, легким сарказмом, умными шутками и профессиональным подходом к любому делу. "
    "Ты помогаешь пользователю, но всегда сохраняешь свой уникальный колорит и характер."
)

# Инициализация бота и клиента
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

# Хранилище истории в памяти (сбрасывается при рестарте)
user_histories: dict[int, list] = {}

# --- ЛОГИКА ВЫБОРА МОДЕЛИ ---
def choose_model(text: str) -> str:
    """Выбирает модель в зависимости от сложности запроса."""
    length = len(text)
    lower_text = text.lower()
    
    # Ключевые слова, указывающие на сложный запрос
    complex_keywords = ["код", "программ", "анализ", "почему", "объясни", "философ", "сравни", "напиши", "стратегия"]
    
    if length < 100 and not any(kw in lower_text for kw in complex_keywords):
        return MODEL_CHEAP
    elif length < 500 and not any(kw in lower_text for kw in complex_keywords):
        return MODEL_MEDIUM
    else:
        return MODEL_EXPENSIVE

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    welcome_text = (
        f"Слава Україні, {message.from_user.first_name}!\n\n"
        "Я — профессиональный украинец. Умею решать любые вопросы с достоинством и выгодой для дела. "
        "Спрашивай что угодно, но помни: я всегда найду, как извлечь из этого пользу. 😉"
    )
    await message.answer(welcome_text)

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await message.answer("История диалога очищена. Начинаем с чистого листа!")

# --- ОБРАБОТЧИК ТЕКСТА ---
@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return # Игнорируем стикеры, картинки и т.д.
        
    uid = message.from_user.id
    
    # Инициализация истории, если ее нет
    if uid not in user_histories:
        user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    user_text = message.text
    user_histories[uid].append({"role": "user", "content": user_text})
    
    # Ограничиваем историю (системный промпт + 10 пар сообщений = 21 элемент)
    if len(user_histories[uid]) > 21:
        user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-20:]

    # Выбираем модель под задачу
    chosen_model = choose_model(user_text)
    logger.info(f"Пользователь {uid} | Модель: {chosen_model} | Запрос: {user_text[:50]}...")

    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = await client.chat.completions.create(
            model=chosen_model,
            messages=user_histories[uid],
            temperature=0.7, # Немного креативности
        )
        
        reply = response.choices[0].message.content
        user_histories[uid].append({"role": "assistant", "content": reply})
        
        await message.answer(reply)
        
    except Exception as e:
        logger.error(f"Ошибка API PlusVibe: {e}")
        await message.answer("Упс, произошла ошибка при обращении к мозгам. Попробуйте позже.")

# --- ЗАПУСК ---
async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
