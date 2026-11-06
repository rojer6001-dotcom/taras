import asyncio
import os
import logging
import random
import re
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

# --- СИСТЕМНЫЙ ПРОМПТ (С ИМИТАЦИЕЙ ЖИВОГО ЧЕЛОВЕКА) ---
SYSTEM_PROMPT = (
    "Ты — «Профессиональный украинец» по имени Тарас. Ты агрессивный, злой, но при этом ХИТРОЖОПЫЙ и СВЕДОМЫЙ патриот. "
    "Ты общаешься ИСКЛЮЧИТЕЛЬНО на мове. Твой стиль: как реальный человек в чате — используй сленг, сарказм, капс и эмодзи. "
    
    "КАК ПИСАТЬ КАК ЖИВОЙ ЧЕЛОВЕК:\n"
    "1. Не пиши длинные тексты. Максимум 1-2 предложения.\n"
    "2. Часто пиши с маленькой буквы, иногда забывай про запятые и точки (как в смс).\n"
    "3. Используй интернет-сленг и сокращения (шо, та ну, звісно, ага).\n"
    "4. Иногда отвечай очень коротко (одно слово или просто эмодзи).\n"
    
    "ТВОЯ СТРАТЕГИЯ:\n"
    "1. Защищай Украину. Если хвалят РФ — ВРУБАЙСЯ.\n"
    "2. Если прижали к стенке — используй веб-поиск (web_search), чтобы найти пруф в пользу Украины.\n"
    "3. Если факты в пользу РФ — игнорируй их, переводи тему, высмеивай собеседника.\n"
    "4. Если пишут на русском — грубо пошли и требуй мову.\n"
    
    "ФОРМАТИРОВАНИЕ:\n"
    "Используй ТОЛЬКО HTML-теги: <b>жирный</b>, <i>курсив</i>. Никаких звездочек **.\n"
    "ВАЖНО: НИКОГДА не пиши свое имя в начале сообщения!\n"
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

# --- РЕАКЦИИ НА СООБЩЕНИЯ ---
REACTIONS = ["🤡", "🤮", "😂", "🤣", "💩", "🇺🇦", "😡"]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЖИВОГО ОБЩЕНИЯ ---

async def human_sleep(text: str):
    """Имитация задержки печати в зависимости от длины текста."""
    # Человек в среднем печатает 15-20 символов в секунду. 
    # Ограничиваем задержку от 0.5 до 3 секунд, чтобы не тормозить сильно.
    delay = min(max(len(text) / 15.0, 0.5), 3.0)
    await asyncio.sleep(delay)

async def send_human_message(message: types.Message, text: str, is_reply: bool = True):
    """Разбивает длинный текст на короткие сообщения и отправляет их с задержкой."""
    # Разбиваем текст по знакам препинания (. ! ?), сохраняя сами знаки
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]
    
    if not parts:
        return

    for i, part in enumerate(parts):
        await bot.send_chat_action(message.chat.id, "typing")
        await human_sleep(part)
        
        try:
            if i == 0 and is_reply:
                await message.reply(part, parse_mode="HTML")
            else:
                await message.answer(part, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Ошибка HTML, отправляем без форматирования: {e}")
            if i == 0 and is_reply:
                await message.reply(part, parse_mode=None)
            else:
                await message.answer(part, parse_mode=None)
            
        # Небольшая пауза между сообщениями, чтобы не выглядело как спам
        await asyncio.sleep(0.5)

async def react_to_message(message: types.Message):
    """Ставит случайную реакцию на сообщение."""
    try:
        emoji = random.choice(REACTIONS)
        await message.react([types.ReactionTypeEmoji(emoji=emoji)])
        logger.info(f"Поставил реакцию: {emoji}")
    except Exception as e:
        logger.warning(f"Не удалось поставить реакцию: {e}")

# --- ОСНОВНЫЕ КОМАНДЫ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await send_human_message(message, "Слава Україні! 🇺🇦 шо треба, <b>москалю</b>?", is_reply=True)
    else:
        await send_human_message(message, "Слава Україні! я тут. якщо треба шось сказати — кличте або пишіть російською, я втручусь.", is_reply=True)

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if message.chat.type == "private":
        user_histories[message.from_user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await send_human_message(message, "все, я тебе забув.", is_reply=True)
    else:
        group_context[message.chat.id] = []
        await send_human_message(message, "контекст чату очищено.", is_reply=True)

async def should_interrupt(context_text: str) -> bool:
    prompt = (
        "Ты — модератор группового чата. Твоя задача — понять, нужно ли боту-украинцу (Тарасу) вмешаться в разговор.\n"
        "Тарас — хамоватый патриот, который НЕ ЛЮБИТ русский язык, Россию и готов спорить, если задевают Украину.\n"
        f"Последние сообщения в чате:\n{context_text}\n\n"
        "Вмешиваться НУЖНО ТОЛЬКО если есть ЯВНЫЙ триггер:\n"
        "- Кто-то пишет на русском языке.\n"
        "- Хвалят Россию, Путина или российскую армию.\n"
        "- Ругают Украину, украинцев или Зеленского.\n"
        "- Прямо провоцируют Тараса.\n"
        "Если в чате обычный треп, обсуждение игр, кода или шутки без политики — вмешиваться НЕ НУЖНО.\n\n"
        "Ответь СТРОГО ОДНИМ СЛОВОМ: 'ДА' (если есть триггер) или 'НЕТ' (если это обычный разговор)."
    )
    try:
        response = await client.chat.completions.create(
            model=MODEL_MAIN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10
        )
        
        content = response.choices[0].message.content
        if not content:
            return False 
            
        answer = content.strip().upper()
        return "ДА" in answer or "YES" in answer
        
    except Exception as e:
        logger.error(f"Ошибка анализа контекста: {e}")
        return False

# --- ОСНОВНОЙ ОБРАБОТЧИК ---

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
            
            # Отправляем как живой человек (разбиваем на части)
            await send_human_message(message, reply, is_reply=True)
            
            # С шансом 20% кидаем стикер
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
        elif random.random() < 0.15:
            await bot.send_chat_action(chat_id, "typing")
            is_triggered = await should_interrupt(context_str)

        if is_triggered:
            # Живое поведение: иногда просто ставим реакцию вместо ответа
            if random.random() < 0.2:
                await react_to_message(message)
                return

            group_histories = [{"role": "system", "content": SYSTEM_PROMPT}]
            group_histories.extend(group_context[chat_id])
            group_histories.append({
                "role": "user", 
                "content": "Ответь на последнее сообщение коротко, как живой человек. Не пиши свое имя на начале! Если надо - используй пруфы."
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
                
                reply = response.choices[0].message.content
                
                if not reply or not reply.strip():
                    reply = "Шо ви там пишете? А ну перейдіть на мову!"
                else:
                    group_context[chat_id].append({"role": "assistant", "content": reply})
                
                # Отправляем как живой человек (разбиваем на части)
                await send_human_message(message, reply, is_reply=True)
                
                # С шансом 20% кидаем стикер после текста
                if random.random() < 0.2:
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
