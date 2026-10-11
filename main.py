import telebot
from telebot import types
import sqlite3
import os
import threading
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- المتغيرات البيئية من Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

# --- بيانات الدفع اليدوي عبر شام كاش (تظهر للعملاء) ---
SHAM_CASH_NUMBER = os.environ.get("SHAM_CASH_NUMBER", "0900000000") # رقم حسابك في شام كاش
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Your_Telegram_Username") # معرف حسابك الشخصي لاستقبال الإيصالات

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
        balance = row[0]
    conn.close()
    return float(balance)

def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- لوحة التحكم التفاعلية داخل تيلجرام ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # زر فتح المتجر الإلكتروني كميني آب
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    web_app_info = types.WebAppInfo(web_app_url)
    shop_button = types.InlineKeyboardButton(text="🛒 فتح متجر عبد البصير", web_app=web_app_info)
    
    # زر لعرض معلومات الإيداع اليدوي
    deposit_button = types.InlineKeyboardButton(text="💳 شحن حسابي (شام كاش)", callback_data="deposit_info")
    
    markup.add(shop_button, deposit_button)
    
    welcome_text = (
        f"👋 مرحباً بك في متجر عبد البصير للشحن الفوري!\n\n"
        f"🆔 حسابك: `{user_id}`\n"
        f"💰 رصيدك الحالي: **{balance} \$**\n\n"
        f"تصفح المتجر أو اشحن رصيدك يدوياً عبر الخيارات أدناه 👇"
    )
    bot.send_message(user_id, welcome_text, reply_markup=markup, parse_mode="Markdown")

# التعامل مع ضغط زر الإيداع اليدوي
@bot.callback_query_handler(func=lambda call: call.data == "deposit_info")
def show_deposit_details(call):
    deposit_text = (
        f"⚠️ **خطوات الشحن اليدوي عبر شام كاش:**\n\n"
        f"1️⃣ قم بتحويل المبلغ المطلوب إلى حسابنا في شام كاش:\n"
        f"📱 رقم الحساب: `{SHAM_CASH_NUMBER}`\n\n"
        f"2️⃣ بعد إتمام التحويل، يرجى إرسال لقطة شاشة للإيصال (صورة التحويل) مع ذكر **الـ ID الخاص بك** (`{call.from_user.id}`) إلى الدعم الفني:\n"
        f"👤 الإدارة: @{ADMIN_USERNAME}\n\n"
        f"⚙️ سيقوم المسؤول بمراجعة التحويل وإضافة الرصيد إلى حسابك خلال دقائق!"
    )
    bot.send_message(call.from_user.id, deposit_text, parse_mode="Markdown")

# --- ميزة الإدارة: شحن رصيد الزبائن بأمر من التيلجرام مباشرة ---
# الطريقة: يرسل الآدمن رسالة بهذا الشكل: /deposit 12345678 10 (الآيدي ثم المبلغ)
@bot.message_handler(commands=['deposit'])
def manual_admin_deposit(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return # تجاهل الأمر إذا لم يكن من الآدمن المعتمد
        
    try:
        args = message.text.split()
        target_user_id = int(args[1])
        amount = float(args[2])
        
        update_user_balance(target_user_id, amount)
        new_balance = get_user_balance(target_user_id)
        
        # إشعار الآدمن بالنجاح
        bot.send_message(ADMIN_CHAT_ID, f"✅ تم بنجاح إضافة `{amount} \$` لحساب العميل `{target_user_id}`.\n💰 رصيده الحالي أصبح: {new_balance} \$")
        
        # إشعار العميل تلقائياً بقدوم الرصيد
        bot.send_message(target_user_id, f"🎉 بشرى سارة! تمت الموافقة على دفعتك اليدوية ونزولها في حسابك.\n➕ تم إضافة: {amount} \$\n💰 رصيدك الإجمالي الحالي: **{new_balance} \$**")
    except Exception as e:
        bot.send_message(ADMIN_CHAT_ID, f"❌ خطأ في صيغة الأمر. الصيغة الصحيحة:\n`/deposit USER_ID AMOUNT`\nمثال:\n`/deposit 5522345582 10.5`")

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
        return f"Database Error: {str(e)}"
        
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
            f"📥 **وصل طلب مبيعات جديد من التطبيق المصغر** 📥\n\n"
            f"👤 حساب المشتري ID: `{user_id}`\n"
            f"📦 الباقة المطلوبة: **{item['name']}**\n"
            f"🆔 **ID اللاعب المستهدف:** `{player_id}`"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
        
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        
        user_msg = (
            f"🔄 تم خصم {item['price']} \$ وشراء **{item['name']}** بنجاح!\n"
            f"🎮 الـ ID المشحون: `{player_id}`\n"
            f"💰 رصيدك المتبقي الحالي: {new_balance} \$"
        )
        bot.send_message(user_id, user_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Async Notification Error: {str(e)}")

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
            return jsonify({"success": False, "message": "بيانات الطلب فارغة!"})
            
        user_id = int(data.get("user_id"))
        item_key = data.get("item")
        player_id = data.get("player_id")
        
        item = PRICES.get(item_key)
        if not item:
            return jsonify({"success": False, "message": "الباقة المطلوبة غير مدعومة حالياً."})
            
        balance = get_user_balance(user_id)
        if balance < item["price"]:
            return jsonify({"success": False, "message": "عذراً! رصيدك الحالي غير كافٍ. يرجى الشحن أولاً بالضغط على زر شحن الحساب في البوت."})
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
            
        response = jsonify({"success": True, "message": "تم تسجيل طلبك وجاري شحن اللعبة!"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    except Exception as e:
        response = jsonify({"success": False, "message": f"خطأ داخلي: {str(e)}"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500

@app.route('/')
def home():
    return "Manual Deposit Store Online!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
