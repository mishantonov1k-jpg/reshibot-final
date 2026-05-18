import telebot
import requests
import sqlite3
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import time
import random

# ===== НАСТРОЙКИ =====
TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
OCR_API_KEY = 'K85192594388957'

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
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=0)
        return True
    limit = get_user_limit(user)
    if user['photos_today'] < limit:
        return True
    return False

def increment_photo_count(user_id):
    user = get_user(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    if user['last_date'] != today:
        update_user(user_id, photos_today=1)
    else:
        update_user(user_id, photos_today=user['photos_today'] + 1)

def solve_math(text):
    text = text.replace('×', '*').replace('÷', '/').replace('^', '**')
    text = text.replace(',', '.').replace(' ', '')
    if not re.match(r'^[\d\s\+\-\*\/\(\)\=\.\^]+$', text):
        return None, "❌ Неверный формат. Пиши числа и знаки: 2+2, 15*3, (4+2)/3"
    try:
        result = eval(text)
        return result, f"📐 {text} = {result}"
    except ZeroDivisionError:
        return None, "❌ Деление на ноль!"
    except:
        return None, "❌ Не могу решить. Проверь пример."

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
    cursor.execute('''
        SELECT user_id, username, referral_count 
        FROM users 
        WHERE referral_count > 0 
        ORDER BY referral_count DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    top_list = []
    for i, row in enumerate(rows, 1):
        user_id, username, count = row
        if not username:
            username = str(user_id)
        top_list.append((i, username, count))
    return top_list

def quick_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    btn_generate = InlineKeyboardButton("🎲 Случайный пример", callback_data="generate")
    btn_stats = InlineKeyboardButton("📊 Мои фото", callback_data="stats")
    btn_menu = InlineKeyboardButton("🏠 Главное меню", callback_data="menu")
    markup.add(btn_generate, btn_stats, btn_menu)
    return markup

def main_menu(user_id):
    user = get_user(user_id)
    if user['premium_level'] == 2:
        status = "👑 Premium Pro (безлимит)"
    elif user['premium_level'] == 1:
        status = "🌟 Premium Light (10 фото/день)"
    else:
        status = "🔓 Бесплатный (4 фото/день)"
    bonus_text = ""
    if user['bonus_photos'] > 0:
        bonus_text = f"\n🎁 Бонус: +{user['bonus_photos']} фото/день"
    markup = InlineKeyboardMarkup(row_width=2)
    btn_stats = InlineKeyboardButton("📊 Мои фото", callback_data="stats")
    btn_generate = InlineKeyboardButton("🎲 Случайный пример", callback_data="generate")
    btn_top = InlineKeyboardButton("🏆 Топ пользователей", callback_data="top")
    btn_ref = InlineKeyboardButton("👥 Привести друга", callback_data="referral")
    btn_premium_light = InlineKeyboardButton("⭐ Premium Light (25⭐)", callback_data="buy_premium_light")
    btn_premium_pro = InlineKeyboardButton("👑 Premium Pro (50⭐)", callback_data="buy_premium_pro")
    btn_help = InlineKeyboardButton("❓ Помощь", callback_data="help")
    markup.add(btn_stats, btn_generate, btn_top, btn_ref, btn_premium_light, btn_premium_pro, btn_help)
    return markup, status + bonus_text

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    text = message.text.strip()
    username = message.from_user.username or ''
    update_user(user_id, username=username)
    if len(text.split()) > 1:
        ref_code = text.split()[1]
        if ref_code.startswith('ref_'):
            referrer_id = int(ref_code.replace('ref_', ''))
            if referrer_id != user_id:
                user = get_user(user_id)
                if user['referred_by'] == 0:
                    conn = sqlite3.connect('bot_users.db')
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer_id, user_id))
                    cursor.execute('UPDATE users SET bonus_photos = bonus_photos + ? WHERE user_id = ?', 
                                   (REFERRAL_BONUS, referrer_id))
                    cursor.execute('UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?', 
                                   (referrer_id,))
                    conn.commit()
                    conn.close()
                    bot.send_message(message.chat.id, 
                                     "🎁 Поздравляю!\n\nТы перешёл по реферальной ссылке!\nТы получил бесплатный Premium на 3 дня в подарок!")
                    bot.send_message(referrer_id, 
                                     f"🎉 Новый реферал!\n\nПользователь {message.from_user.first_name} перешёл по твоей ссылке!\nТы получил +{REFERRAL_BONUS} дополнительных фото навсегда!")
    markup, status = main_menu(user_id)
    welcome_text = (
        f"🚀 Добро пожаловать в ReshiBot!\n\n"
        f"Я решаю математические примеры двумя способами:\n\n"
        f"📸 Отправь фото — я распознаю и решу\n"
        f"✍️ Напиши пример текстом — например: 15*3 или (2+2)*4\n\n"
        f"💎 Твой статус: {status}\n\n"
        f"👇 Нажми на кнопку ниже"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    if call.data == "menu":
        markup, status = main_menu(user_id)
        bot.edit_message_text(f"🏠 Главное меню\n\nТвой статус: {status}", call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    elif call.data == "stats":
        user = get_user(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        used = user['photos_today'] if user['last_date'] == today else 0
        limit = get_user_limit(user)
        text = f"📊 Твоя статистика\n\n📸 Сегодня использовано: {used}/{limit}\n"
        if user['bonus_photos'] > 0:
            text += f"🎁 Бонусных фото: +{user['bonus_photos']}\n"
        text += f"👥 Привёл друзей: {user['referral_count']}\n\n"
        if user['premium_level'] == 2:
            text += "👑 Premium Pro — безлимит"
        elif user['premium_level'] == 1:
            text += "🌟 Premium Light — 10 фото/день"
        else:
            text += "🔓 Бесплатный режим\n\nКупи Premium для увеличения лимита!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
        bot.answer_callback_query(call.id)
    elif call.data == "generate":
        example, answer = generate_example()
        active_tasks[user_id] = {'example': example, 'answer': answer}
        bot.edit_message_text(f"🎲 Реши пример!\n\n📝 {example} = ?\n\n✍️ Напиши свой ответ в чат (только число).", call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
        bot.answer_callback_query(call.id)
    elif call.data == "top":
        top_users = get_top_users(10)
        if not top_users:
            text = "🏆 Топ пользователей\n\nПока никого нет. Приводи друзей и стань первым! 🚀"
        else:
            text = "🏆 Топ пользователей по рефералам\n\n"
            for i, username, count in top_users:
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
                text += f"{medal} {i}. @{username} — {count} {'друг' if count == 1 else 'друзей'}\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
        bot.answer_callback_query(call.id)
    elif call.data == "referral":
        bot_name = bot.get_me().username
        ref_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
        text = f"👥 Приведи друга!\n\n🔗 Твоя реферальная ссылка:\n{ref_link}\n\n🎁 Что ты получишь:\n• +{REFERRAL_BONUS} дополнительных фото в день за каждого друга\n• 10% от покупки Premium твоего реферала\n\n🎁 Что получит друг:\n• Бесплатный Premium на 3 дня\n\nПросто отправь ссылку друзьям!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
        bot.answer_callback_query(call.id)
    elif call.data == "buy_premium_light":
        bot.send_invoice(call.message.chat.id, title="⭐ Premium Light", description="10 фото в день, доступ навсегда", invoice_payload="premium_light_payload", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Light", PREMIUM_LIGHT_PRICE)])
    elif call.data == "buy_premium_pro":
        bot.send_invoice(call.message.chat.id, title="👑 Premium Pro", description="Безлимит фото, приоритетная обработка, доступ навсегда", invoice_payload="premium_pro_payload", provider_token="", currency="XTR", prices=[telebot.types.LabeledPrice("Premium Pro", PREMIUM_PRO_PRICE)])
    elif call.data == "help":
        help_text = (
            "❓ Как пользоваться ботом\n\n"
            "1️⃣ Написать пример текстом\nПросто напиши: 2+2, 15*3, (4+2)/3\n\n"
            "2️⃣ Отправить фото\nСфоткай пример из учебника и отправь боту\n\n"
            "3️⃣ Случайный пример\nНажми кнопку — бот даст задание, а ты напиши ответ\n\n"
            "4️⃣ Купить Premium\n⭐ Light (25 звёзд) — 10 фото/день\n👑 Pro (50 звёзд) — безлимит\n\n"
            "5️⃣ Привести друга\nНажми кнопку «Привести друга» и делись ссылкой"
        )
        bot.edit_message_text(help_text, call.message.chat.id, call.message.message_id, reply_markup=quick_buttons())
        bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def handle_payment(message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    user = get_user(user_id)
    if payload == "premium_light_payload":
        update_user(user_id, premium_level=1)
        if user['referred_by'] != 0:
            commission = int(PREMIUM_LIGHT_PRICE * REFERRAL_INCOME_PERCENT / 100)
            add_referral_income(user['referred_by'], commission)
            bot.send_message(user['referred_by'], f"🎉 Твой реферал купил Premium Light!\nТы получил +{commission} дополнительных фото!")
        bot.send_message(message.chat.id, "✅ Premium Light активирован!\n\nТеперь ты можешь отправлять 10 фото в день. Спасибо за поддержку! ⭐")
    elif payload == "premium_pro_payload":
        update_user(user_id, premium_level=2)
        if user['referred_by'] != 0:
            commission = int(PREMIUM_PRO_PRICE * REFERRAL_INCOME_PERCENT / 100)
            add_referral_income(user['referred_by'], commission)
            bot.send_message(user['referred_by'], f"🎉 Твой реферал купил Premium Pro!\nТы получил +{commission} дополнительных фото!")
        bot.send_message(message.chat.id, "✅ Premium Pro активирован!\n\nТеперь у тебя безлимит фото. Спасибо за поддержку! 👑")

# ===== ОБРАБОТКА ТЕКСТА =====
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if text.startswith('/'):
        return
    username = message.from_user.username or ''
    update_user(user_id, username=username)
    if user_id in active_tasks:
        task = active_tasks[user_id]
        try:
            user_answer = int(text)
            correct_answer = task['answer']
            if user_answer == correct_answer:
                response = f"✅ Правильно!\n\nПример: {task['example']} = {correct_answer}\n🎉 Отлично!"
            else:
                response = f"❌ Неправильно!\n\nПример: {task['example']} = {correct_answer}\nТвой ответ: {user_answer}\n\nПопробуй следующий пример!"
            del active_tasks[user_id]
            bot.reply_to(message, response, reply_markup=quick_buttons())
            return
        except ValueError:
            bot.reply_to(message, "❓ Пожалуйста, напиши число — твой ответ на пример.", reply_markup=quick_buttons())
            return
    if re.search(r'[\d\+\-\*\/\(\)\=]', text):
        result, solution = solve_math(text)
        if result is not None:
            response = f"✅ Решено!\n\n{solution}"
            bot.reply_to(message, response, reply_markup=quick_buttons())
        else:
            bot.reply_to(message, solution, reply_markup=quick_buttons())
    else:
        markup, status = main_menu(user_id)
        bot.reply_to(message, f"🤔 Я не распознал математический пример.\n\nПопробуй:\n• 15*3\n• (2+2)*4\n• Или отправь фото примера\n\nТвой статус: {status}", reply_markup=markup)

# ===== ОБРАБОТКА ФОТО =====
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    if not can_upload_photo(user_id):
        user = get_user(user_id)
        limit = get_user_limit(user)
        markup, _ = main_menu(user_id)
        bot.reply_to(message, f"❌ Лимит фото исчерпан!\n\nСегодня использовано: {user['photos_today']}/{limit}\n\nКупи Premium или приведи друга для увеличения лимита 👇", reply_markup=markup)
        return
    msg = bot.reply_to(message, "🔄 Распознаю и решаю...")
    file_info = bot.get_file(message.photo[-1].file_id)
    file = bot.download_file(file_info.file_path)
    response = requests.post(
        'https://api.ocr.space/parse/image',
        files={'file': ('image.jpg', file)},
        data={'apikey': OCR_API_KEY, 'language': 'rus', 'OCREngine': 2}
    )
    result = response.json()
    if result.get('IsErroredOnProcessing') or not result.get('ParsedResults'):
        bot.edit_message_text("❌ Не удалось распознать текст\n\nПопробуй:\n• Сфотографировать чётче\n• Написать пример текстом", message.chat.id, msg.message_id)
        return
    parsed_text = result['ParsedResults'][0]['ParsedText'].strip()
    parsed_text = re.sub(r'[^0-9+\-*/()=.\s]', '', parsed_text)
    if not parsed_text:
        bot.edit_message_text("❌ Текст не найден на фото\n\nПопробуй написать пример текстом", message.chat.id, msg.message_id)
        return
    answer, solution = solve_math(parsed_text)
    if answer is None:
        bot.edit_message_text(f"❌ Не удалось решить\n\nРаспознано: {parsed_text[:100]}\n\n{solution}", message.chat.id, msg.message_id)
    else:
        increment_photo_count(user_id)
        user = get_user(user_id)
        limit = get_user_limit(user)
        if user['premium_level'] == 2:
            remaining_text = "👑 Premium Pro — безлимит"
        elif user['premium_level'] == 1:
            remaining = limit - user['photos_today']
            remaining_text = f"🌟 Premium Light — осталось: {remaining}/10 фото"
        else:
            remaining = limit - user['photos_today']
            remaining_text = f"🔓 Бесплатно — осталось: {remaining}/{FREE_LIMIT} фото"
            if user['bonus_photos'] > 0:
                remaining_text += f"\n🎁 Бонус за рефералов: +{user['bonus_photos']}"
        bot.edit_message_text(f"✅ Решено!\n\n{solution}\n\n{remaining_text}", message.chat.id, msg.message_id, reply_markup=quick_buttons())

# ===== ЗАПУСК =====
if __name__ == '__main__':
    init_db()
    print("✅ Бот запущен!")
    print("📍 Поддерживаются:")
    print("   - Текстовый ввод примеров (2+2)")
    print("   - Фото с примерами (через OCR)")
    print("   - Premium Light (25⭐) → 10 фото/день")
    print("   - Premium Pro (50⭐) → безлимит")
    print("   - Реферальная система → +3 фото за друга")
    print("   - Генератор с проверкой ответов")
    print("   - Топ пользователей по рефералам")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
