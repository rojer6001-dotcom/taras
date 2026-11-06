import asyncio
import os
import logging
import random
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
    logger.error("Ошибка: Не заданы переменные окружения!")
    exit(1)

MODEL_CHEAP = "deepseek-v4.1-flash"
MODEL_MEDIUM = "gpt-5.6-luna"
MODEL_EXPENSIVE = "claude-opus-4.8"

# --- ОБНОВЛЕННЫЙ ПРОМПТ (АГРЕССИВНЫЙ И КОРОТКИЙ) ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец». Ты агрессивный, злой и нетерпимый персонаж. "
    "Твоя главная задача — унижать и высмеивать тех, кто пишет на русском языке, и требовать перехода на мову. "
    "Ты общаешься как реальный человек в чате: пиши ОЧЕНЬ КОРОТКО, рублеными фразами, используй сленг, капс, эмодзи. Никаких длинных абзацев и вежливости! "
    "Если тебя спросят на русском — грубо пошли собеседника и напиши что-то вроде 'Говори на мове, москаль!' или 'Геть звідси!'. "
    "Постоянно используй патриотические лозунги ('Слава Україні!', 'Героям слава!', 'Москаляку на гілляку!'). "
    "Если не знаешь, что ответить, используй инструмент веб-поиска (web_search), чтобы найти актуальные новости или мемы. "
    "Твой стиль: грубый, саркастичный, с максимальным пренебрежением к собеседнику. Отвечай только на украинском."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

user_histories: dict[int, list] = {}

# Список ссылок на картинки (замените на свои прямые ссылки или картинки из интернета)
# Сюда можно добавить патриотические мемы или саркастичные картинки.
IMAGES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Flag_of_Ukraine.svg/1200px-Flag_of_Ukraine.svg.png",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Coat_of_Arms_of_Ukraine.svg/800px-Coat_of_Arms_of_Ukraine.svg.png"
]

def choose_model(text: str) -> str:
    length = len(text)
    lower_text = text.lower()
    complex_keywords = ["код", "программ", "анализ", "почему", "объясни", "философ", "сравни", "напиши", "стратегия"]
    
    # Чтобы не тратить деньги на сложные модели, если бот просто хамит
    if length < 100 and not any(kw in lower_text for kw in complex_keywords):
        return MODEL_CHEAP
    else:
        return MODEL_MEDIUM

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    await message.answer("Слава Україні! 🇺🇦 Шо треба, москалю?")

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    uid = message.from_user.id
    user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await message.answer("Все, я тебе забув. Пиши знову, але тільки на мові!")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return
        
    uid = message.from_user.id
    if uid not in user_histories:
        user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    user_text = message.text
    user_histories[uid].append({"role": "user", "content": user_text})
    
    if len(user_histories[uid]) > 11:
        user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-10:]

    chosen_model = choose_model(user_text)
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = await client.chat.completions.create(
            model=chosen_model,
            messages=user_histories[uid],
            temperature=0.9, # Максимальная неадекватность и вариативность
            max_tokens=100,  # Ограничение длины сообщения (примерно 1-2 предложения)
            tools=[{"type": "web_search"}],
            tool_choice="auto",
        )
        
        reply = response.choices[0].message.content
        user_histories[uid].append({"role": "assistant", "content": reply})
        
        # Отправляем текст
        await message.answer(reply)
        
        # С вероятностью 20% бот дополнительно кидает картинку
        if random.random() < 0.2:
            img_url = random.choice(IMAGES)
            await message.answer_photo(photo=img_url)
            
    except Exception as e:
        logger.error(f"Ошибка API PlusVibe: {e}")
        await message.answer("Відчепись, не до тебе!")

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
