import telebot
from telebot import types
import sqlite3
import os
import threading
import json
from flask import Flask, render_template_string

app = Flask('')

@app.route('/shop/<int:user_id>')
def shop_interface(user_id):
    balance = get_user_balance(user_id)
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except:
        return "Error: index.html not found."
    html_content = html_content.replace("urlParams.get('balance') || '0.0'", f"'{balance}'")
    return render_template_string(html_content)

@app.route('/')
def home():
    return "السيرفر يعمل بنجاح!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_توكن_البوت_الخاص_بـك_هنا")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "123456789"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)

PAYMENT_METHODS = (
    "💳 طرق الشحن المتوفرة حالياً:\n\n"
    "1️⃣ شام كاش (Sham Cash):\n"
    "📞 رقم المحفظة: 09xxxxxxxx\n\n"
    "2️⃣ عملة رقمية USDT (شبكة BEP20):\n"
    "🌐 العنوان:\n"
    "0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n\n"
    "📌 قم بتحويل المبلغ، ثم أرسل صورة إيصال التحويل هنا فوراً."
)

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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    
    welcome_text = f"👋 أهلاً بك في متجر الشحن الفوري!\n\n💰 رصيدك الحالي: {balance} دولار\n\nاضغط على الزر أدناه لفتح المتجر:"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🎮 فتح المتجر الإلكتروني", web_app=types.WebAppInfo(url=web_app_url)))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get("action")
        if action == "buy":
            item_key = data.get("item")
            item = PRICES[item_key]
            update_user_balance(user_id, -item["price"])
            msg = bot.send_message(chat_id, f"🔄 تم تأكيد شراء {item['name']} وخصم {item['price']} دولار من رصيدك.\nالرجاء إرسال الـ ID الخاص بك الآن للشحن:")
            bot.register_next_step_handler(msg, lambda m: bot.send_message(chat_id, "✅ تم استلام الـ ID بنجاح، جاري الشحن يدوياً."))
        elif action == "deposit":
            msg = bot.send_message(chat_id, PAYMENT_METHODS)
            bot.register_next_step_handler(msg, process_deposit_receipt)
    except Exception as e:
        bot.send_message(chat_id, "❌ حدث خطأ أثناء معالجة الطلب.")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if data.startswith("deposit_approve_"):
        customer_id = data.replace("deposit_approve_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("+1$", callback_data=f"add_1_{customer_id}"),
            types.InlineKeyboardButton("+5$", callback_data=f"add_5_{customer_id}"),
            types.InlineKeyboardButton("+10$", callback_data=f"add_10_{customer_id}"),
            types.InlineKeyboardButton("+20$", callback_data=f"add_20_{customer_id}")
        )
        bot.edit_message_caption(caption="حدد المبلغ المراد شحنه لحساب المستخدم:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        
    elif data.startswith("add_"):
        parts = data.split("_")
        amount = float(parts[1])
        customer_id = int(parts[2])
        update_user_balance(customer_id, amount)
        new_balance = get_user_balance(customer_id)
        try:
            bot.send_message(customer_id, f"🎉 تم إضافة {amount} دولار لحسابك بنجاح!\n💰 رصيدك الحالي أصبح: {new_balance} دولار")
        except:
            pass
        bot.edit_message_caption(caption=f"✅ تم شحن {amount} دولار للمستخدم {customer_id}.\n💰 رصيده الآن: {new_balance} دولار", chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)
        
    elif data.startswith("deposit_reject_"):
        customer_id = int(data.replace("deposit_reject_", ""))
        try:
            bot.send_message(customer_id, "❌ نعتذر منك، تم رفض إيصال الشحن الخاص بك من قبل الإدارة.")
        except:
            pass
        bot.edit_message_caption(caption=f"❌ تم رفض إيصال المستخدم {customer_id}.", chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)

def process_deposit_receipt(message):
    user_id = message.from_user.id
    if message.content_type != 'photo':
        bot.send_message(message.chat.id, "❌ خطأ! يجب إرسال صورة الإيصال.")
        return
    photo_id = message.photo[-1].file_id
    bot.send_message(message.chat.id, "⏳ جاري مراجعة إيصالك من قبل الإدارة...")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ موافقة", callback_data=f"deposit_approve_{user_id}"),
        types.InlineKeyboardButton("❌ رفض", callback_data=f"deposit_reject_{user_id}")
    )
    try:
        bot.send_photo(ADMIN_CHAT_ID, photo_id, caption=f"📥 وصل شحن جديد:\n🆔 ID: {user_id}\n👤 الاسم: {message.from_user.first_name}", reply_markup=markup)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Server is starting...")
    bot.infinity_polling()
