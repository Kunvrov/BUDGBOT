import os
import json
import telebot
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import re
import threading
import time
import schedule
import calendar
from flask import Flask

# 🔑 Google Sheets через переменные окружения
creds_json = os.getenv("GOOGLE_CREDENTIALS")
creds_dict = json.loads(creds_json)
creds = Credentials.from_service_account_info(creds_dict)
client = gspread.authorize(creds)

# 📄 открываем таблицу
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
spreadsheet = client.open_by_key(SHEET_ID)

# 🤖 Telegram Bot
TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN)

print("✅ Бот запущен. Жду сообщений...")

# Flask-заглушка для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# Категории
CATEGORIES = {
    "Еда": ["еда", "манты", "кафе", "обед", "продукты", "ужин"],
    "Транспорт": ["такси", "автобус", "бензин", "транспорт", "проезд"],
    "Коммуналка": ["свет", "газ", "жкх", "интернет", "вода", "коммуналка", "кварплата"],
    "Развлечения": ["кино", "игра", "театр", "развлечения"],
    "Другое": []
}

ALLOWED_USERS = [476791477, 1388487185]
REPORT_CHAT_IDS = [476791477, 1388487185]

def send_to_all(text):
    for chat_id in REPORT_CHAT_IDS:
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            print(f"⚠️ Ошибка отправки в {chat_id}: {e}")

def detect_category(text):
    text_lower = text.lower()
    for category, keywords in CATEGORIES.items():
        for word in keywords:
            if word in text_lower:
                return category
    return "Другое"

def get_current_worksheet():
    month_name = datetime.now().strftime("%B")
    try:
        worksheet = spreadsheet.worksheet(month_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=month_name, rows="1000", cols="10")
        worksheet.append_row(["Дата", "Категория", "Сумма", "Комментарий"])
    return worksheet

# ======= Автоотчёты =======
def send_daily_report():
    try:
        worksheet = get_current_worksheet()
        today = datetime.now().strftime("%d.%m.%Y")
        all_records = worksheet.get_all_values()[1:]
        today_sum = sum(int(row[2]) for row in all_records if row[0] == today)
        send_to_all(f"🌙 Вечерний отчёт за {today}:\nПотратили сегодня — {today_sum} ₸")
    except Exception as e:
        send_to_all(f"⚠️ Ошибка в ежедневном отчёте: {e}")

def send_weekly_report():
    try:
        worksheet = get_current_worksheet()
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        all_records = worksheet.get_all_values()[1:]
        week_sum = 0
        for row in all_records:
            date_obj = datetime.strptime(row[0], "%d.%m.%Y")
            if week_ago <= date_obj <= today:
                week_sum += int(row[2])
        send_to_all(f"📅 Итог за неделю (до {today.strftime('%d.%m.%Y')}):\n{week_sum} ₸")
    except Exception as e:
        send_to_all(f"⚠️ Ошибка в недельном отчёте: {e}")

def send_monthly_report():
    try:
        worksheet = get_current_worksheet()
        today = datetime.now()
        month = today.strftime("%m.%Y")
        all_records = worksheet.get_all_values()[1:]
        month_sum = sum(int(row[2]) for row in all_records if month in row[0])
        send_to_all(f"📊 Итог за месяц {today.strftime('%B')}:\n{month_sum} ₸")
    except Exception as e:
        send_to_all(f"⚠️ Ошибка в месячном отчёте: {e}")

# ======= Планировщик =======
schedule.every().day.at("22:00").do(send_daily_report)
schedule.every().sunday.at("22:30").do(send_weekly_report)
schedule.every().day.at("23:59").do(
    lambda: send_monthly_report() if datetime.now().day == calendar.monthrange(datetime.now().year, datetime.now().month)[1] else None
)

def schedule_checker():
    while True:
        schedule.run_pending()
        time.sleep(30)

threading.Thread(target=schedule_checker, daemon=True).start()

# ======= Команды =======
@bot.message_handler(commands=['id'])
def send_id(message):
    bot.reply_to(message, f"Ваш chat_id: {message.chat.id}")

@bot.message_handler(commands=['report'])
def report(message):
    if message.chat.id not in ALLOWED_USERS:
        bot.reply_to(message, "⛔ У вас нет доступа к этому боту.")
        return
    try:
        worksheet = get_current_worksheet()
        today = datetime.now().strftime("%d.%m.%Y")
        month = datetime.now().strftime("%m.%Y")
        all_records = worksheet.get_all_values()[1:]
        today_sum = sum(int(row[2]) for row in all_records if row[0] == today)
        month_sum = sum(int(row[2]) for row in all_records if month in row[0])
        bot.reply_to(message,
            f"📊 Отчёт:\n"
            f"Сегодня ({today}) — {today_sum} ₸\n"
            f"За месяц — {month_sum} ₸")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка в /report: {e}")

@bot.message_handler(func=lambda m: True)
def add_or_auto(message):
    if message.chat.id not in ALLOWED_USERS:
        bot.reply_to(message, "⛔ У вас нет доступа к этому боту.")
        return
    print(f"📩 Получено сообщение: {message.text} от {message.chat.id}")
    if message.text.startswith("/add"):
        try:
            parts = message.text.split(maxsplit=3)
            category = parts[1]
            amount = parts[2]
            comment = parts[3] if len(parts) > 3 else ""
        except:
            bot.reply_to(message, "⚠️ Формат: /add Категория Сумма Комментарий")
            return
    else:
        try:
            amount_match = re.search(r'\d+', message.text)
            if not amount_match:
                bot.reply_to(message, "⚠️ Укажи сумму.")
                return
            amount = amount_match.group()
            comment = message.text.replace(amount, "").strip()
            category = detect_category(message.text)
        except:
            bot.reply_to(message, "⚠️ Не понял сообщение. Попробуй формат: /add Категория Сумма Комментарий")
            return
    today = datetime.now().strftime("%d.%m.%Y")
    worksheet = get_current_worksheet()
    worksheet.append_row([today, category, amount, comment])
    bot.reply_to(message, f"✅ Запись: {category} — {amount} ₸ ({comment})")

# Запуск Flask и бота
if __name__ == "__main__":
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
