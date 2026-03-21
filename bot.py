import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from os import getenv
from dotenv import load_dotenv
from aiogram.filters import Command
from groq import Groq

load_dotenv()

BOT_TOKEN = getenv("BOT_TOKEN")
GROQ_API_KEY = getenv("GROQ_API_KEY")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет! Я тестовый бот. Пока умею только отвечать на /start.")

@dp.message(F.text)
async def ai_reply(message: Message):
    text = message.text.strip() if message.text else ""

    # Исключаем команды /start, /help и любые другие команды
    if not text or text.startswith("/"):
        return

    user_id = message.from_user.id
    if user_id not in chat_histories:
        chat_histories[user_id] = []

    system_prompt = "Ты консультант барбершопа «Чёрный кот» в Ярославле. Услуги: стрижка 800р, борода 500р, комплекс 1200р. Запись по кнопке ниже или по номеру +7 999 123-45-67. Режим работы: ежедневно 10:00-21:00. Отвечай дружелюбно и кратко. Если вопрос не по теме — вежливо скажи что ты консультант барбершопа."
    try:
        # Собираем историю сообщений
        messages = [{"role": "system", "content": system_prompt}] + chat_histories[user_id] + [{"role": "user", "content": text}]

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # можно изменить на предпочитаемую модель
            messages=messages,
            max_completion_tokens=256,
            temperature=0.3,
        )

        answer = ""
        if getattr(completion, "choices", None):
            choice = completion.choices[0]
            message_obj = getattr(choice, "message", None)
            if message_obj is not None:
                answer = getattr(message_obj, "content", "") or ""

        if not answer:
            answer = "Извините, не удалось получить ответ от Groq."

        # Добавляем в историю
        chat_histories[user_id].append({"role": "user", "content": text})
        chat_histories[user_id].append({"role": "assistant", "content": answer})
        chat_histories[user_id] = chat_histories[user_id][-10:]

        await message.answer(answer)
    except Exception as e:
        await message.answer(f"Ошибка при запросе к Groq: {e}")

async def main():

    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())