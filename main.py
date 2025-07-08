import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import types

API_TOKEN = os.getenv("BOT_TOKEN")
PSYCHOLOG_ID = int(os.getenv("PSYCHOLOG_ID"))
user_data_file = "user_data.json"
session_data_file = "sessions.json"

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

active_sessions = {}
user_data = {}

start_button = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Начать", callback_data="start_session")]
])

final_button = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Готов(а) записаться на консультацию", url="https://t.me/psycenter_support_bot")]
])

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_json(user_data_file)
active_sessions = load_json(session_data_file)

@dp.message(CommandStart())
async def start(message: Message):
    user_id = str(message.from_user.id)
    last_used = user_data.get(user_id)
    now = datetime.utcnow()

    if last_used:
        last_used_time = datetime.fromisoformat(last_used)
        if now - last_used_time < timedelta(days=30):
            await message.answer("Ты уже пользовался(-ась) ботом в этом месяце. Попробуй снова позже.")
            return

    await message.answer(
        "Привет! Это бот экстренной психологической поддержки Центра клинической психологии и психотерапии. Здесь ты можешь поговорить с психологом в течение 30 минут.\n\n⚠️ Пожалуйста, помни: это не служба спасения. Если ты в опасности, обратись по номеру 112.\n\nЕсли согласен(на) — нажми «Начать».",
        reply_markup=start_button
    )

@dp.callback_query(F.data == "start_session")
async def handle_session_start(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    now = datetime.utcnow()
    user_data[user_id] = now.isoformat()
    save_json(user_data_file, user_data)

    await callback.message.answer("Ожидай подключения психолога...")

    await bot.send_message(
        PSYCHOLOG_ID,
        f"🔔 Новый клиент: {callback.from_user.full_name} (@{callback.from_user.username})\nID: {callback.from_user.id}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Начать сессию", callback_data=f"admin_start_{user_id}")]]
        )
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_start_"))
async def admin_start(callback: CallbackQuery):
    if callback.from_user.id != PSYCHOLOG_ID:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.replace("admin_start_", ""))
    active_sessions[str(client_id)] = {
        "start_time": datetime.utcnow().isoformat(),
        "warned": False
    }
    save_json(session_data_file, active_sessions)

    await bot.send_message(client_id, "🔔 Психолог подключился. Можешь начать писать сообщение.")
    await callback.answer("Сессия началась")

@dp.message()
async def forward_message(message: Message):
    user_id = str(message.from_user.id)
    print(f"Получено сообщение от {user_id}: {message.text}")

    if user_id == str(PSYCHOLOG_ID) and message.reply_to_message:
        lines = message.reply_to_message.text.splitlines()
        for line in lines:
            if line.startswith("ID: "):
                try:
                    client_id = int(line.split("ID: ")[1].split(":")[0])
                    await bot.send_message(client_id, message.text)
                    return
                except Exception as e:
                    logging.warning(f"Ошибка определения ID клиента: {e}")

    if user_id not in active_sessions:
        await message.answer("Сессия ещё не началась или уже завершена. Подожди, пока подключится психолог.")
        return

    await bot.send_message(
        PSYCHOLOG_ID,
        f"✉️ Новое сообщение от {message.from_user.full_name} (@{message.from_user.username})\nID: {user_id}:\n{message.text}"
    )

    session = active_sessions[user_id]
    start_time = datetime.fromisoformat(session["start_time"])
    elapsed = datetime.utcnow() - start_time

    if elapsed > timedelta(minutes=25) and not session["warned"]:
        await bot.send_message(user_id, "⏰ Осталось 5 минут до окончания сессии")
        session["warned"] = True
        save_json(session_data_file, active_sessions)

    if elapsed > timedelta(minutes=30):
        await bot.send_message(user_id, "Спасибо за доверие. Надеемся, тебе стало хоть немного легче.\nЕсли захочешь продолжить — записывайся на консультацию.\n💬 Первая сессия — со скидкой 20%!", reply_markup=final_button)
        del active_sessions[user_id]
        save_json(session_data_file, active_sessions)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))