import telebot
import sqlite3
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
import google.generativeai as genai
from PIL import Image
import io
import re
import random

# ===== НАСТРОЙКИ =====
TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
GEMINI_KEY = 'AIzaSyCl_f0jRS8L-ufaybBoJ0pGXFr3fRXEMV8'

# ===== АДМИНИСТРАТОР (безлимит) =====
ADMINS = [1985646308]

# ===== НАСТРОЙКА GEMINI =====
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ===== ЛИМИТЫ И ЦЕНЫ =====
FREE_LIMIT = 4
PREMIUM_LIGHT_LIMIT = 10
PREMIUM_PRO_LIMIT = 999999
PREMIUM_LIGHT_PRICE = 25
PREMIUM_PRO_PRICE = 50
REFERRAL_BONUS = 3

bot = telebot.TeleBot(TOKEN)

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            messages_today INTEGER DEFAULT 0,
            last_date TEXT,
            premium_level INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            bonus_messages INTEGER DEFAULT 0,
            username TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT messages_today, last_date, premium_level, referred_by, referral_count, bonus_messages, username FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'messages_today': row[0],
            'last_date': row[1],
            'premium_level': row[2],
            'referred_by': row[3],
            'referral_count': row[4],
            'bonus_messages': row[5],
            'username': row[6]
        }
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect('bot_users.db')
        c = conn.cursor()
        c.execute('INSERT INTO users (user_id, messages_today, last_date, premium_level, referred_by, referral_count, bonus_messages, username) VALUES (?, 0, ?, 0, 0, 0, 0, ?)', (user_id, today, ''))
        conn.commit()
        conn.close()
        return {'messages_today': 0, 'last_date': today, 'premium_level': 0, 'referred_by': 0, 'referral_count': 0, 'bonus_messages': 0, 'username': ''}

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    for key, val in kwargs.items():
        c.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (val, user_id))
    conn.commit()
    conn.close()

def get_user_limit(user):
    base = FREE_LIMIT
    if user['premium_level'] == 2:
        base = PREMIUM_PRO_LIMIT
    elif user['premium_level'] == 1:
        base = PREMIUM_LIGHT_LIMIT
    if base == PREMIUM_PRO_LIMIT:
        return base
    return base + user['bonus_messages']

def can_send(user_id):
    if user_id in ADMINS:
        return True
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, messages_today=0)
        return True
    return user['messages_today'] < get_user_limit(user)

def increment_count(user_id):
    if user_id in ADMINS:
        return
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, messages_today=1)
    else:
        update_user(user_id, messages_today=user['messages_today'] + 1)

# ===== ФУНКЦИЯ ЗАПРОСА К GEMINI =====
def ask_gemini(question, image_data=None):
    try:
        if image_data:
            img = Image.open(io.BytesIO(image_data))
            response = model.generate_content([question, img])
        else:
            response = model.generate_content(question)
        return response.text
    except Exception as e:
        return f"❌ Ошибка ИИ: {str(e)[:200]}"

# ===== КНОПКИ И МЕНЮ =====
def main_menu(user_id):
    user = get_user(user_id)
    if user['premium_level'] == 2:
        status = "👑 Premium Pro (безлимит)"
    elif user['premium_level'] == 1:
        status = "🌟 Premium Light (10 запросов/день)"
    else:
        status = "🔓 Бесплатный (4 запроса/день)"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("👥 Рефералка", callback_data="referral"),
        InlineKeyboardButton("⭐ Light (25⭐)", callback_data="buy_light"),
        InlineKeyboardButton("👑 Pro (50⭐)", callback_data="buy_pro"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup, status

def quick_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats")
    )
    return markup

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('ref_'):
        ref = int(args[1][4:])
        if ref != user_id:
            user = get_user(user_id)
            if user['referred_by'] == 0:
                update_user(user_id, referred_by=ref)
                update_user(ref, bonus_messages=get_user(ref)['bonus_messages'] + REFERRAL_BONUS, referral_count=get_user(ref)['referral_count'] + 1)
                bot.send_message(user_id, "🎁 Ты перешёл по реферальной ссылке! +3 запроса/день навсегда!")
                bot.send_message(ref, "🎉 Новый реферал! +3 запроса/день!")
    markup, status = main_menu(user_id)
    bot.send_message(message.chat.id,
        f"🤖 *ReshiBot с ИИ*\n\n"
        f"Я решаю ЛЮБЫЕ примеры, задачи и тесты!\n\n"
        f"📸 Отправь фото — ИИ решит всё задание\n"
        f"✍️ Напиши вопрос — например: реши уравнение 2x+5=15\n\n"
        f"💎 Твой статус: {status}\n\n"
        f"👇 Нажми на кнопку ниже",
        parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    if call.data == "menu":
        markup, status = main_menu(user_id)
        bot.edit_message_text(f"🏠 Главное меню\n\nТвой статус: {status}", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(call.id)
    elif call.data == "stats":
        user = get_user(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        used = user['messages_today'] if user['last_date'] == today else 0
        limit = get_user_limit(user)
        text = f"📊 *Статистика*\n📸 Сегодня: {used}/{limit}\n👥 Рефералов: {user['referral_count']}\n🎁 Бонус: +{user['bonus_messages']}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_menu())
        bot.answer_callback_query(call.id)
    elif call.data == "referral":
        link = f"https://t.me/{bot.get_me().username}?start=ref_{user_id}"
        text = f"👥 *Твоя ссылка*\n{link}\nЗа каждого друга +3 запроса/день!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_menu())
        bot.answer_callback_query(call.id)
    elif call.data == "buy_light":
        bot.send_invoice(call.message.chat.id, title="⭐ Premium Light", description="10 запросов/день", invoice_payload="light", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Light", PREMIUM_LIGHT_PRICE)])
    elif call.data == "buy_pro":
        bot.send_invoice(call.message.chat.id, title="👑 Premium Pro", description="Безлимит", invoice_payload="pro", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Pro", PREMIUM_PRO_PRICE)])
    elif call.data == "help":
        text = "❓ *Помощь*\n✍️ Напиши любой вопрос\n📸 Отправь фото теста\n⭐ Купи Premium за Telegram Stars"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_menu())
        bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    level = 1 if message.successful_payment.invoice_payload == "light" else 2
    update_user(message.from_user.id, premium_level=level)
    bot.send_message(message.chat.id, f"✅ Premium {'Light' if level==1 else 'Pro'} активирован!")

# ===== ОБРАБОТКА СООБЩЕНИЙ =====
@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_handler(m):
    user_id = m.from_user.id
    text = m.text.strip()
    if text.startswith('/'):
        return
    if not can_send(user_id):
        user = get_user(user_id)
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} запросов/день. Купи Premium!")
        return
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(text)
    increment_count(user_id)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_menu())

@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    user_id = m.from_user.id
    if not can_send(user_id):
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} запросов/день. Купи Premium!")
        return
    msg = bot.reply_to(m, "🔄 Распознаю и решаю...")
    file = bot.get_file(m.photo[-1].file_id)
    data = bot.download_file(file.file_path)
    ans = ask_gemini("Реши задание с этого фото. Подробно. Пиши на русском.", data)
    increment_count(user_id)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_menu())

# ===== ЗАПУСК =====
if __name__ == '__main__':
    init_db()
    print("✅ Бот запущен!")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
