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
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return "Бот работает ✅"

# 🔐 Авторизация Google Sheets
creds_json = os.getenv("GOOGLE_CREDENTIALS")
creds_dict = json.loads(creds_json)
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
spreadsheet = client.open_by_key(SHEET_ID)

# 🤖 Телеграм бот
TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN)

# 🔒 Доступ
ALLOWED_USERS = [476791477, 1388487185]
REPORT_CHAT_IDS = [476791477, 1388487185]

CATEGORIES = {
    "Еда": ["еда", "манты", "кафе", "обед", "продукты", "ужин"],
    "Транспорт": ["такси", "автобус", "бензин", "транспорт", "проезд"],
    "Коммуналка": ["свет", "газ", "жкх", "интернет", "вода", "коммуналка", "кварплата"],
    "Развлечения": ["кино", "игра", "театр", "развлечения"],
    "Другое": []
}

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
        return spreadsheet.worksheet(month_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=month_name, rows="1000", cols="10")
        ws.append_row(["Дата", "Категория", "Сумма", "Комментарий"])
        return ws

# === Автоотчёты ===
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

# === Планировщик ===
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

# === Обработчики Telegram ===
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
        bot.reply_to(message, f"📊 Отчёт:\nСегодня ({today}) — {today_sum} ₸\nЗа месяц — {month_sum} ₸")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка в /report: {e}")

@bot.message_handler(func=lambda m: True)
def add_or_auto(message):
    if message.chat.id not in ALLOWED_USERS:
        bot.reply_to(message, "⛔ У вас нет доступа к этому боту.")
        return
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

# === Keep-alive ping ===
def keep_alive_ping():
    while True:
        try:
            url = os.getenv("RENDER_URL", "https://budgbot.onrender.com")
            requests.get(url)
            print(f"🔄 Keep-alive ping {url}")
        except Exception as e:
            print(f"⚠️ Ошибка keep-alive: {e}")
        time.sleep(600)

threading.Thread(target=keep_alive_ping, daemon=True).start()

# === Запуск ===
if __name__ == "__main__":
    # запускаем бота только в основном процессе (во избежание 409 Conflict)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
        print("🤖 Бот запущен параллельно с Flask")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))