import telebot
from telebot import types
import sqlite3
import os
import threading
import json
from flask import Flask, render_template_string

# --- إعداد سيرفر Flask لاستضافة التطبيق المصغر ومنع النوم ---
app = Flask('')

# قراءة واجهة index.html المرفقة بالمشروع وعرضها ديناميكياً
@app.route('/shop/<int:user_id>')
def shop_interface(user_id):
    # جلب رصيد المستخدم الحالي لعرضه مباشرة في التطبيق المصغر
    balance = get_user_balance(user_id)
    
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except:
        return "خطأ: لم يتم العثور على ملف index.html في سيرفر المشروع."
        
    # تمرير الرصيد للـ Web App عبر الـ URL Query
    html_content = html_content.replace("urlParams.get('balance') || '0.0'", f"'{balance}'")
    return render_template_string(html_content)

@app.route('/')
def home():
    return "التطبيق المصغر والسيرفر يعملان بنجاح 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- إعدادات الحماية والأمان لبوت التيليجرام ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_توكن_البوت_الخاص_بـك_هنا")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "123456789"))
# رابط مشروعك على ريندر (مثال: https://onrender.com) ليفتح التطبيق المصغر من خلاله
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

bot = telebot.TeleBot(BOT_TOKEN)

PAYMENT_METHODS = (
    "💳 **طرق الشحن المتوفرة حالياً:**\n\n"
    "1️⃣ **شام كاش (Sham Cash):**\n"
    "📞 رقم المحفظة: `09xxxxxxxx`\n\n"
    "2️⃣ **عملة رقمية USDT (شبكة BEP20):**\n"
    "🌐 العنوان (Address):\n"
    "`0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n\n"
    "📌 قم بتحويل المبلغ، ثم أرسل **صورة إيصال التحويل** هنا فوراً."
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

# --- أمر البدء /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    # بناء رابط التطبيق المصغر الديناميكي الخاص بالمستخدم
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    
    welcome_text = (
        f"👋 أهلاً بك في متجر شحن الألعاب الفوري الجديد!\n\n"
        f"💰 رصيدك الحالي: {balance} \$\n\n"
        f"اضغط على الزر أدناه لفتح المتجر كمكتبة ألعاب وتطبيق مصغر تفاعلي:"
    )
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # إضافة زر التطبيق المصغر المدمج بداخل الكيبورد الرئيسي للعميل
    markup.add(types.KeyboardButton("🎮 فتح المتجر الإلكتروني", web_app=types.WebAppInfo(url=web_app_url)))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# --- استقبال البيانات المرسلة من التطبيق المصغر (Web App Data) ---
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
            
            # خصم السعر وتأكيد الطلب
            update_user_balance(user_id, -item["price"])
            msg = bot.send_message(chat_id, f"🔄 تم تأكيد شراء {item['name']} وخصم {item['price']}\$ من رصيدك بنجاح.\nالرجاء إرسال الـ ID الخاص بحسابك في اللعبة لتوصيل شحنتك فوراً:")
            bot.register_next_step_handler(msg, lambda m: bot.send_message(chat_id, "✅ تم استلام الـ ID بنجاح، جاري الشحن يدوياً من الإدارة."))
            
        elif action == "deposit":
            msg = bot.send_message(chat_id, PAYMENT_METHODS, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_receipt)
            
    except Exception as e:
        bot.send_message(chat_id, "❌ حدث خطأ أثناء معالجة الطلب من التطبيق المصغر.")

# --- الأزرار التفاعلية للأدمن ---
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    
    if call.data.startswith("deposit_approve_"):
        customer_id = int(call.data.replace("deposit_approve_", ""))
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("+1 \$", callback_data=f"addamt_1_{customer_id}"),
            types.InlineKeyboardButton("+5 \$", callback_data=f"addamt_5_{customer_id}"),
            types.InlineKeyboardButton("+10 \$", callback_data=f"addamt_10_{customer_id}"),
            types.InlineKeyboardButton("+20 \(", callback_data=f"addamt_20_{customer_id}")         )         bot.edit_message_caption(caption="حدد المبلغ المراد شحنه لحساب المستخدم:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)      elif call.data.startswith("addamt_"):         _, amount_str, customer_id = call.data.split("_")         amount = float(amount_str)         customer_id = int(customer_id)                  update_user_balance(customer_id, amount)         new_balance = get_user_balance(customer_id)                  try:             bot.send_message(customer_id, f"🎉 تم تأكيد إيداعك وإضافة **{amount} \$** لحسابك بنجاح!\n💰 رصيدك الحالي أصبح: {new_balance} \)")
        except:
            pass
        
        bot.edit_message_caption(caption=f"✅ تم شحن {amount}\$ بنجاح للمستخدم `{customer_id}`!\n💰 رصيده الحالي الآن أصبح: {new_balance}\$", chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)

    elif call.data.startswith("deposit_reject_"):
        customer_id = int(call.data.replace("deposit_reject_", ""))
        try:
            bot.send_message(customer_id, "❌ نعتذر منك، تم رفض إيصال الشحن الخاص بك من قبل الإدارة.")
        except:
            pass
        bot.edit_message_caption(caption=f"❌ تم رفض إيصال المستخدم {customer_id} بنجاح.", chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)

def process_deposit_receipt(message):
    user_id = message.from_user.id
    if message.content_type != 'photo':
        bot.send_message(message.chat.id, "❌ خطأ! يجب إرسال صورة الإيصال. يرجى إعادة المحاولة.")
        return

    photo_id = message.photo[-1].file_id
    bot.send_message(message.chat.id, "⏳ جاري مراجعة إيصالك من قبل الإدارة الفورية...")
    
    btn_approve = types.InlineKeyboardButton("✅ موافقة", callback_data=f"deposit_approve_{user_id}")
    btn_reject = types.InlineKeyboardButton("❌ رفض", callback_data=f"deposit_reject_{user_id}")
    admin_markup = types.InlineKeyboardMarkup()
    admin_markup.add(btn_approve, btn_reject)
    
    try:
        bot.send_photo(ADMIN_CHAT_ID, photo_id, caption=f"📥 وصل إيصال شحن جديد:\n🆔 ID: `{user_id}`\n👤 الاسم: {message.from_user.first_name}", reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending to admin: {e}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Mini App Server is running successfully...")
    bot.infinity_polling()
