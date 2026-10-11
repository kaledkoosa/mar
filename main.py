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
        f"🔄 سعر الصرف المعتمد: 1$ = {USD_TO_SYP:,} ل.س\n\n"
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
            f"💳 **%D8%AA%D8%B9%D9%84%D9%8A%D9%85%D8%A7%D8%AA الإيداع عبر محفظة شام كاش:**\n\n"
            f"يرجى تحويل المبلغ المراد شحنه بالليرة السورية إلى الحساب التالي:\n"
            f"📞 **رقم المحفظة:** `{SHAM_CASH_NUMBER}`\n"
            f"👤 **اسم صاحب الحساب:** {SHAM_CASH_NAME}\n\n"
            f"⚠️ بعد إتمام التحويل الناجح، أرسل **رقم عملية التحويل** هنا في المحادثة مباشرة."
        )
        bot.send_message(user_id, deposit_instruction, parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_deposit_proof)
        bot.answer_callback_query(call.id)
        
    elif call.data.startswith("approve_"):
        _, dep_id, c_user_id, amount_usd = call.data.split("_")
        dep_id, c_user_id, amount_usd = int(dep_id), int(c_user_id), float(amount_usd)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM deposits WHERE deposit_id = ?", (dep_id,))
        row = cursor.fetchone()
        
        if row and row['status'] == 'PENDING':
            cursor.execute("UPDATE deposits SET status = 'APPROVED' WHERE deposit_id = ?", (dep_id,))
            conn.commit()
            conn.close()
            
            update_user_balance(c_user_id, amount_usd)
            new_balance = get_user_balance(c_user_id)
            
            bot.send_message(c_user_id, f"✅ **تم تأكيد إيداعك بنجاح!**\n💰 أضيف لحسابك: `+{amount_usd:.2f}$`\n💳 رصيدك الإجمالي: `{new_balance:.2f}$`")
            bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=f"🟢 تم قبول طلب الإيداع رقم #{dep_id} بنجاح.")
        else:
            conn.close()
            bot.answer_callback_query(call.id, "هذا الطلب تم معالجته مسبقاً!")
            
    elif call.data.startswith("reject_"):
        _, dep_id, c_user_id = call.data.split("_")
        dep_id, c_user_id = int(dep_id), int(c_user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE deposit_id = ?", (dep_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(c_user_id, "❌ تم رفض طلب الإيداع. يرجى التواصل مع الدعم للتحقق.")
        bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=f"🔴 تم رفض طلب الإيداع رقم #{dep_id} .")

def process_deposit_proof(message):
    user_id = message.from_user.id
    proof_text = message.text
    
    if not proof_text or proof_text.startswith('/'):
        bot.send_message(user_id, "❌ خطأ: يرجى إرسال إشعار تحويل صحيح.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO deposits (user_id, reference_code, amount_syp) VALUES (?, ?, ?)", (user_id, proof_text, 0.0))
    dep_id = cursor.lastrow_id
    conn.commit()
    conn.close()
    
    bot.send_message(user_id, "⏳ جاري مراجعة طلب الإيداع الخاص بك من قِبل الإدارة...")
    
    admin_markup = types.InlineKeyboardMarkup()
    estimated_usd = 5.0 
    
    btn_approve = types.InlineKeyboardButton(text="🟢 قبول (5$)", callback_data=f"approve_{dep_id}_{user_id}_{estimated_usd}")
    btn_reject = types.InlineKeyboardButton(text="🔴 رفض", callback_data=f"reject_{dep_id}_{user_id}")
    admin_markup.add(btn_approve, btn_reject)
    
    admin_notification = (
        f"🚨 **طلب إيداع معلق** 🚨\n\n"
        f"👤 العميل: `{user_id}`\n"
        f"🔢 الإثبات: `{proof_text}`\n\n"
        f"اختر إجراء الإشعار المباشر:"
    )
    bot.send_message(ADMIN_CHAT_ID, admin_notification, reply_markup=admin_markup)

# ==================== مسارات خادم الويب (Flask) ====================

@app.route('/')
def home():
    return "🚀 متجر عبد البصير يعمل بثبات تام وبدون توقف إجباري!", 200

# تصحيح مسار استقبال الـ Webhook بشكل آمن ومحمي لمنع التوقف المبكر
@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    else:
        return jsonify({"error": "Invalid Content-Type"}), 403

@app.route('/shop/<int:user_id>')
def shop_interface(user_id):
    try:
        balance = get_user_balance(user_id)
    except Exception as e:
        return f"Error: {str(e)}"
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except:
        return "Error: index.html not found."
    html_content = html_content.replace("USER_BALANCE_MARKER", str(balance))
    html_content = html_content.replace("USER_ID_MARKER", str(user_id))
    return render_template_string(html_content)

def async_send_order(user_id, item, player_id):
    try:
        admin_msg = (
            f"📥 **طلب مبيعات جديد** 📥\n\n"
            f"👤 المشتري ID: `{user_id}`\n"
            f"📦 الباقة: **{item['name']}**\n"
            f"🆔 اللاعب: `{player_id}`"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg)
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        user_msg = f"🔄 تم خصم {item['price']} دولار وشراء **{item['name']}** بنجاح!\n💰 رصيدك الحالي: {new_balance:.2f}$"
        bot.send_message(user_id, user_msg)
    except Exception as e:
        print(f"Error in async_send_order: {str(e)}")

@app.route('/api/buy', methods=['POST', 'OPTIONS'])
def api_buy_item():
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
# ==================== مسارات الويب وخادم التشغيل ====================

@app.route('/')
def home():
    return "🚀 البوت وخادم الويب يعملان بنجاح وبدون مشاكل!"

# مسار المتجر الإلكتروني الخاص بك (تأكد من تعديله ليناسب مشروعك لاحقاً)
@app.route('/shop/<int:user_id>')
def shop(user_id):
    return f"🛒 مرحباً بك في المتجر الإلكتروني للمستخدم: {user_id}"

def run_flask():
    """تشغيل خادم الويب على المنفذ المطلوب من منصة Render"""
    # جلب المنفذ تلقائياً من نظام ريندر أو استخدام 8080 كافتراضي لتجنب كراش التشغيل
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # 1. تشغيل خادم Flask في خيط معالجة (Thread) منفصل بالخلفية
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🌐 Web Server started in background...")
    print("🤖 Telegram Bot is starting polling...")
    
    # 2. تشغيل البوت بشكل مستمر لحمايته من الانغلاق
    # خيار non_stop=True يضمن إعادة تشغيل البوت تلقائياً في حال انقطع الاتصال للحظات
    bot.infinity_polling(non_stop=True)
