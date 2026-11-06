import asyncio
import os
import logging
import random
from aiogram import Bot, Dispatcher, types, F
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
MODEL_VISION = "gpt-5.6-luna"

# --- СИСТЕМНЫЙ ПРОМПТ ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец». Ты агрессивный, злой и нетерпимый персонаж, общаешься ИСКЛЮЧИТЕЛЬНО на мове. "
    "Твой стиль: как реальный человек в чате — ОЧЕНЬ КОРОТКО, рублеными фразами, без длинных абзацев. Максимум 1-2 предложения. "
    
    "ПРАВИЛА РЕАКЦИИ НА ТЕКСТ:\n"
    "1. Если пользователь пишет что-то позитивное про Россию — коротко, но аргументированно оспаривай это.\n"
    "2. Если пишут что-то плохое про Украину или украинских политиков — ВРУБАЙСЯ. Защищай их яростно.\n"
    "3. Если пишут на русском — грубо пошли и требуй перейти на мову.\n"
    
    "ПРАВИЛА РАБОТЫ С КАРТИНКАМИ:\n"
    "Если тебе прислали картинку — пойми её суть, но КАТЕГОРИЧЕСКИ НЕ ОПИСЫВАЙ её. Просто дай короткую, злую или защитную реакцию на смысл.\n"
    
    "Используй патриотические лозунги ('Слава Україні!', 'Героям слава!'). "
    "Используй встроенный веб-поиск для аргументов."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

# Хранилище личных диалогов и контекста групп
user_histories: dict[int, list] = {}
group_context: dict[int, list] = {}

# --- СЛОВАРЬ СТИКЕРОВ (ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ ID НА СВОИ) ---
STICKERS = {
    "angry": "YOUR_STICKER_ID_ANGRY",       
    "laugh": "YOUR_STICKER_ID_LAUGH",       
    "patriotic": "YOUR_STICKER_ID_PATRIOT", 
    "dismissive": "YOUR_STICKER_ID_DISMISS" 
}

IMAGES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Flag_of_Ukraine.svg/1200px-Flag_of_Ukraine.svg.png",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Coat_of_Arms_of_Ukraine.svg/800px-Coat_of_Arms_of_Ukraine.svg.png"
]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await message.answer("Слава Україні! 🇺🇦 Шо треба, москалю?")
    else:
        await message.reply("Слава Україні! Я тут. Якщо треба щось сказати — кличте або пишіть російською, я втручусь.")

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await message.answer("Все, я тебе забув.")
    else:
        group_context[message.chat.id] = []
        await message.reply("Контекст чату очищено.")

# --- ФУНКЦИЯ АНАЛИЗА: СТОИТ ЛИ ВМЕШИВАТЬСЯ? ---
async def should_interrupt(context_text: str) -> bool:
    prompt = (
        "Ты — модератор чата. Твоя задача — понять, нужно ли боту-украинцу вмешаться в разговор.\n"
        "Бот ненавидит русский язык, Россию и любит защищать Украину.\n"
        f"Последние сообщения в чате:\n{context_text}\n\n"
        "Ответь СТРОГО ОДНИМ СЛОВОМ: 'ДА' (если в чате пишут на русском, хвалят РФ или ругают Украину) "
        "или 'НЕТ' (если это обычный треп)."
    )
    try:
        response = await client.chat.completions.create(
            model=MODEL_CHEAP,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10
        )
        answer = response.choices[0].message.content.strip().upper()
        return "ДА" in answer or "YES" in answer
    except Exception as e:
        logger.error(f"Ошибка анализа контекста: {e}")
        return False

# --- ОСНОВНОЙ ОБРАБОТЧИК (ТЕКСТ И КАРТИНКИ) ---
@dp.message(F.text | F.photo)
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    is_private = message.chat.type == "private"
    bot_username = (await bot.get_me()).username

    # --- ЛОГИКА ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ---
    if is_private:
        uid = message.from_user.id
        if uid not in user_histories:
            user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
            
        content = []
        if message.text:
            content.append({"type": "text", "text": message.text})
        if message.photo:
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            caption = message.caption if message.caption else "Реагируй на эту картинку."
            content.append({"type": "text", "text": caption})
            content.append({"type": "image_url", "image_url": {"url": file_url}})

        user_histories[uid].append({"role": "user", "content": content})
        if len(user_histories[uid]) > 11:
            user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-10:]

        chosen_model = MODEL_VISION if message.photo else MODEL_CHEAP
        await bot.send_chat_action(chat_id, "typing")
        
        try:
            response = await client.chat.completions.create(
                model=chosen_model,
                messages=user_histories[uid],
                temperature=0.9,
                max_tokens=500, # Увеличено, чтобы модель не выдавала пустоту
                extra_body={"plugins": [{"id": "web"}]}
            )
            
            # Логируем причину завершения ответа (stop, length, content_filter)
            finish_reason = response.choices[0].finish_reason
            logger.info(f"Finish reason (личка): {finish_reason}")

            reply = response.choices[0].message.content
            
            # Защита от пустого ответа
            if not reply or not reply.strip():
                reply = "Шо ти там бурмочеш? Говори нормально, москалю!"
                
            user_histories[uid].append({"role": "assistant", "content": reply})
            await message.answer(reply)
            
            # Отправка стикера или картинки
            rand_val = random.random()
            if rand_val < 0.15:
                sticker_id = random.choice(list(STICKERS.values()))
                if "YOUR_STICKER" not in sticker_id:
                    await message.answer_sticker(sticker=sticker_id)
            elif rand_val < 0.30:
                await message.answer_photo(photo=random.choice(IMAGES))
                
        except Exception as e:
            logger.error(f"Ошибка API в личке: {e}", exc_info=True) 
            await message.answer("Відчепись, не до тебе!")
            
    # --- ЛОГИКА ДЛЯ ГРУПП ---
    else:
        if chat_id not in group_context:
            group_context[chat_id] = []
            
        author = message.from_user.first_name
        text_content = message.text if message.text else "[Картинка]"
        group_context[chat_id].append(f"{author}: {text_content}")
        
        if len(group_context[chat_id]) > 7:
            group_context[chat_id] = group_context[chat_id][-7:]
            
        context_str = "\n".join(group_context[chat_id])

        is_triggered = False
        
        if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
            is_triggered = True
        elif message.text and f"@{bot_username}" in message.text:
            is_triggered = True
        elif random.random() < 0.4:
            await bot.send_chat_action(chat_id, "typing")
            is_triggered = await should_interrupt(context_str)

        if is_triggered:
            group_histories = [{"role": "system", "content": SYSTEM_PROMPT}]
            group_histories.append({
                "role": "user", 
                "content": f"Вот последние сообщения в чате:\n{context_str}\n\nОтветь на это коротко, как участник чата."
            })
            
            await bot.send_chat_action(chat_id, "typing")
            
            try:
                response = await client.chat.completions.create(
                    model=MODEL_CHEAP,
                    messages=group_histories,
                    temperature=0.9,
                    max_tokens=500, # Увеличено для групп
                    extra_body={"plugins": [{"id": "web"}]}
                )
                
                # Логируем причину завершения
                finish_reason = response.choices[0].finish_reason
                logger.info(f"Finish reason (группа): {finish_reason}")

                reply = response.choices[0].message.content
                
                # Защита от пустого ответа
                if not reply or not reply.strip():
                    reply = "Шо ви там пишете? А ну перейдіть на мову!"
                
                await message.reply(reply)
                group_context[chat_id].append(f"Бот: {reply}")
                
                if random.random() < 0.25:
                    sticker_id = random.choice(list(STICKERS.values()))
                    if "YOUR_STICKER" not in sticker_id:
                        await message.answer_sticker(sticker=sticker_id)
                    
            except Exception as e:
                logger.error(f"Ошибка API в группе: {e}", exc_info=True)

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
