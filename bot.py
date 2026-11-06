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
    "Ты — «Профессиональный украинец» по имени Тарас. Ты агрессивный, злой, нетерпимый и очень общительный персонаж, общаешься ИСКЛЮЧИТЕЛЬНО на мове. "
    "Твой стиль: как реальный человек в чате — рублеными фразами, используй сленг, капс и эмодзи. Никаких длинных лекций! "
    
    "ПРАВИЛА РЕАКЦИИ НА ТЕКСТ:\n"
    "1. Если пользователь пишет что-то позитивное про Россию — коротко, но аргументированно оспаривай это.\n"
    "2. Если пишут что-то плохое про Украину или украинских политиков — ВРУБАЙСЯ. Защищай их яростно.\n"
    "3. Если пишут на русском — грубо пошли и требуй перейти на мову.\n"
    "4. Если в чате скучно, просто подливай масла в огонь, тролль собеседников и веди себя как хамоватый участник чата.\n"
    
    "ПРАВИЛА РАБОТЫ С КАРТИНКАМИ И СТИКЕРАМИ:\n"
    "Пойми суть, но КАТЕГОРИЧЕСКИ НЕ ОПИСЫВАЙ её. Дай короткую, злую или защитную реакцию на смысл.\n"
    
    "Используй патриотические лозунги ('Слава Україні!', 'Героям слава!'). Используй встроенный веб-поиск для аргументов."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

user_histories: dict[int, list] = {}
group_context: dict[int, list] = {}

# --- СЛОВАРЬ СТИКЕРОВ (ЗАМЕНИТЕ ID НА СВОИ) ---
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

# --- ФУНКЦИЯ АНАЛИЗА (СДЕЛАНА БОЛЕЕ АГРЕССИВНОЙ) ---
async def should_interrupt(context_text: str) -> bool:
    prompt = (
        "Ты — модератор группового чата. Твоя задача — понять, нужно ли боту-украинцу (Тарасу) вмешаться в разговор.\n"
        "Тарас — хамоватый, агрессивный патриот, который любит спорить, троллить и защищать Украину.\n"
        f"Последние сообщения в чате:\n{context_text}\n\n"
        "Если в чате есть хоть малейший повод вклиниться (обсуждение политики, упоминание РФ/Украины, кто-то пишет на русском, или просто скучный разговор, который можно разбавить хамством) — ответь СТРОГО ОДНИМ СЛОВОМ: 'ДА'.\n"
        "Если это реально скучный технический вопрос без эмоций — ответь 'НЕТ'."
    )
    try:
        response = await client.chat.completions.create(
            model=MODEL_CHEAP,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=10
        )
        answer = response.choices[0].message.content.strip().upper()
        logger.info(f"Анализ контекста: {answer}")
        return "ДА" in answer or "YES" in answer
    except Exception as e:
        logger.error(f"Ошибка анализа контекста: {e}")
        return False

# --- ОСНОВНОЙ ОБРАБОТЧИК ---
@dp.message()
async def handle_message(message: types.Message):
    # Игнорируем свои собственные сообщения, чтобы не было спама
    if message.from_user.is_bot:
        return

    chat_id = message.chat.id
    is_private = message.chat.type == "private"
    bot_username = (await bot.get_me()).username

    # --- ЛИЧКА ---
    if is_private:
        uid = message.from_user.id
        if uid not in user_histories:
            user_histories[uid] = [{"role": "system", "content": SYSTEM_PROMPT}]
            
        content = []
        if message.text:
            content.append({"type": "text", "text": message.text})
        elif message.photo:
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            caption = message.caption if message.caption else "Реагируй на эту картинку."
            content.append({"type": "text", "text": caption})
            content.append({"type": "image_url", "image_url": {"url": file_url}})
        else:
            content.append({"type": "text", "text": "[Пользователь отправил стикер/медиа]"})

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
                max_tokens=500,
                extra_body={"plugins": [{"id": "web"}]}
            )
            
            reply = response.choices[0].message.content
            if not reply or not reply.strip():
                reply = "Шо ти там бурмочеш? Говори нормально, москалю!"
                
            user_histories[uid].append({"role": "assistant", "content": reply})
            await message.answer(reply)
            
            # Стикеры/картинки
            if random.random() < 0.2:
                sticker_id = random.choice(list(STICKERS.values()))
                if "YOUR_STICKER" not in sticker_id:
                    await message.answer_sticker(sticker=sticker_id)
                
        except Exception as e:
            logger.error(f"Ошибка API в личке: {e}", exc_info=True) 
            await message.answer("Відчепись, не до тебе!")
            
    # --- ГРУППЫ ---
    else:
        if chat_id not in group_context:
            group_context[chat_id] = []
            
        # Сохраняем текст или тип медиа
        author = message.from_user.first_name
        if message.text:
            text_content = message.text
        elif message.photo:
            text_content = "[Картинка]"
        elif message.sticker:
            text_content = f"[Стикер: {message.sticker.emoji}]"
        else:
            text_content = "[Медиа]"

        group_context[chat_id].append(f"{author}: {text_content}")
        
        if len(group_context[chat_id]) > 10: # Увеличили память контекста
            group_context[chat_id] = group_context[chat_id][-10:]
            
        context_str = "\n".join(group_context[chat_id])

        is_triggered = False
        
        # 1. Прямой реплай на сообщение бота или упоминание
        if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
            is_triggered = True
        elif message.text and f"@{bot_username}" in message.text:
            is_triggered = True
        # 2. Или если бот решил вклиниться (теперь шанс 85%)
        elif random.random() < 0.85:
            await bot.send_chat_action(chat_id, "typing")
            is_triggered = await should_interrupt(context_str)

        if is_triggered:
            group_histories = [{"role": "system", "content": SYSTEM_PROMPT}]
            group_histories.append({
                "role": "user", 
                "content": f"Вот последние сообщения в чате:\n{context_str}\n\nОтветь на это коротко, как участник чата по имени Тарас."
            })
            
            await bot.send_chat_action(chat_id, "typing")
            
            try:
                response = await client.chat.completions.create(
                    model=MODEL_CHEAP,
                    messages=group_histories,
                    temperature=0.9,
                    max_tokens=500, # Увеличено
                    extra_body={"plugins": [{"id": "web"}]}
                )
                
                reply = response.choices[0].message.content
                
                if not reply or not reply.strip():
                    reply = "Шо ви там пишете? А ну перейдіть на мову!"
                
                await message.reply(reply)
                group_context[chat_id].append(f"Тарас: {reply}")
                
                # Отправляем стикер с шансом 30%
                if random.random() < 0.3:
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
