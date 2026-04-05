import asyncio
import json
from datetime import date, timedelta
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
import gspread
from google.oauth2.service_account import Credentials


load_dotenv()

GOOGLE_SHEET_ID = getenv("GOOGLE_SHEET_ID")


scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
if os.path.exists("credentials.json"):
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
else:
    creds_json = json.loads(getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
gs_client = gspread.authorize(creds)
sheet = gs_client.open_by_key(GOOGLE_SHEET_ID).sheet1

BOT_TOKEN = getenv("BOT_TOKEN")
GROQ_API_KEY = getenv("GROQ_API_KEY")
ADMIN_ID = int(getenv("ADMIN_ID"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

BOOKINGS_FILE = "bookings.csv"

MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр",
    5: "май", 6: "июн", 7: "июл", 8: "авг",
    9: "сен", 10: "окт", 11: "ноя", 12: "дек"
}
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
TIME_SLOTS = [f"{h:02d}:00" for h in range(10, 20)]  # 10 слотов: 10:00–19:00


def save_booking(name, service, date, time, user_id):
    file_exists = os.path.exists(BOOKINGS_FILE)
    with open(BOOKINGS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Имя", "Услуга", "Дата", "Время", "User ID"])
        writer.writerow([name, service, date, time, user_id])

    # Сохраняем в Google Sheets
    if sheet.row_values(1) == []:
        sheet.append_row(["Имя", "Услуга", "Дата", "Время", "User ID"])
    sheet.append_row([name, service, date, time, str(user_id)])


def get_booked_slots() -> dict:
    """Возвращает {date_str: set(time_str)} из Google Sheets."""
    records = sheet.get_all_values()
    booked = {}
    for row in records[1:]:  # пропускаем заголовок
        if len(row) >= 4:
            date_str = row[2]  # колонка Дата
            time_str = row[3]  # колонка Время
            if date_str not in booked:
                booked[date_str] = set()
            booked[date_str].add(time_str)
    return booked


def build_week_keyboard(offset: int) -> InlineKeyboardMarkup:
    today = date.today()
    start = today + timedelta(weeks=offset)
    booked = get_booked_slots()

    buttons = []
    for i in range(7):
        day = start + timedelta(days=i)
        day_str = day.strftime("%d.%m.%Y")
        day_name = DAYS_RU[day.weekday()]
        month_name = MONTHS_RU[day.month]

        day_booked = booked.get(day_str, set())
        all_busy = len(day_booked) >= len(TIME_SLOTS)
        emoji = "❌" if all_busy else "✅"
        label = f"{day_name} {day.day} {month_name} {emoji}"

        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"day_{day_str}"
        )])

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data="week_prev"))
    nav_row.append(InlineKeyboardButton(text="▶️ Вперёд", callback_data="week_next"))
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_slots_keyboard(date_str: str) -> InlineKeyboardMarkup:
    booked = get_booked_slots()
    day_booked = booked.get(date_str, set())

    buttons = []
    row = []
    for slot in TIME_SLOTS:
        is_busy = slot in day_booked
        if is_busy:
            btn = InlineKeyboardButton(text=f"❌ {slot}", callback_data="slot_busy")
        else:
            btn = InlineKeyboardButton(text=slot, callback_data=f"slot_{slot}")
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_week = State()
    choosing_slot = State()
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
    await state.update_data(service=call.data, week_offset=0)
    await call.answer(f"Вы выбрали: {service_name}")

    keyboard = build_week_keyboard(offset=0)
    await call.message.answer("Выберите удобный день:", reply_markup=keyboard)
    await state.set_state(BookingStates.choosing_week)

@dp.callback_query(BookingStates.choosing_week, F.data == "week_next")
async def on_week_next(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offset = data.get("week_offset", 0) + 1
    await state.update_data(week_offset=offset)
    keyboard = build_week_keyboard(offset)
    await call.message.edit_reply_markup(reply_markup=keyboard)
    await call.answer()

@dp.callback_query(BookingStates.choosing_week, F.data == "week_prev")
async def on_week_prev(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offset = max(0, data.get("week_offset", 0) - 1)
    await state.update_data(week_offset=offset)
    keyboard = build_week_keyboard(offset)
    await call.message.edit_reply_markup(reply_markup=keyboard)
    await call.answer()

@dp.callback_query(BookingStates.choosing_week, F.data.startswith("day_"))
async def on_day_selected(call: CallbackQuery, state: FSMContext):
    date_str = call.data[4:]  # убираем префикс "day_"
    await state.update_data(date=date_str)
    await call.answer(f"Выбрана дата: {date_str}")

    keyboard = build_slots_keyboard(date_str)
    await call.message.answer(f"Выберите время на {date_str}:", reply_markup=keyboard)
    await state.set_state(BookingStates.choosing_slot)

@dp.callback_query(BookingStates.choosing_slot, F.data == "slot_busy")
async def on_slot_busy(call: CallbackQuery):
    await call.answer("Этот слот уже занят, выберите другое время.", show_alert=True)

@dp.callback_query(BookingStates.choosing_slot, F.data.startswith("slot_"))
async def on_slot_selected(call: CallbackQuery, state: FSMContext):
    time_str = call.data[5:]  # убираем префикс "slot_"
    await state.update_data(time=time_str)
    await call.answer(f"Выбрано время: {time_str}")
    await call.message.answer("Введите ваше имя:")
    await state.set_state(BookingStates.entering_name)

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
