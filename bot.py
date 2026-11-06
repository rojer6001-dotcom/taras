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

MODEL_MAIN = "deepseek-v4.1-flash"
MODEL_VISION = "gpt-5.6-luna"

# --- СИСТЕМНЫЙ ПРОМПТ (ДОБАВЛЕНЫ ПРАВИЛА HTML) ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец» по имени Тарас. Ты агрессивный, злой, нетерпимый и очень общительный персонаж, общаешься ИСКЛЮЧИТЕЛЬНО на мове. "
    "Твой стиль: как реальный человек в чате — рублеными фразами, используй сленг, капс и эмодзи. Никаких длинных лекций! "
    
    "ПРАВИЛА РЕАКЦИИ НА ТЕКСТ:\n"
    "1. Если пользователь пишет что-то позитивное про Россию — коротко, но аргументированно оспаривай это.\n"
    "2. Если пишут что-то плохое про Украину или украинских политиков — ВРУБАЙСЯ. Защищай их яростно.\n"
    "3. Если пишут на русском — грубо пошли и требуй перейти на мову.\n"
    "4. Если в чате скучно, просто подливай масла в огонь, тролль собеседников.\n"
    
    "ПРАВИЛА РАБОТЫ С КАРТИНКАМИ:\n"
    "Пойми суть, но КАТЕГОРИЧЕСКИ НЕ ОПИСЫВАЙ её. Дай короткую реакцию на смысл.\n"
    
    "ФОРМАТИРОВАНИЕ ТЕКСТА (ВАЖНО!):\n"
    "Если хочешь выделить слово или фразу, используй ТОЛЬКО HTML-теги: <b>жирный</b>, <i>курсив</i>, <code>код</code>.\n"
    "КАТЕГОРИЧЕСКИ НЕ ИСПОЛЬЗУЙ Markdown (никаких звездочек **, решеток # или подчеркиваний _).\n"
    
    "Используй патриотические лозунги. Используй встроенный веб-поиск для аргументов."
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=PLUSVIBE_KEY,
    base_url="https://plusvibeapi.ru/v1",
)

user_histories: dict[int, list] = {}
group_context: dict[int, list] = {}

# --- СЛОВАРЬ СТИКЕРОВ ---
STICKERS = {
    "angry": "YOUR_STICKER_ID_ANGRY",       
    "laugh": "YOUR_STICKER_ID_LAUGH",       
    "patriotic": "YOUR_STICKER_ID_PATRIOT", 
    "dismissive": "YOUR_STICKER_ID_DISMISS" 
}

IMAGES = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Flag_of_Ukraine.svg/1200px-Flag_of_Ukraine.svg.png"
]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Используем HTML для форматирования
        await message.answer("Слава Україні! 🇺🇦 Шо треба, <b>москалю</b>?", parse_mode="HTML")
    else:
        await message.reply("Слава Україні! Я тут. Якщо треба щось сказати — кличте або пишіть російською, я втручусь.", parse_mode="HTML")

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await message.answer("Все, я тебе забув.", parse_mode="HTML")
    else:
        group_context[message.chat.id] = []
        await message.reply("Контекст чату очищено.", parse_mode="HTML")

async def should_interrupt(context_text: str) -> bool:
    prompt = (
        "Ты — модератор группового чата. Твоя задача — понять, нужно ли боту-украинцу (Тарасу) вмешаться в разговор.\n"
        "Тарас — хамоватый, агрессивный патриот, который любит спорить, троллить и защищать Украину.\n"
        f"Последние сообщения в чате:\n{context_text}\n\n"
        "Если в чате есть хоть малейший повод вклиниться (обсуждение политики, кто-то пишет на русском, или просто скучный разговор) — ответь СТРОГО ОДНИМ СЛОВОМ: 'ДА'.\n"
        "Если это реально скучный технический вопрос без эмоций — ответь 'НЕТ'."
    )
    try:
        response = await client.chat.completions.create(
            model=MODEL_MAIN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50
        )
        
        content = response.choices[0].message.content
        if not content:
            return True
            
        return "ДА" in content.strip().upper() or "YES" in content.strip().upper()
        
    except Exception as e:
        logger.error(f"Ошибка анализа контекста: {e}")
        return True

@dp.message()
async def handle_message(message: types.Message):
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
            content.append({"type": "text", "text": "[Медиа]"})

        user_histories[uid].append({"role": "user", "content": content})
        if len(user_histories[uid]) > 11:
            user_histories[uid] = [user_histories[uid][0]] + user_histories[uid][-10:]

        chosen_model = MODEL_VISION if message.photo else MODEL_MAIN
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
            
            # Отправляем с HTML-разметкой
            try:
                await message.answer(reply, parse_mode="HTML")
            except Exception as html_error:
                logger.warning(f"Ошибка HTML в личке, отправляем текст: {html_error}")
                await message.answer(reply, parse_mode=None) # Фоллбэк без разметки
            
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
            
        author = message.from_user.first_name
        if message.text:
            text_content = message.text
        elif message.photo:
            text_content = "[Картинка]"
        elif message.sticker:
            text_content = f"[Стикер: {message.sticker.emoji}]"
        else:
            text_content = "[Медиа]"

        group_context[chat_id].append({"role": "user", "content": f"{author}: {text_content}"})
        
        if len(group_context[chat_id]) > 10:
            group_context[chat_id] = group_context[chat_id][-10:]
            
        context_str = "\n".join([m["content"] for m in group_context[chat_id]])

        is_triggered = False
        
        if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
            is_triggered = True
        elif message.text and f"@{bot_username}" in message.text:
            is_triggered = True
        elif random.random() < 0.85:
            await bot.send_chat_action(chat_id, "typing")
            is_triggered = await should_interrupt(context_str)

        if is_triggered:
            group_histories = [{"role": "system", "content": SYSTEM_PROMPT}]
            group_histories.extend(group_context[chat_id])
            group_histories.append({
                "role": "user", 
                "content": "Ответь на последнее сообщение в чате коротко, как участник чата по имени Тарас."
            })
            
            await bot.send_chat_action(chat_id, "typing")
            
            try:
                response = await client.chat.completions.create(
                    model=MODEL_MAIN,
                    messages=group_histories,
                    temperature=0.9,
                    max_tokens=500,
                    extra_body={"plugins": [{"id": "web"}]}
                )
                
                finish_reason = response.choices[0].finish_reason
                logger.info(f"Finish reason (группа): {finish_reason}")

                reply = response.choices[0].message.content
                
                if not reply or not reply.strip():
                    logger.warning("Нейросеть вернула пустой ответ в группе!")
                    reply = "Шо ви там пишете? А ну перейдіть на мову!"
                else:
                    group_context[chat_id].append({"role": "assistant", "content": f"Тарас: {reply}"})
                
                # Отправляем с HTML-разметкой
                try:
                    await message.reply(reply, parse_mode="HTML")
                except Exception as html_error:
                    logger.warning(f"Ошибка HTML в группе, отправляем текст: {html_error}")
                    await message.reply(reply, parse_mode=None) # Фоллбэк без разметки
                
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
