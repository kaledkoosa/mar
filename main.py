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

# تفعيل البوت بدون خيوط معالجة عشوائية مسببة للمشاكل
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

# ==================== أقسام التحكم بالبوت (تليجرام) ====================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    welcome_text = (
        f"👋 أهلاً بك في متجر عبد البصير الإلكتروني!\n\n"
        f"🆔 معرفك الشخصي: `{user_id}`\n"
        f"💰 رصيدك الحالي: {balance:.2f} دولار\n"
        f"🔄 سعر الصرف المعتمد: 1\$ = {USD_TO_SYP:,} ل.س\n\n"
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
    """معالجة رقم الحوالة المرسل من المستخدم وإشعار المسؤول"""
    user_id = message.from_user.id
    reference_code = message.text.strip()
    
    # حفظ الإيداع بقاعدة البيانات بحالة انتظار التفعيل PENDING
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO deposits (user_id, reference_code, status) VALUES (?, ?, 'PENDING')", (user_id, reference_code))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, "✅ تم استلام رقم العملية بنجاح! سيقوم المسؤول بمراجعة التحويل وإضافة الرصيد إلى حسابك فوراً.")
        
        # إشعار الأدمن بالعملية الجديدة إذا تم تعيين المعرف
        if ADMIN_CHAT_ID != 0:
            admin_text = f"🚨 **طلب إيداع جديد قيد الانتظار:**\n\n👤 المستخدم: `{user_id}`\n🔢 رقم العملية: `{reference_code}`"
            bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error processing deposit: {str(e)}")
        bot.reply_to(message, "❌ حدث خطأ أثناء حفظ بيانات العملية، يرجى المحاولة لاحقاً.")

# ==================== مسارات الويب وخادم التشغيل ====================

@app.route('/')
def render_home(): 
    # تم تغيير الاسم هنا لمنع التعارض مع أي دالة 'home' أخرى في مشروعك
    return "🚀 خادم الويب والبوت يعملان معاً بنجاح دون أي تضارب!"

@app.route('/shop/<int:user_id>')
def shop(user_id):
    return f"🛒 واجهة المتجر الإلكتروني للمستخدم: {user_id} جاهزة للربط والعمل."

def run_flask():
    """تشغيل خادم الويب على المنفذ المطلوب من منصة Render بشكل ديناميكي"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # 1. تشغيل خادم ويب Flask في الخلفية باستخدام الـ Threads
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🌐 Web Server started in background...")
    print("🤖 Telegram Bot is starting polling...")
    
    # 2. تشغيل البوت بشكل لا نهائي ومستمر لاستقبال الرسائل
    bot.infinity_polling(non_stop=True)
