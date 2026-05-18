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

ADMIN_ID = 1985646308  # Твой ID — безлимит

genai.configure(api_key=GEMINI_KEY)
model = None
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        model = genai.GenerativeModel(m.name)
        print(f"✅ Модель: {m.name}")
        break

FREE_LIMIT = 4
PREMIUM_LIGHT_LIMIT = 10
PREMIUM_PRO_LIMIT = 999999
PREMIUM_LIGHT_PRICE = 25
PREMIUM_PRO_PRICE = 50
REFERRAL_BONUS = 3

bot = telebot.TeleBot(TOKEN)
active_tasks = {}

def init_db():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            photos_today INTEGER DEFAULT 0,
            last_date TEXT,
            premium_level INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            bonus_photos INTEGER DEFAULT 0,
            username TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT photos_today, last_date, premium_level, referred_by, referral_count, bonus_photos, username FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'photos_today': row[0],
            'last_date': row[1],
            'premium_level': row[2],
            'referred_by': row[3],
            'referral_count': row[4],
            'bonus_photos': row[5],
            'username': row[6]
        }
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect('bot_users.db')
        c = conn.cursor()
        c.execute('INSERT INTO users (user_id, photos_today, last_date, premium_level, referred_by, referral_count, bonus_photos, username) VALUES (?, 0, ?, 0, 0, 0, 0, ?)', (user_id, today, ''))
        conn.commit()
        conn.close()
        return {'photos_today': 0, 'last_date': today, 'premium_level': 0, 'referred_by': 0, 'referral_count': 0, 'bonus_photos': 0, 'username': ''}

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    for key, val in kwargs.items():
        c.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (val, user_id))
    conn.commit()
    conn.close()

def get_user_limit(user):
    if user['premium_level'] == 2:
        return PREMIUM_PRO_LIMIT
    elif user['premium_level'] == 1:
        return PREMIUM_LIGHT_LIMIT
    return FREE_LIMIT + user['bonus_photos']

def can_upload_photo(user_id):
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=0)
        return True
    return user['photos_today'] < get_user_limit(user)

def increment_photo_count(user_id):
    if user_id == ADMIN_ID:
        return
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=1)
    else:
        update_user(user_id, photos_today=user['photos_today'] + 1)

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

def get_top_users(limit=10):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, referral_count FROM users WHERE referral_count > 0 ORDER BY referral_count DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    top = []
    for i, (uid, name, cnt) in enumerate(rows, 1):
        top.append((i, name or str(uid), cnt))
    return top

def quick_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    )
    return markup

def main_menu(user_id):
    user = get_user(user_id)
    if user_id == ADMIN_ID:
        status = "👑 Админ (безлимит ∞)"
    elif user['premium_level'] == 2:
        status = "👑 Premium Pro (безлимит)"
    elif user['premium_level'] == 1:
        status = "🌟 Premium Light (10 фото/день)"
    else:
        limit = get_user_limit(user)
        used = user['photos_today'] if user['last_date'] == datetime.now().strftime('%Y-%m-%d') else 0
        status = f"🔓 Бесплатный ({used}/{limit} фото сегодня)"
    bonus = f"\n🎁 Бонус: +{user['bonus_photos']}" if user['bonus_photos'] > 0 else ""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("🏆 Топ пользователей", callback_data="top"),
        InlineKeyboardButton("👥 Рефералка", callback_data="referral"),
        InlineKeyboardButton("⭐ Light (25⭐)", callback_data="buy_light"),
        InlineKeyboardButton("👑 Pro (50⭐)", callback_data="buy_pro"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup, status + bonus

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if len(text.split()) > 1 and text.split()[1].startswith('ref_'):
        ref = int(text.split()[1][4:])
        if ref != user_id:
            user = get_user(user_id)
            if user['referred_by'] == 0:
                update_user(user_id, referred_by=ref)
                update_user(ref, bonus_photos=get_user(ref)['bonus_photos'] + REFERRAL_BONUS, referral_count=get_user(ref)['referral_count'] + 1)
                bot.send_message(user_id, "🎁 +3 фото/день по рефералке!")
                bot.send_message(ref, "🎉 Новый реферал! +3 фото/день!")
    markup, status = main_menu(user_id)
    bot.send_message(message.chat.id,
        f"🤖 *ReshiBot*\n\n"
        f"📸 Отправь фото — OCR + ИИ решат\n"
        f"✍️ Напиши пример (2+2) — калькулятор\n"
        f"🎲 Случайный пример — проверь себя\n\n"
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
            text = "👑 Админ — безлимит ∞"
        else:
            user = get_user(user_id)
            today = datetime.now().strftime('%Y-%m-%d')
            used = user['photos_today'] if user['last_date'] == today else 0
            limit = get_user_limit(user)
            text = f"📊 *Статистика*\nСегодня использовано: {used}/{limit}\nРефералов: {user['referral_count']}\nБонус: +{user['bonus_photos']}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "generate":
        ex, ans = generate_example()
        active_tasks[user_id] = {'example': ex, 'answer': ans}
        bot.edit_message_text(f"🎲 *Реши пример*\n📝 {ex} = ?\n✍️ Напиши число", call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "top":
        top = get_top_users()
        if not top:
            text = "🏆 Топ пуст. Приводи друзей!"
        else:
            text = "🏆 *Топ рефералов*\n"
            for i, name, cnt in top:
                text += f"{i}. {name} — {cnt}\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "referral":
        link = f"https://t.me/{bot.get_me().username}?start=ref_{user_id}"
        text = f"👥 *Твоя ссылка*\n{link}\nЗа каждого друга +3 фото/день!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    elif call.data == "buy_light":
        bot.send_invoice(call.message.chat.id, title="⭐ Premium Light", description="10 фото/день", invoice_payload="light", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Light", PREMIUM_LIGHT_PRICE)])
    elif call.data == "buy_pro":
        bot.send_invoice(call.message.chat.id, title="👑 Premium Pro", description="Безлимит", invoice_payload="pro", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Pro", PREMIUM_PRO_PRICE)])
    elif call.data == "help":
        text = "❓ *Помощь*\n✍️ Напиши 2+2 — калькулятор\n📸 Отправь фото уравнения\n🎲 Случайный пример\n⭐ Premium за Stars"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=quick_buttons())
    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    level = 1 if message.successful_payment.invoice_payload == "light" else 2
    update_user(message.from_user.id, premium_level=level)
    bot.send_message(message.chat.id, f"✅ Premium {'Light' if level==1 else 'Pro'} активирован!")

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
    res = simple_calc(text)
    if res is not None:
        bot.reply_to(m, f"✅ {text} = {res}", reply_markup=quick_buttons())
        increment_photo_count(user_id)
        return
    if not can_upload_photo(user_id):
        markup, _ = main_menu(user_id)
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} запросов в день. Купи Premium!", reply_markup=markup)
        return
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(text)
    increment_photo_count(user_id)
    bot.edit_message_text(ans[:3000], m.chat.id, msg.message_id, reply_markup=quick_buttons())

@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    user_id = m.from_user.id
    if not can_upload_photo(user_id):
        markup, _ = main_menu(user_id)
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} фото в день. Купи Premium!", reply_markup=markup)
        return
    msg = bot.reply_to(m, "🔄 Распознаю текст...")
    file = bot.get_file(m.photo[-1].file_id)
    file_data = bot.download_file(file.file_path)
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
        increment_photo_count(user_id)
        return
    bot.edit_message_text("🔄 Решаю через ИИ...", m.chat.id, msg.message_id)
    ans = ask_gemini(f"Реши пример: {parsed}. Напиши ответ и решение.", None)
    increment_photo_count(user_id)
    bot.edit_message_text(f"✅ {ans}", m.chat.id, msg.message_id, reply_markup=quick_buttons())

if __name__ == '__main__':
    init_db()
    print("✅ Бот запущен. У админа безлимит ∞")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
