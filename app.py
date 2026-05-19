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

# ===== НАСТРОЙКИ =====
TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
OCR_API_KEY = 'K85192594388957'
GEMINI_KEY = 'AIzaSyCl_f0jRS8L-ufaybBoJ0pGXFr3fRXEMV8'

# Администраторы (безлимит) — добавь свой ID
ADMINS = [1985646308]  # Твой user_id

# ===== НАСТРОЙКА GEMINI =====
genai.configure(api_key=GEMINI_KEY)
model = None
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        model = genai.GenerativeModel(m.name)
        print(f"✅ Использую модель: {m.name}")
        break

FREE_LIMIT = 4
PREMIUM_LIGHT_LIMIT = 10
PREMIUM_PRO_LIMIT = 999999
PREMIUM_LIGHT_PRICE = 25
PREMIUM_PRO_PRICE = 50
REFERRAL_BONUS = 3
REFERRAL_INCOME_PERCENT = 10

bot = telebot.TeleBot(TOKEN)
active_tasks = {}

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute('''
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
    cursor = conn.cursor()
    cursor.execute('''
        SELECT photos_today, last_date, premium_level, referred_by, referral_count, bonus_photos, username 
        FROM users WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
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
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, photos_today, last_date, premium_level, referred_by, referral_count, bonus_photos, username) 
            VALUES (?, 0, ?, 0, 0, 0, 0, ?)
        ''', (user_id, today, ''))
        conn.commit()
        conn.close()
        return {
            'photos_today': 0, 
            'last_date': today, 
            'premium_level': 0,
            'referred_by': 0,
            'referral_count': 0,
            'bonus_photos': 0,
            'username': ''
        }

def update_user(user_id, photos_today=None, premium_level=None, bonus_photos=None, username=None):
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    if photos_today is not None:
        cursor.execute('UPDATE users SET photos_today = ?, last_date = ? WHERE user_id = ?', 
                       (photos_today, datetime.now().strftime('%Y-%m-%d'), user_id))
    if premium_level is not None:
        cursor.execute('UPDATE users SET premium_level = ? WHERE user_id = ?', (premium_level, user_id))
    if bonus_photos is not None:
        cursor.execute('UPDATE users SET bonus_photos = ? WHERE user_id = ?', (bonus_photos, user_id))
    if username is not None:
        cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    conn.commit()
    conn.close()

def increment_referral_count(user_id):
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET referral_count = referral_count + 1, bonus_photos = bonus_photos + ? WHERE user_id = ?', 
                   (REFERRAL_BONUS, user_id))
    conn.commit()
    conn.close()

def get_user_limit(user):
    base_limit = FREE_LIMIT
    if user['premium_level'] == 2:
        base_limit = PREMIUM_PRO_LIMIT
    elif user['premium_level'] == 1:
        base_limit = PREMIUM_LIGHT_LIMIT
    if base_limit == PREMIUM_PRO_LIMIT:
        return base_limit
    return base_limit + user['bonus_photos']

def can_upload_photo(user_id):
    if user_id in ADMINS:
        return True
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=0)
        return True
    return user['photos_today'] < get_user_limit(user)

def increment_photo_count(user_id):
    if user_id in ADMINS:
        return
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=1)
    else:
        update_user(user_id, photos_today=user['photos_today'] + 1)

# ===== КАЛЬКУЛЯТОР =====
def simple_calc(expr):
    expr = expr.replace(' ', '').replace('×', '*').replace('÷', '/')
    if re.match(r'^[\d+\-*/\(\)]+$', expr):
        try:
            return eval(expr)
        except:
            return None
    return None

# ===== ФУНКЦИЯ ИИ =====
def ask_gemini(question, image_data=None):
    if model is None:
        return "❌ ИИ недоступен. Попробуй позже."
    try:
        if image_data:
            img = Image.open(io.BytesIO(image_data))
            response = model.generate_content([question, img])
        else:
            response = model.generate_content(question)
        return response.text
    except Exception as e:
        return f"❌ Ошибка ИИ: {str(e)[:200]}"

# ===== ГЕНЕРАТОР ПРИМЕРОВ =====
def generate_example():
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        return f"{a} + {b}", a + b
    elif op == '-':
        return f"{a} - {b}", a - b
    else:
        return f"{a} * {b}", a * b

def get_top_users(limit=10):
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, referral_count FROM users WHERE referral_count > 0 ORDER BY referral_count DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    top_list = []
    for i, row in enumerate(rows, 1):
        user_id, username, count = row
        top_list.append((i, username or str(user_id), count))
    return top_list

def quick_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("📊 Мои фото", callback_data="stats"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    )
    return markup

def main_menu(user_id):
    user = get_user(user_id)
    if user['premium_level'] == 2:
        status = "👑 Premium Pro (безлимит)"
    elif user['premium_level'] == 1:
        status = "🌟 Premium Light (10 фото/день)"
    else:
        status = "🔓 Бесплатный (4 фото/день)"
    bonus_text = f"\n🎁 Бонус: +{user['bonus_photos']}" if user['bonus_photos'] > 0 else ""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Мои фото", callback_data="stats"),
        InlineKeyboardButton("🎲 Случайный пример", callback_data="generate"),
        InlineKeyboardButton("🏆 Топ пользователей", callback_data="top"),
        InlineKeyboardButton("👥 Привести друга", callback_data="referral"),
        InlineKeyboardButton("⭐ Premium Light (25⭐)", callback_data="buy_premium_light"),
        InlineKeyboardButton("👑 Premium Pro (50⭐)", callback_data="buy_premium_pro"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup, status + bonus_text

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    text = message.text.strip()
    username = message.from_user.username or ''
    update_user(user_id, username=username)
    
    if len(text.split()) > 1 and text.split()[1].startswith('ref_'):
        ref = int(text.split()[1][4:])
        if ref != user_id:
            user = get_user(user_id)
            if user['referred_by'] == 0:
                conn = sqlite3.connect('bot_users.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (ref, user_id))
                cursor.execute('UPDATE users SET bonus_photos = bonus_photos + ? WHERE user_id = ?', (REFERRAL_BONUS, ref))
                cursor.execute('UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?', (ref,))
                conn.commit()
                conn.close()
                bot.send_message(user_id, "🎁 +3 фото/день по рефералке!")
                bot.send_message(ref, "🎉 Новый реферал! +3 фото/день!")
    
    markup, status = main_menu(user_id)
    bot.send_message(message.chat.id,
        f"🤖 *ReshiBot*\n\n"
        f"📸 Отправь фото — решу\n"
        f"✍️ Напиши пример — 2+2\n"
        f"🎲 Случайный пример\n\n"
        f"💎 {status}\n👇",
        parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    if call.data == "menu":
        markup, status = main_menu(user_id)
        bot.edit_message_text(f"🏠 Главное меню\n\n{status}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data == "stats":
        user = get_user(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        used = user['photos_today'] if user['last_date'] == today else 0
        limit = get_user_limit(user)
        text = f"📊 Статистика\n📸 Сегодня: {used}/{limit}\n👥 Рефералов: {user['referral_count']}\n🎁 Бонус: +{user['bonus_photos']}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
    elif call.data == "generate":
        ex, ans = generate_example()
        active_tasks[user_id] = {'example': ex, 'answer': ans}
        bot.edit_message_text(f"🎲 Реши пример\n📝 {ex} = ?\n✍️ Напиши число", call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
    elif call.data == "top":
        top = get_top_users()
        text = "🏆 Топ рефералов\n" + "\n".join([f"{i}. {name} — {cnt}" for i, name, cnt in top]) if top else "🏆 Топ пуст"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
    elif call.data == "referral":
        link = f"https://t.me/{bot.get_me().username}?start=ref_{user_id}"
        bot.edit_message_text(f"👥 Твоя ссылка\n{link}\nЗа каждого друга +3 фото/день", call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
    elif call.data == "buy_premium_light":
        bot.send_invoice(call.message.chat.id, title="⭐ Premium Light", description="10 фото/день", invoice_payload="light", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Light", PREMIUM_LIGHT_PRICE)])
    elif call.data == "buy_premium_pro":
        bot.send_invoice(call.message.chat.id, title="👑 Premium Pro", description="Безлимит фото", invoice_payload="pro", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Pro", PREMIUM_PRO_PRICE)])
    elif call.data == "help":
        bot.edit_message_text("❓ Помощь\n✍️ Напиши 2+2\n📸 Отправь фото", call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    level = 1 if message.successful_payment.invoice_payload == "light" else 2
    update_user(message.from_user.id, premium_level=level)
    bot.send_message(message.chat.id, f"✅ Premium {'Light' if level==1 else 'Pro'} активирован!")

# ===== ОБРАБОТКА ТЕКСТА =====
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
            bot.reply_to(m, f"✅ Верно! {active_tasks[user_id]['example']} = {correct}" if ans == correct else f"❌ Неверно! {active_tasks[user_id]['example']} = {correct}", reply_markup=quick_buttons())
            del active_tasks[user_id]
            return
        except:
            bot.reply_to(m, "❓ Напиши число!", reply_markup=quick_buttons())
            return
    res = simple_calc(text)
    if res is not None:
        bot.reply_to(m, f"✅ {text} = {res}", reply_markup=quick_buttons())
        return
    if not can_upload_photo(user_id):
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} запросов. Купи Premium!", reply_markup=quick_buttons())
        return
    msg = bot.reply_to(m, "🤔 Думаю...")
    ans = ask_gemini(text)
    increment_photo_count(user_id)
    bot.edit_message_text(ans[:2000], m.chat.id, msg.message_id, reply_markup=quick_buttons())

# ===== ОБРАБОТКА ФОТО =====
@bot.message_handler(content_types=['photo'])
def photo_handler(m):
    user_id = m.from_user.id
    if not can_upload_photo(user_id):
        bot.reply_to(m, f"❌ Лимит {FREE_LIMIT} фото. Купи Premium!", reply_markup=quick_buttons())
        return
    msg = bot.reply_to(m, "🔄 Распознаю...")
    file = bot.get_file(m.photo[-1].file_id)
    data = bot.download_file(file.file_path)
    # Сначала OCR
    ocr = requests.post('https://api.ocr.space/parse/image', files={'file': ('img.jpg', data)}, data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2}).json()
    if ocr.get('IsErroredOnProcessing') or not ocr.get('ParsedResults'):
        bot.edit_message_text("❌ Не распознано. Сфоткай чётче.", m.chat.id, msg.message_id)
        return
    parsed = re.sub(r'[^0-9+\-*/()=.\s]', '', ocr['ParsedResults'][0]['ParsedText'].strip())
    if not parsed:
        bot.edit_message_text("❌ Текст не найден.", m.chat.id, msg.message_id)
        return
    # Пробуем калькулятор
    res = simple_calc(parsed)
    if res is not None:
        bot.edit_message_text(f"✅ {parsed} = {res}", m.chat.id, msg.message_id, reply_markup=quick_buttons())
        increment_photo_count(user_id)
        return
    # Если сложное — ИИ
    bot.edit_message_text("🔄 Решаю через ИИ...", m.chat.id, msg.message_id)
    ans = ask_gemini(f"Реши: {parsed}. Пиши ответ кратко.", None)
    increment_photo_count(user_id)
    bot.edit_message_text(f"✅ {ans}", m.chat.id, msg.message_id, reply_markup=quick_buttons())

if __name__ == '__main__':
    init_db()
    print("✅ Бот запущен!")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
