import telebot
import requests
import sqlite3
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import time
import random
import google.generativeai as genai
from PIL import Image
import io

TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
OCR_API_KEY = 'K85192594388957'
GEMINI_KEY = 'AIzaSyCl_f0jRS8L-ufaybBoJ0pGXFr3fRXEMV8'

genai.configure(api_key=GEMINI_KEY)
model = None
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        model = genai.GenerativeModel(m.name)
        print(f"✅ Модель: {m.name}")
        break

bot = telebot.TeleBot(TOKEN)
active_tasks = {}

def simple_calc(expr):
    expr = expr.replace(' ', '').replace('×', '*').replace('÷', '/')
    if re.match(r'^[\d+\-*/\(\)]+$', expr):
        try:
            return eval(expr)
        except:
            return None
    return None

def ask_gemini(question, image_data=None):
    if model is None:
        return "❌ ИИ временно недоступен."
    try:
        if image_data:
            img = Image.open(io.BytesIO(image_data))
            response = model.generate_content([question, img])
        else:
            response = model.generate_content(question)
        return response.text
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def generate_example():
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        return f"{a} + {b}", a + b
    elif op == '-':
        return f"{a} - {b}", a - b
    return f"{a} * {b}", a * b

def quick_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    )
    return markup

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id,
        f"🤖 *ReshiBot*\n\n"
        f"📸 Отправь фото с примером\n"
        f"✍️ Напиши пример (2+2) — калькулятор\n"
        f"🎲 Случайный пример\n\n"
        f"👇",
        parse_mode='Markdown', reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "menu":
        bot.edit_message_text("🏠 Главное меню", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    elif call.data == "generate":
        ex, ans = generate_example()
        active_tasks[call.from_user.id] = {'example': ex, 'answer': ans}
        bot.edit_message_text(f"🎲 *Реши пример*\n📝 {ex} = ?\n✍️ Напиши число", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "help":
        bot.edit_message_text("❓ *Помощь*\n✍️ Напиши 2+2\n📸 Отправь фото", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=main_menu())
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_handler(m):
    uid = m.from_user.id
    text = m.text.strip()
    if text.startswith('/'):
        return
    if uid in active_tasks:
        try:
            ans = int(text)
            correct = active_tasks[uid]['answer']
            if ans == correct:
                bot.reply_to(m, f"✅ Верно! {active_tasks[uid]['example']} = {correct}", reply_markup=quick_buttons())
            else:
                bot.reply_to(m, f"❌ Неверно! {active_tasks[uid]['example']} = {correct}", reply_markup=quick_buttons())
            del active_tasks[uid]
            return
        except:
            bot.reply_to(m, "❓ Напиши число!", reply_markup=quick_buttons())
            return
    res = simple_calc(text)
    if res is not None:
        bot.reply_to(m, f"✅ {text} = {res}", reply_markup=quick_buttons())
        return
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(text)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_buttons())

@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    msg = bot.reply_to(m, "🔄 Распознаю и решаю...")
    file = bot.get_file(m.photo[-1].file_id)
    file_data = bot.download_file(file.file_path)
    # OCR
    ocr_response = requests.post(
        'https://api.ocr.space/parse/image',
        files={'file': ('img.jpg', file_data)},
        data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2},
        timeout=30
    )
    ocr_data = ocr_response.json()
    if ocr_data.get('IsErroredOnProcessing') or not ocr_data.get('ParsedResults'):
        bot.edit_message_text("❌ Не распознано. Сфоткай чётче.", m.chat.id, msg.message_id)
        return
    parsed = ocr_data['ParsedResults'][0]['ParsedText'].strip()
    parsed = re.sub(r'[^0-9+\-*/()=.\s]', '', parsed)
    if not parsed:
        bot.edit_message_text("❌ Текст не найден.", m.chat.id, msg.message_id)
        return
    res = simple_calc(parsed)
    if res is not None:
        bot.edit_message_text(f"✅ {parsed} = {res}", m.chat.id, msg.message_id, reply_markup=quick_buttons())
        return
    bot.edit_message_text("🔄 Решаю через ИИ...", m.chat.id, msg.message_id)
    ans = ask_gemini(f"Реши пример: {parsed}. Напиши ответ и решение.", None)
    bot.edit_message_text(f"✅ {ans}", m.chat.id, msg.message_id, reply_markup=quick_buttons())

if __name__ == '__main__':
    print("✅ Бот запущен. Без лимитов, без админов.")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
