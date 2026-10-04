import telebot
from telebot import types
import sqlite3
import os
import threading
import json
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

@app.route('/shop/<int:user_id>')
def shop_interface(user_id):
    balance = get_user_balance(user_id)
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except:
        return "Error: index.html not found."
    
    # حقن الرموز والمغيرات البرمجية لتتكامل لوحة التحكم بداخل التطبيق المصغر
    html_content = html_content.replace("USER_BALANCE_MARKER", str(balance))
    html_content = html_content.replace("USER_ID_MARKER", str(user_id))
    html_content = html_content.replace("ADMIN_ID_MARKER", str(ADMIN_CHAT_ID))
    return render_template_string(html_content)

# استقبال ومعالجة عمليات الشراء وشحن رصيد المستخدمين كلياً من داخل واجهة الويب المصغرة
@app.route('/api/action', methods=['POST'])
def handle_api_action():
    data = request.json
    try:
        user_id = int(data.get("user_id"))
        action = data.get("action")
        
        if action == "buy":
            item_key = data.get("item")
            player_id = data.get("player_id")
            item = PRICES[item_key]
            
            # خصم قيمة الباقة من حساب المشترك
            update_user_balance(user_id, -item["price"])
            new_balance = get_user_balance(user_id)
            
            # تشغيل إشعارات تيليجرام في Threads منفصلة وآمنة تماماً
            threading.Thread(target=notify_purchase, args=(user_id, item, player_id, new_balance)).start()
            
        elif action == "admin_pay" and user_id == ADMIN_CHAT_ID:
            target_id = int(data.get("target_id"))
            amount = float(data.get("amount"))
            
            update_user_balance(target_id, amount)
            threading.Thread(target=notify_deposit, args=(target_id, amount)).start()

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"status": "error"}), 500

def notify_purchase(user_id, item, player_id, new_balance):
    try:
        # إشعار العميل بنجاح الخصم والشراء
        bot.send_message(user_id, f"🎉 تم تأكيد شراء **{item['name']}** بنجاح واقتطاع {item['price']}\$ من رصيدك.\n🎮 الـ ID المستهدف للشحن: `{player_id}`\n💰 رصيدك المتبقي الحالي في المتجر: {new_balance}\$\n\n⏳ جاري توصيل الشحنات والشدات لحسابك في اللعبة فوراً من الإدارة.")
        
        # إرسال إشعار فوري وتفصيلي للأدمن ببيانات عملية الشراء لتوصيل الشحنة يدوياً في اللعبة
        bot.send_message(ADMIN_CHAT_ID, f"📥 **طلب شحن جديد قادم من التطبيق المصغر** 📥\n\n👤 حساب المشتري ID: `{user_id}`\n📦 الباقة المطلوبة: **{item['name']}**\n🆔 **ID اللاعب المراد شحنه في اللعبة:** `{player_id}`\n\n📌 يرجى الدخول للعبة وشحن الباقة للـ ID المحدد فوراً!")
    except Exception as e:
        print(f"Telegram Notify Purchase Error: {e}")

def notify_deposit(target_id, amount):
    try:
        new_balance = get_user_balance(target_id)
        bot.send_message(target_id, f"🎉 بشرى سارة! تم تأكيد إيداعك وإضافة **{amount} \$** لحسابك بنجاح عن طريق الإدارة.\n💰 رصيدك الحالي بداخل المتجر أصبح: **{new_balance} \$**")
    except Exception as e:
        print(f"Telegram Notify Deposit Error: {e}")

@app.route('/')
def home():
    return "السيرفر والتطبيق المصغر المستقل بالكامل يعملان بأعلى كفاءة ومزامنة تامة!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_توكن_البوت_الخاص_بـك_هنا")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "123456789"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

PRICES = {
    "pubg_60": {"name": "60 شدة PUBG", "price": 1.0},
    "pubg_325": {"name": "325 شدة PUBG", "price": 5.0},
    "ff_100": {"name": "100 جوهرة Free Fire", "price": 1.0},
    "ff_310": {"name": "310 جوهرة Free Fire", "price": 3.0}
}

DB_PATH = "/data/manual_shop.db" if os.path.exists("/data") else "manual_shop.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0)')
    conn.commit()
    conn.close()

init_db()

# --- دالة جلب الرصيد الآمنة والمعدلة كلياً لمنع الأخطاء الداخلية ---
def get_user_balance(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        balance = 0.0
    else:
        # التأكد من فك كائن الـ Tuple بأمان سواء كان مصفوفة أو رقماً مجرداً
        balance = row[0] if isinstance(row, (tuple, list)) else row
    conn.close()
    return float(balance)

def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    
    welcome_text = f"👋 أهلاً بك في متجر عبد البصير للشحن الكامل المطور!\n\n💰 رصيدك الحالي: {balance} دولار\n\nاضغط على الزر الشفاف أدناه لفتح واجهة المتجر المستقلة كلياً وبوابة الشحن مدمجة:"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 فتح المتجر الإلكتروني", web_app=types.WebAppInfo(url=web_app_url)))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def process_deposit_receipt(message):
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id
    bot.send_message(message.chat.id, "⏳ تم استلام صورة الإيصال بنجاح. جاري مراجعتها وتأكيدها من قبل الإدارة الفورية لحسابك.")
    try:
        bot.send_photo(ADMIN_CHAT_ID, photo_id, caption=f"📥 وصل إيصال شحن جديد:\n🆔 ID المستخدم لنسخه وشحن حسابه بداخل التطبيق المصغر: `{user_id}`\n👤 الاسم: {message.from_user.first_name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Independent Mini App Server is running...")
    
    bot.delete_webhook()
    bot.infinity_polling()
