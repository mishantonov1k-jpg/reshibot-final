import telebot
import sqlite3
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
import google.generativeai as genai
from PIL import Image
import io
import random
import re
import requests

TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
OCR_API_KEY = 'K85192594388957'
GEMINI_KEY = 'AIzaSyCl_f0jRS8L-ufaybBoJ0pGXFr3fRXEMV8'

# Твой ID — админ, для него нет лимита
ADMIN_ID = 1985646308

# Gemini
genai.configure(api_key=GEMINI_KEY)
model = None
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        model = genai.GenerativeModel(m.name)
        print(f"Модель: {m.name}")
        break

bot = telebot.TeleBot(TOKEN)
active_tasks = {}

# ===== БАЗА ДАННЫХ (для других пользователей) =====
def init_db():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            usage_today INTEGER DEFAULT 0,
            last_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_usage(user_id):
    if user_id == ADMIN_ID:
        return 0  # Админ — всегда 0
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT usage_today, last_date FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    today = datetime.now().strftime('%Y-%m-%d')
    if row and row[1] == today:
        return row[0]
    return 0

def increment_usage(user_id):
    if user_id == ADMIN_ID:
        return
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO users (user_id, usage_today, last_date) VALUES (?, 1, ?) ON CONFLICT(user_id) DO UPDATE SET usage_today = usage_today + 1, last_date = ?', (user_id, today, today))
    conn.commit()
    conn.close()

def can_use(user_id):
    if user_id == ADMIN_ID:
        return True
    return get_usage(user_id) < 4

# ===== КАЛЬКУЛЯТОР =====
def simple_calc(text):
    text = text.replace(' ', '').replace('×', '*').replace('÷', '/')
    if re.match(r'^[\d+\-*/\(\)]+$', text):
        try:
            return eval(text)
        except:
            return None
    return None

def ask_gemini(question, image_data=None):
    if model is None:
        return "❌ ИИ недоступен."
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
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    )
    return markup

def main_menu(user_id):
    if user_id == ADMIN_ID:
        status = "👑 Админ (безлимит)"
    else:
        used = get_usage(user_id)
        status = f"🔓 Бесплатный ({4 - used}/4 запросов сегодня)"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup, status

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    markup, status = main_menu(user_id)
    bot.send_message(message.chat.id,
        f"🤖 *ReshiBot*\n\n"
        f"📸 Отправь фото с примером\n"
        f"✍️ Напиши пример (2+2) — калькулятор\n"
        f"🎲 Случайный пример — не тратит лимит\n\n"
        f"💎 {status}\n👇",
        parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    if call.data == "menu":
        markup, status = main_menu(user_id)
        bot.edit_message_text(f"🏠 Главное меню\n\n{status}", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    elif call.data == "stats":
        if user_id == ADMIN_ID:
            text = "👑 Админ — безлимит"
        else:
            used = get_usage(user_id)
            text = f"📊 Сегодня использовано: {used}/4 запросов"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "generate":
        ex, ans = generate_example()
        active_tasks[user_id] = {'example': ex, 'answer': ans}
        bot.edit_message_text(f"🎲 *Реши пример*\n📝 {ex} = ?\n✍️ Напиши число", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "help":
        text = "❓ *Помощь*\n✍️ Напиши 2+2 — калькулятор\n📸 Отправь фото уравнения\n🎲 Случайный пример — не тратит лимит"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_handler(m):
    user_id = m.from_user.id
    text = m.text.strip()
    if text.startswith('/'):
        return
    if user_id in active_tasks:
        try:
            ans = int(text)
            correct = active_tasks[user_id]['answer']
            if ans == correct:
                bot.reply_to(m, f"✅ Верно! {active_tasks[user_id]['example']} = {correct}", reply_markup=quick_buttons())
            else:
                bot.reply_to(m, f"❌ Неверно! {active_tasks[user_id]['example']} = {correct}", reply_markup=quick_buttons())
            del active_tasks[user_id]
            return
        except:
            bot.reply_to(m, "❓ Напиши число!", reply_markup=quick_buttons())
            return
    # Проверка лимита
    if not can_use(user_id):
        bot.reply_to(m, "❌ Лимит 4 запроса в день. Завтра обновится.", reply_markup=quick_buttons())
        return
    # Калькулятор
    res = simple_calc(text)
    if res is not None:
        bot.reply_to(m, f"✅ {text} = {res}", reply_markup=quick_buttons())
        increment_usage(user_id)
        return
    # ИИ для сложного
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(text)
    increment_usage(user_id)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_buttons())

@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    user_id = m.from_user.id
    if not can_use(user_id):
        bot.reply_to(m, "❌ Лимит 4 запроса в день. Завтра обновится.", reply_markup=quick_buttons())
        return
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
    # Решаем
    res = simple_calc(parsed)
    if res is not None:
        bot.edit_message_text(f"✅ {parsed} = {res}", m.chat.id, msg.message_id, reply_markup=quick_buttons())
        increment_usage(user_id)
        return
    bot.edit_message_text("🔄 Решаю через ИИ...", m.chat.id, msg.message_id)
    ans = ask_gemini(f"Реши пример: {parsed}. Напиши ответ.", None)
    increment_usage(user_id)
    bot.edit_message_text(f"✅ {ans}", m.chat.id, msg.message_id, reply_markup=quick_buttons())

if __name__ == '__main__':
    init_db()
    print("✅ Бот запущен. У админа безлимит.")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
