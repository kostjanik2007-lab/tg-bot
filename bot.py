import asyncio
from aiogram import Bot, Dispatcher
from os import getenv
from dotenv import load_dotenv
from aiogram.filters import Command

load_dotenv()

BOT_TOKEN = getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message):
    await message.answer("Привет! Я тестовый бот. Пока умею только отвечать на /start.")

async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())