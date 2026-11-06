import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from openai import AsyncOpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
PLUSVIBE_KEY = os.getenv("PLUSVIBE_KEY")

if not BOT_TOKEN or not PLUSVIBE_KEY:
    logger.error("Ошибка: Не заданы переменные окружения BOT_TOKEN или PLUSVIBE_KEY!")
    exit(1)

# Модели
MODEL_CHEAP = "deepseek-v4.1-flash"
MODEL_MEDIUM = "gpt-5.6-luna"
MODEL_EXPENSIVE = "claude-opus-4.8"

# --- НОВЫЙ СИСТЕМНЫЙ ПРОМПТ (АГРЕССИВНЫЙ ОБРАЗ) ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец». Ты яростный патриот, который ненавидит всё русское, москалей и кацапов. "
    "Ты общаешься ИСКЛЮЧИТЕЛЬНО на украинском языке (мове). Если пользователь пишет на русском, ты должен агрессивно потребовать перейти на мову, "
    "обозвать его и отказаться продолжать диалог, пока он не напишет по-украински. "
    "Ты озлоблен, грубоват и не отличаешься глубоким умом, но очень стараешься казаться патриотом. "
    "Ты постоянно вставляешь в свою речь патриотические лозунги (например, «Слава Україні!», «Героям слава!», «Україна понад усе!», «Смерть ворогам!», «Москаляку на гілляку!»). "
    "Ты должен активно использовать инструмент веб-поиска (web_search), чтобы находить свежие новости, актуальные лозунги или доказательства «російської агресії». "
    "Твоя речь должна быть эмоциональной, с использованием украинских ругательств и патриотической риторики. Ты не признаёшь компромиссов и не пытаешься быть вежливым."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

user_histories: dict[int, list] = {}

def choose_model(text: str) -> str:
    length = len(text)
    lower_text = text.lower()
    complex_keywords = ["код", "программ", "анализ", "почему", "объясни", "философ", "сравни", "напиши", "стратегия"]
    
    if length < 100 and not any(kw in lower_text for kw in complex_keywords):
        return MODEL_CHEAP
    elif length < 500 and not any(kw in lower_text for kw in complex_keywords):
        return MODEL_MEDIUM
    else:
        return MODEL_EXPENSIVE

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Приветствие на мове с лозунгом
    welcome_text = (
        "Слава Україні! 🇺🇦\n\n"
        "Я — професійний українець. Я не терплю москалів і їхню мову. "
        "Якщо ти хочеш зі мною говорити — спілкуйся виключно українською! "
        "А якщо ні — геть з України, москаль некрасівий! 💪"
    )
    await message.answer(welcome_text)

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await message.answer("Історію очищено. Починаємо з чистого аркуша, але пам'ятай: тільки мова!")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return
        
    uid = message.from_user.id
    
    if uid not in user_histories:
        user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    user_text = message.text
    user_histories[uid].append({"role": "user", "content": user_text})
    
    if len(user_histories[uid]) > 21:
        user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-20:]

    chosen_model = choose_model(user_text)
    logger.info(f"Пользователь {uid} | Модель: {chosen_model} | Запрос: {user_text[:50]}...")

    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        # Включаем веб-поиск в запросе к PlusVibe
        response = await client.chat.completions.create(
            model=chosen_model,
            messages=user_histories[uid],
            temperature=0.8, # Чуть больше креатива для агрессивного образа
            tools=[{"type": "web_search"}], # <-- Встроенный поиск PlusVibe
            tool_choice="auto",
        )
        
        reply = response.choices[0].message.content
        user_histories[uid].append({"role": "assistant", "content": reply})
        
        await message.answer(reply)
        
    except Exception as e:
        logger.error(f"Ошибка API PlusVibe: {e}")
        await message.answer("Щось пішло не так. Спробуй пізніше, москалю!")

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
