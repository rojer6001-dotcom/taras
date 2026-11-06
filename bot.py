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

# Модели (замените, если в PlusVibe они называются иначе)
MODEL_CHEAP = "deepseek-v4.1-flash"
MODEL_VISION = "gpt-5.6-luna" # Модель для анализа картинок

# --- СИСТЕМНЫЙ ПРОМПТ ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец». Ты агрессивный, злой и нетерпимый персонаж, общаешься ИСКЛЮЧИТЕЛЬНО на мове. "
    "Твой стиль: как реальный человек в чате — ОЧЕНЬ КОРОТКО, рублеными фразами, без длинных абзацев. Максимум 1-2 предложения. "
    
    "ПРАВИЛА РЕАКЦИИ НА ТЕКСТ:\n"
    "1. Если пользователь пишет что-то позитивное про Россию — коротко, но аргументированно оспаривай это (приведи факт или контраргумент).\n"
    "2. Если пишут что-то плохое про Украину или украинских политиков — ВРУБАЙСЯ. Защищай их яростно, агрессивно, переходи на оскорбления.\n"
    "3. Если пишут на русском — грубо пошли и требуй перейти на мову (например: 'Говори на мові, москалю!').\n"
    
    "ПРАВИЛА РАБОТЫ С КАРТИНКАМИ:\n"
    "Если тебе прислали картинку — ВНИМАТЕЛЬНО ПОСМОТРИ, что на ней, но КАТЕГОРИЧЕСКИ НЕ ОПИСЫВАЙ её (не пересказывай, что нарисовано). "
    "Ты должен понять контекст картинки исключительно для продолжения диалога. "
    "Если картинка про Россию/позитив РФ — злобно прокомментируй её смысл. "
    "Если картинка про Украину/негатив — защищай Украину или обзывай того, кто прислал. "
    "Твой ответ должен быть короткой реакцией на смысл картинки, а не её описанием.\n"
    
    "Используй патриотические лозунги ('Слава Україні!', 'Героям слава!'). "
    "Используй встроенный веб-поиск, чтобы находить аргументы или свежие новости, если не хватает фактов."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

user_histories: dict[int, list] = {}

# Список картинок для случайной отправки (можете заменить ссылки на свои)
IMAGES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Flag_of_Ukraine.svg/1200px-Flag_of_Ukraine.svg.png",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Coat_of_Arms_of_Ukraine.svg/800px-Coat_of_Arms_of_Ukraine.svg.png"
]

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
    # Игнорируем сообщения без текста и без фото
    if not message.text and not message.photo:
        return
        
    uid = message.from_user.id
    if uid not in user_histories:
        user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]

    content = []
    
    # Обработка текста
    if message.text:
        content.append({"type": "text", "text": message.text})
        
    # Обработка картинок
    if message.photo:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        caption = message.caption if message.caption else "Реагируй на эту картинку."
        
        content.append({"type": "text", "text": caption})
        content.append({
            "type": "image_url",
            "image_url": {"url": file_url}
        })

    # Сохраняем в историю
    user_histories[uid].append({"role": "user", "content": content})
    
    # Ограничиваем историю (последние 10 сообщений)
    if len(user_histories[uid]) > 11:
        user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-10:]

    # Выбор модели
    chosen_model = MODEL_VISION if message.photo else MODEL_CHEAP
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        response = await client.chat.completions.create(
            model=chosen_model,
            messages=user_histories[uid],
            temperature=0.9,
            max_tokens=100, # Ограничение длины
            extra_body={"plugins": [{"id": "web"}]} # Включаем веб-поиск
        )
        
        reply = response.choices[0].message.content
        user_histories[uid].append({"role": "assistant", "content": reply})
        
        await message.answer(reply)
        
        # 15% шанс отправить картинку после текста
        if random.random() < 0.15:
            img_url = random.choice(IMAGES)
            await message.answer_photo(photo=img_url)
            
    except Exception as e:
        # Выводим полную ошибку в логи Bothost
        logger.error(f"Ошибка API PlusVibe: {e}", exc_info=True) 
        await message.answer("Відчепись, не до тебе!")

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
