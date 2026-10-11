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

# 💳 بيانات محفظة شام كاش الخاصة بك (تُجلب من إعدادات Render أو القيم الافتراضية أدناه)
SHAM_CASH_NUMBER = os.environ.get("SHAM_CASH_NUMBER", "09XXXXXXXX")  
SHAM_CASH_NAME = os.environ.get("SHAM_CASH_NAME", "عبد البصير") 
USD_TO_SYP = float(os.environ.get("USD_TO_SYP", "15000")) # سعر صرف الدولار مقابل الليرة السورية بالمتجر

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

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
        # إنشاء جدول لإدارة عمليات الإيداع المعلقة وضمان عدم تكرارها
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

# معالجة طلبات الأزرار الشفافة (Callback)
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "request_deposit":
        # إرسال بيانات الشحن للمستخدم وطريقة التحويل
        deposit_instruction = (
            f"💳 **تعليمات الإيداع عبر محفظة شام كاش:**\n\n"
            f"يرجى تحويل المبلغ المراد شحنه بالليرة السورية إلى الحساب التالي:\n"
            f"📞 **رقم المحفظة:** `{SHAM_CASH_NUMBER}`\n"
            f"👤 **اسم صاحب الحساب:** {SHAM_CASH_NAME}\n\n"
            f"⚠️ بعد إتمام التحويل الناجح، أرسل **رقم عملية التحويل** أو **رقم الإشعار** هنا في المحادثة مباشرة ليتم مراجعته وإضافة الرصيد لحسابك بالدولار."
        )
        bot.send_message(user_id, deposit_instruction, parse_mode="Markdown")
        # نقل حالة المستخدم لانتظار الإثبات
        bot.register_next_step_handler(call.message, process_deposit_proof)
        bot.answer_callback_query(call.id)
        
    elif call.data.startswith("approve_"):
        # معالجة موافقة الأدمن على الإيداع
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
            
            # تحديث الرصيد للمستخدم وإخطاره
            update_user_balance(c_user_id, amount_usd)
            new_balance = get_user_balance(c_user_id)
            
            bot.send_message(c_user_id, f"✅ **تهانينا!** تم تأكيد إيداعك بنجاح.\n💰 أضيف لحسابك: `+{amount_usd:.2f}$`\n💳 رصيدك الإجمالي الآن: `{new_balance:.2f}$`")
            bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=f"🟢 تم قبول طلب الإيداع رقم #{dep_id} وإضافة الرصيد بنجاح.")
        else:
            conn.close()
            bot.answer_callback_query(call.id, "هذا الطلب تم معالجته مسبقاً!")
            
    elif call.data.startswith("reject_"):
        # معالجة رفض الأدمن للطلب
        _, dep_id, c_user_id = call.data.split("_")
        dep_id, c_user_id = int(dep_id), int(c_user_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE deposit_id = ?", (dep_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(c_user_id, "❌ نأسف، تم رفض طلب الإيداع الخاص بك. يرجى التواصل مع الدعم للتأكد من بيانات التحويل ورقم العملية.")
        bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=f"🔴 تم رفض طلب الإيداع رقم #{dep_id} بنجاح.")

def process_deposit_proof(message):
    user_id = message.from_user.id
    proof_text = message.text
    
    if not proof_text or proof_text.startswith('/'):
        bot.send_message(user_id, "❌ خطأ: يرجى إرسال رقم إشعار عملية تحويل صحيح بدون الرموز العامة للتحكم.")
        return

    # حفظ الطلب معلقاً بقاعدة البيانات
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO deposits (user_id, reference_code, amount_syp) VALUES (?, ?, ?)", (user_id, proof_text, 0.0))
    dep_id = cursor.lastrow_id
    conn.commit()
    conn.close()
    
    bot.send_message(user_id, "⏳ تم إرسال إشعار وإثبات التحويل الخاص بك إلى الإدارة بنجاح. سيتم مراجعة الطلب وإضافة الرصيد فوراً.")
    
    # إرسال إشعار فوري للأدمن لاتخاذ الإجراء (قبول أو رفض من أزرار التحكم)
    admin_markup = types.InlineKeyboardMarkup()
    # لنفرض أن الشحن الافتراضي المتاح للتجربة أو المراجعة سيتم تقديره، أو يكتبه الأدمن، الكود هنا يحتسب الرصيد افتراضياً بانتظار تحديد القيمة أو إضافتها بذكاء
    # هنا سنقوم بطلب تحديد قيمة تقريبية أو اعتماد إيداع ثابت بقيمة 1$ كبداية أو يتيح للأدمن التحقق منها. لسهولة الأتمتة سنفرض الإيداع محدد القيمة عبر المراجعة:
    # لغايات برمجية سريعة سنضع قيمة تجريبية 5 دولارات أو يمكن تعديلها لاحقاً حسب نظام الأسعار
    estimated_usd = 5.0 
    
    btn_approve = types.InlineKeyboardButton(text="🟢 قبول وشحن (5$)", callback_data=f"approve_{dep_id}_{user_id}_{estimated_usd}")
    btn_reject = types.InlineKeyboardButton(text="🔴 رفض الطلب", callback_data=f"reject_{dep_id}_{user_id}")
    admin_markup.add(btn_approve, btn_reject)
    
    admin_notification = (
        f"🚨 **طلب إيداع معلق جديد** 🚨\n\n"
        f"👤 معرف العميل: `{user_id}`\n"
        f"🔢 إثبات التحويل المستلم: `{proof_text}`\n"
        f"🆔 رقم الطلب الداخلي: #{dep_id}\n\n"
        f"تأكد من تطبيق شام كاش الخاص بك أولاً، ثم اضغط على الإجراء المناسب:"
    )
    bot.send_message(ADMIN_CHAT_ID, admin_notification, reply_markup=admin_markup)

# ==================== مسارات خادم الويب (Flask) ====================

@app.route('/')
def home():
    return "🚀 متجر عبد البصير يعمل بنجاح تام وبأعلى استقرار عبر خادم SQLite المحلي!", 200

@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

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
