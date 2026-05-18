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
ADMIN_ID = 1985646308

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = telebot.TeleBot(TOKEN)
active_tasks = {}

# База для обычных пользователей (для админа не используется)
def init_db():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, usage INTEGER DEFAULT 0, date TEXT)')
    conn.commit()
    conn.close()

def can_use(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('SELECT usage FROM users WHERE user_id = ? AND date = ?', (user_id, today))
    row = c.fetchone()
    conn.close()
    used = row[0] if row else 0
    return used < 4

def increment_usage(user_id):
    if user_id == ADMIN_ID:
        return
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO users (user_id, usage, date) VALUES (?, 1, ?) ON CONFLICT(user_id) DO UPDATE SET usage = usage + 1', (user_id, today))
    conn.commit()
    conn.close()

def simple_calc(expr):
    expr = expr.replace(' ', '').replace('×', '*').replace('÷', '/')
    if re.match(r'^[\d+\-*/\(\)]+$', expr):
        try:
            return eval(expr)
        except:
            return None
    return None

def ask_gemini(question, image_data=None):
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
    a, b = random.randint(1, 20), random.randint(1, 20)
    op = random.choice(['+', '-', '*'])
    if op == '+': return f"{a} + {b}", a + b
    if op == '-': return f"{a} - {b}", a - b
    return f"{a} * {b}", a * b

def main_menu(user_id):
    if user_id == ADMIN_ID:
        status = "👑 Админ (безлимит ∞)"
    else:
        conn = sqlite3.connect('bot_users.db')
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('SELECT usage FROM users WHERE user_id = ? AND date = ?', (user_id, today))
        row = c.fetchone()
        conn.close()
        used = row[0] if row else 0
        status = f"🔓 Бесплатный ({used}/4 запросов сегодня)"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup, status

def quick_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    )
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(m):
    markup, status = main_menu(m.from_user.id)
    bot.send_message(m.chat.id, f"🤖 *ReshiBot*\n\n📸 Фото — ИИ решит\n✍️ Пример (2+2) — калькулятор\n🎲 Случайный пример\n\n💎 {status}", parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    uid = call.from_user.id
    if call.data == "menu":
        markup, status = main_menu(uid)
        bot.edit_message_text(f"🏠 Главное меню\n\n{status}", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    elif call.data == "stats":
        if uid == ADMIN_ID:
            text = "👑 Админ — безлимит ∞"
        else:
            conn = sqlite3.connect('bot_users.db')
            c = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            c.execute('SELECT usage FROM users WHERE user_id = ? AND date = ?', (uid, today))
            row = c.fetchone()
            conn.close()
            used = row[0] if row else 0
            text = f"📊 Сегодня использовано: {used}/4 запросов"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "generate":
        ex, ans = generate_example()
        active_tasks[uid] = {'example': ex, 'answer': ans}
        bot.edit_message_text(f"🎲 *Реши пример*\n📝 {ex} = ?\n✍️ Напиши число", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "help":
        bot.edit_message_text("❓ *Помощь*\n✍️ Напиши 2+2\n📸 Отправь фото\n🎲 Случайный пример", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_handler(m):
    uid = m.from_user.id
    txt = m.text.strip()
    if txt.startswith('/'):
        return
    if uid in active_tasks:
        try:
            ans = int(txt)
            corr = active_tasks[uid]['answer']
            if ans == corr:
                bot.reply_to(m, f"✅ Верно! {active_tasks[uid]['example']} = {corr}", reply_markup=quick_buttons())
            else:
                bot.reply_to(m, f"❌ Неверно! {active_tasks[uid]['example']} = {corr}", reply_markup=quick_buttons())
            del active_tasks[uid]
            return
        except:
            bot.reply_to(m, "❓ Напиши число!", reply_markup=quick_buttons())
            return
    if not can_use(uid):
        bot.reply_to(m, "❌ Лимит 4 запроса в день. Завтра обновится.", reply_markup=quick_buttons())
        return
    res = simple_calc(txt)
    if res is not None:
        bot.reply_to(m, f"✅ {txt} = {res}", reply_markup=quick_buttons())
        increment_usage(uid)
        return
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(txt)
    increment_usage(uid)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_buttons())

@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    uid = m.from_user.id
    if not can_use(uid):
        bot.reply_to(m, "❌ Лимит 4 запроса в день. Завтра обновится.", reply_markup=quick_buttons())
        return
    msg = bot.reply_to(m, "🔄 Распознаю и решаю...")
    file = bot.get_file(m.photo[-1].file_id)
    data = bot.download_file(file.file_path)
    # OCR
    ocr = requests.post('https://api.ocr.space/parse/image', files={'file': ('img.jpg', data)}, data={'apikey': OCR_API_KEY, 'language': 'rus'})
    ocr_data = ocr.json()
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
        increment_usage(uid)
        return
    ans = ask_gemini(f"Реши пример: {parsed}. Напиши ответ.", None)
    increment_usage(uid)
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
