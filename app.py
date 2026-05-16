import telebot
import time
import os
from flask import Flask
import threading

TOKEN = '8352640245:AAFlnxkvrHpW5foObSupcWTb3xOgYSYuujw'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "✅ Бот работает! Привет!")

@bot.message_handler(func=lambda message: True)
def echo(message):
    bot.reply_to(message, f"Ты написал: {message.text}")

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_bot():
    print("✅ Бот запущен!")
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
