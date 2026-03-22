import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from os import getenv
from dotenv import load_dotenv
from aiogram.filters import Command
from groq import Groq
import csv
import os


load_dotenv()

BOT_TOKEN = getenv("BOT_TOKEN")
GROQ_API_KEY = getenv("GROQ_API_KEY")
ADMIN_ID = int(getenv("ADMIN_ID"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

BOOKINGS_FILE = "bookings.csv"

def save_booking(name, service, date, time, user_id):
    file_exists = os.path.exists(BOOKINGS_FILE)
    with open(BOOKINGS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Имя", "Услуга", "Дата", "Время", "User ID"])
        writer.writerow([name, service, date, time, user_id])


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()

@dp.message(Command("start"))
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✂️ Записаться", callback_data="book")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="prices")],
        [InlineKeyboardButton(text="📍 Адрес", callback_data="address")],
    ])

    await message.answer(
        "Добро пожаловать в барбершоп «Чёрный кот»! Я помогу выбрать услугу и записаться.",
        reply_markup=keyboard,
    )

@dp.callback_query(lambda call: call.data == "book")
async def on_book(call: CallbackQuery, state: FSMContext):
    await call.answer("Запускаем процесс записи")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✂️ Мужская стрижка (800₽)", callback_data="service_haircut")],
        [InlineKeyboardButton(text="🧔 Коррекция бороды (500₽)", callback_data="service_beard")],
        [InlineKeyboardButton(text="💈 Комплекс (1200₽)", callback_data="service_complex")],
    ])
    
    await call.message.answer("Выберите услугу:", reply_markup=keyboard)
    await state.set_state(BookingStates.choosing_service)

@dp.callback_query(F.data.in_({"service_haircut", "service_beard", "service_complex"}))
async def on_service_selected(call: CallbackQuery, state: FSMContext):
    service_map = {
        "service_haircut": "Мужская стрижка (800₽)",
        "service_beard": "Коррекция бороды (500₽)",
        "service_complex": "Комплекс (1200₽)",
    }
    
    service_name = service_map.get(call.data, "Услуга")
    await state.update_data(service=call.data)
    await call.answer(f"Вы выбрали: {service_name}")
    await call.message.answer("Введите удобную дату в формате ДД.ММ.ГГГГ (например, 25.03.2026):")
    await state.set_state(BookingStates.choosing_date)

@dp.callback_query(lambda call: call.data == "prices")
async def on_prices(call: CallbackQuery):
    await call.answer("Узнаём цены")
    await call.message.answer(
        "Наши цены:\n✂️ Мужская стрижка — 800₽\n🧔 Коррекция бороды — 500₽\n💈 Комплекс (стрижка + борода) — 1200₽",
    )

@dp.callback_query(lambda call: call.data == "address")
async def on_address(call: CallbackQuery):
    await call.answer("Смотрим адрес")
    await call.message.answer(
        "Мы находимся в Ярославле, ул. Советская, 12. Работаем ежедневно с 10:00 до 21:00.\n📞 +7 999 123-45-67",
    )

@dp.message(BookingStates.choosing_date)
async def on_date_entered(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("Спасибо! Введите удобное время в формате ЧЧ:МИ (например, 14:30):")
    await state.set_state(BookingStates.choosing_time)

@dp.message(BookingStates.choosing_time)
async def on_time_entered(message: Message, state: FSMContext):
    await state.update_data(time=message.text)
    await message.answer("Введите ваше имя:")
    await state.set_state(BookingStates.entering_name)

@dp.message(BookingStates.entering_name)
async def on_name_entered(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    data = await state.get_data()
    
    service_map = {
        "service_haircut": "✂️ Мужская стрижка (800₽)",
        "service_beard": "🧔 Коррекция бороды (500₽)",
        "service_complex": "💈 Комплекс (1200₽)",
    }
    
    service_name = service_map.get(data.get("service"), "Услуга")
    date = data.get("date", "—")
    time = data.get("time", "—")
    name = message.text
    
    confirmation = f"""
✅ Ваша запись подтверждена!

Услуга: {service_name}
Дата: {date}
Время: {time}
Имя: {name}

Спасибо за выбор! Ждём вас в барбершопе «Чёрный кот»
Если вам нужно изменить запись, звоните: +7 999 123-45-67
    """
    
    # Сохраняем запись в CSV
    save_booking(name, service_name, date, time, message.from_user.id)
    
    # Отправляем уведомление администратору
    await bot.send_message(ADMIN_ID, f"📋 Новая запись!\n\nИмя: {name}\nУслуга: {service_name}\nДата: {date}\nВремя: {time}\nTelegram ID: {message.from_user.id}")
    
    await message.answer(confirmation)
    await state.clear()

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