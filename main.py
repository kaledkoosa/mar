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
SHAM_CASH_NAME = os.environ.get("SHAM_CASH_NAME", "اسم صاحب الحساب") 
USD_TO_SYP = float(os.environ.get("USD_TO_SYP", "15000")) 

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
        conn.commit()
        conn.close()
        print("✅ SUCCESS: SQLite Database Initialized Successfully!")
    except Exception as e:
        print(f"❌ DATABASE ERROR: {str(e)}")

# تشغيل قاعدة البيانات المحلية فوراً وبدون خوادم خارجية
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

# 🛠️ إضافة الاستجابة لأمر /start الذي كان مفقوداً
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.user_id if hasattr(message.from_user, 'user_id') else message.chat.id
    balance = get_user_balance(user_id)
    
    welcome_text = (
        f"👋 أهلاً بك في متجر عبد البصير الإلكتروني!\n\n"
        f"🆔 معرفك الشخصي: `{user_id}`\n"
        f"💰 رصيدك الحالي: {balance} دولار\n\n"
        f"اضغط على الزر أدناه لفتح واجهة المتجر وشحن الألعاب مباشرة."
    )
    
    # إنشاء زر يفتح المتجر كـ WebApp داخل تليجرام
    markup = types.InlineKeyboardMarkup()
    shop_url = f"{RENDER_WEB_URL.strip('/')}/shop/{user_id}"
    web_app = types.WebAppInfo(shop_url)
    markup.add(types.InlineKeyboardButton(text="🛒 فتح المتجر الإلكتروني", web_app=web_app))
    
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode="Markdown")

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
    html_content = html_content.replace("USER_BALANCE_MARKER", str(balance))
    html_content = html_content.replace("USER_ID_MARKER", str(user_id))
    return render_template_string(html_content)

def async_send_order(user_id, item, player_id):
    try:
        admin_msg = (
            f"📥 **وصل طلب مبيعات جديد** 📥\n\n"
            f"👤 حساب المشتري ID: `{user_id}`\n"
            f"📦 الباقة: **{item['name']}**\n"
            f"🆔 **ID اللاعب:** `{player_id}`"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg)
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        user_msg = f"🔄 تم خصم {item['price']} دولار وشراء **{item['name']}** بنجاح!\n🎮 الـ ID: `{player_id}`\n💰 رصيدك المتبقي: {new_balance} دولار"
        bot.send_message(user_id, user_msg)
    except Exception as e:
        print(f"Error in async_send_order: {str(e)}")

@app.route('/api/buy', methods=['POST', 'OPTIONS'])
def api_buy_item():
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Accept")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response
    
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "بيانات فارغة!"}), 400
            
        user_id = data.get("user_id")
        item_id = data.get("item_id")
        player_id = data.get("player_id")
        
        if not user_id or not item_id or not player_id:
            return jsonify({"success": False, "message": "جميع الحقول مطلوبة!"}), 400
            
        item = PRICES.get(item_id)
        if not item:
            return jsonify({"success": False, "message": "المنتج غير موجود!"}), 404
            
        balance = get_user_balance(user_id)
        if balance < item["price"]:
            return jsonify({"success": False, "message": "رصيدك غير كافٍ لإتمام هذه العملية!"}), 400
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
        
        response = jsonify({"success": True, "message": "تم تقديم طلبك بنجاح وجاري معالجته!"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 200

    except Exception as e:
        print(f"Error in api_buy_item: {str(e)}")
        response = jsonify({"success": False, "message": "حدث خطأ داخلي في الخادم!"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

# --- دالة ربط البوت برابط الاستضافة (Webhook) تلقائياً عند التشغيل ---
def set_webhook():
    try:
        # حذف أي ربط قديم أولاً للتهيئة الإجبارية
        bot.remove_webhook()
        webhook_url = f"{RENDER_WEB_URL.strip('/')}/{BOT_TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"🌐 Webhook successfully set to: {webhook_url}")
    except Exception as e:
        print(f"❌ Failed to set webhook: {str(e)}")

if __name__ == "__main__":
    # تشغيل ربط الـ Webhook في خيط منفصل لتجنب عرقلة إقلاع خادم الفلاسك
    threading.Thread(target=set_webhook).start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
