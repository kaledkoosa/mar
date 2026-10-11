import telebot
from telebot import types
import sqlite3  
import os
import threading
import json
import requests
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات السرية بأمان من Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

# 💳 بيانات محفظة شام كاش الخاصة بك
SHAM_CASH_NUMBER = os.environ.get("SHAM_CASH_NUMBER", "09XXXXXXXX")  
SHAM_CASH_NAME = os.environ.get("SHAM_CASH_NAME", "عبد البصير") 
USD_TO_SYP = float(os.environ.get("USD_TO_SYP", "15000")) 

# تفعيل البوت بدون خيوط معالجة عشوائية مسببة للمشاكل داخلياً
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

PRICES = {
    "pubg_60": {"name": "60 شدة PUBG", "price": 1.0},
    "pubg_325": {"name": "325 شدة PUBG", "price": 5.0},
    "ff_100": {"name": "100 جوهرة Free Fire", "price": 1.0},
    "ff_310": {"name": "310 جوهرة Free Fire", "price": 3.0}
}

DB_FILE = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0)')
        cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (
                            deposit_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            user_id INTEGER, 
                            amount_syp REAL, 
                            reference_code TEXT, 
                            status TEXT DEFAULT 'PENDING')''')
        conn.commit()
        conn.close()
        print("✅ SUCCESS: SQLite Database & Deposit System Initialized!")
    except Exception as e:
        print(f"❌ DATABASE ERROR: {str(e)}")

init_db()

def get_user_balance(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
            conn.commit()
            balance = 0.0
        else:
            balance = row['balance']
        conn.close()
        return float(balance)
    except Exception as e:
        print(f"Error getting balance: {str(e)}")
        return 0.0

def update_user_balance(user_id, amount):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
            conn.commit()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating balance: {str(e)}")
        return False

# ==================== استقبال تحديثات الـ Webhook عبر Flask ====================

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def receive_updates():
    """المسار الذي يستمع لطلبات تليجرام القادمة فور حدوثها"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return jsonify({"error": "Unsupported Media Type"}), 415

@app.route('/')
def home():
    """صفحة رئيسية عامة للتأكد من عمل السيرفر"""
    return "<h1>تطبيق البوت والمتجر يعملان بنجاح على منصة Render!</h1>", 200

# ==================== أقسام التحكم بالبوت (تليجرام) ====================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    welcome_text = (
        f"👋 أهلاً بك في متجر عبد البصير الإلكتروني!\n\n"
        f"🆔 معرفك الشخصي: `{user_id}`\n"
        f"💰 رصيدك الحالي: {balance:.2f} دولار\n"
        f"🔄 سعر الصرف المعتمد: 1\\$ = {USD_TO_SYP:,} ل.س\n\n"
        f"استخدم الأزرار أدناه للتنقل داخل المتجر وشحن حسابك."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    shop_url = f"{RENDER_WEB_URL.strip('/')}/shop/{user_id}"
    web_app = types.WebAppInfo(shop_url)
    
    btn_shop = types.InlineKeyboardButton(text="🛒 فتح المتجر الإلكتروني", web_app=web_app)
    btn_deposit = types.InlineKeyboardButton(text="💵 إيداع رصيد (شام كاش)", callback_data="request_deposit")
    
    markup.add(btn_shop)
    markup.add(btn_deposit)
    
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "request_deposit":
        deposit_instruction = (
            f"💳 **تعليمات الإيداع عبر محفظة شام كاش:**\n\n"
            f"يرجى تحويل المبلغ المراد شحنه بالليرة السورية إلى الحساب التالي:\n"
            f"📞 **رقم المحفظة:** `{SHAM_CASH_NUMBER}`\n"
            f"👤 **اسم صاحب الحساب:** {SHAM_CASH_NAME}\n\n"
            f"⚠️ بعد إتمام التحويل الناجح، أرسل **رقم عملية التحويل** هنا في المحادثة مباشرة."
        )
        bot.send_message(user_id, deposit_instruction, parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_deposit_proof)
        bot.answer_callback_query(call.id)

def process_deposit_proof(message):
    """معالجة رقم الحوالة المرسل من المستخدم"""
    user_id = message.from_user.id
    reference_code = message.text.strip()
    
    # يمكنك هنا إضافة المنطق الخاص بحفظ رقم التحويل وقيمته في قاعدة البيانات وإشعار المسؤول
    bot.reply_to(message, f"✅ تم استلام رقم العملية: `{reference_code}`.\nجاري مراجعتها من قبل الإدارة وسيتم تحديث رصيدك فوراً.", parse_mode="Markdown")

# ==================== تشغيل الويب هوك والسيرفر مًعا ====================

# إزالة أي تعارض قديم وتفعيل الويب هوك بشكل آلي وآمن عند بدء تشغيل الكود
try:
    bot.remove_webhook()
    # تنظيف وتجهيز الرابط الكامل للويب هوك ليطابق المسار الجديد المضاف في السيرفر
    webhook_url = f"{RENDER_WEB_URL.strip('/')}/{BOT_TOKEN}"
    bot.set_webhook(url=webhook_url)
    print(f"🚀 Telegram Webhook successfully set to: {webhook_url}")
except Exception as e:
    print(f"❌ Failed to set Webhook: {str(e)}")

if __name__ == '__main__':
    # تشغيل تطبيق flask الذي سيتكفل باستقبال تحديثات المتجر والبوت معاً
    # تأكد أن منفذ التشغيل (Port) هو 10000 وهو الافتراضي لمنصة Render
    app.run(host='0.0.0.0', port=10000)
