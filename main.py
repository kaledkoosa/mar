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
    try:
        balance = get_user_balance(user_id)
    except Exception as e:
        return f"Error inside database fetching: {str(e)}"
        
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
    except:
        return "Error: index.html not found."
    
    # استبدال العلامة بالرصيد المالي المجرد والصافي مباشرة داخل نص الـ HTML
    html_content = html_content.replace("USER_BALANCE_MARKER", str(balance))
    return render_template_string(html_content)

# مسار خلفي (API) متوافق تماماً مع الأزرار الشفافة لاستقبال عمليات الشراء وإرسال الإشعارات
@app.route('/api/buy', methods=['POST'])
def api_buy_item():
    try:
        data = request.json
        user_id = int(data.get("user_id"))
        item_key = data.get("item")
        player_id = data.get("player_id")
        
        item = PRICES.get(item_key)
        if not item:
            return jsonify({"success": False, "message": "الباقة المطلوبة غير مدعومة حالياً."})
            
        balance = get_user_balance(user_id)
        if balance < item["price"]:
            return jsonify({"success": False, "message": "عذراً! رصيدك الحالي غير كافٍ لإتمام العملية."})
            
        # الخصم وتحديث الرصيد الفوري بداخل قاعدة البيانات
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        
        # إشعار العميل بنجاح العملية في شات البوت
        try:
            bot.send_message(user_id, f"🔄 تم خصم {item['price']} \$ وشراء **{item['name']}** بنجاح!\n🎮 الـ ID المستهدف للشحن في اللعبة: `{player_id}`\n💰 رصيدك المتبقي الحالي: {new_balance} \$\n\n⏳ جاري توصيل الشحنات والشدات لحسابك فوراً من الإدارة.")
        except:
            pass

        # إرسال التفاصيل الكاملة للأدمن لتسليم الشحنة يدوياً في اللعبة
        try:
            bot.send_message(ADMIN_CHAT_ID, text=f"📥 **وصل طلب مبيعات جديد من التطبيق المصغر** 📥\n\n👤 حساب المشتري ID: `{user_id}`\n📦 الباقة المطلوبة: **{item['name']}**\n🆔 **ID اللاعب المراد شحنه في اللعبة:** `{player_id}`\n\n📌 يرجى الدخول للعبة وشحن الباقة للـ ID المحدد فوراً!")
        except:
            pass
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/')
def home():
    return "السيرفر والتطبيق المصغر المستقر والآمن يعملان بنجاح ساحق!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# إعدادات التوكن والمعرف الرقمي الموثقة لحسابك الشخصي
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

# فك المصفوفة بشكل صريح للوصول إلى القيمة الرقمية الصافية ومنع خطأ 500
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
        balance = row[0]  # جلب العنصر الأول داخل الـ Tuple لمنع انهيار الـ float
    conn.close()
    return float(balance)

def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_total_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    row = cursor.fetchone()
    count = row[0] if row else 0 
    conn.close()
    return count

@bot.message_handler(commands=['pay'])
def pay_user_balance(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID:
        try:
            parts = message.text.split()
            if len(parts) < 3:
                bot.send_message(message.chat.id, "⚠️ صيغة الأمر خاطئة! يرجى الكتابة بالشكل التالي:\n\n`/pay [ID المستخدم] [المبلغ]`", parse_mode="Markdown")
                return
            
            target_id = int(parts[1]) # أخذ الفهرس الصحيح للمستخدم
            amount = float(parts[2])  # أخذ الفهرس الصحيح للمبلغ
            
            update_user_balance(target_id, amount)
            new_balance = get_user_balance(target_id)
            
            bot.send_message(message.chat.id, f"✅ تم بنجاح إضافة **{amount} \$** للمستخدم `{target_id}`.\n💰 رصيده الحالي الآن أصبح: **{new_balance} \$**", parse_mode="Markdown")
            
            try:
                bot.send_message(target_id, f"🎉 أخبار رائعة! تم تأكيد إيداعك وإضافة **{amount} \$** لحسابك بنجاح.\n💰 رصيدك الحالي بداخل المتجر أصبح: **{new_balance} \$**", parse_mode="Markdown")
            except:
                pass
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء تنفيذ الأمر. تأكد من صحة الـ ID والمبلغ.")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID:
        total_users = get_total_users()
        admin_text = (
            f"👑 **لوحة تحكم الإدارة لمتجر عبد البصير** 👑\n\n"
            f"👥 إجمالي المستخدمين: `{total_users}` مستخدم.\n\n"
            f"💡 **لشحن رصيد مستخدم:**\n"
            f"`/pay [ID المستخدم] [المبلغ]`"
        )
        bot.send_message(message.chat.id, admin_text, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    
    welcome_text = f"👋 أهلاً بك في متجر عبد البصير للشحن!\n\n💰 رصيدك الحالي: {balance} دولار\n\nاضغط على الزر الشفاف أدناه لفتح واجهة المتجر وتفعيل أزرار الشراء الفورية الحتمية:"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 فتح المتجر الإلكتروني", web_app=types.WebAppInfo(url=web_app_url)))
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def process_deposit_receipt(message):
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id
    bot.send_message(message.chat.id, "⏳ تم استلام صورة الإيصال بنجاح. جاري مراجعتها وتأكيدها من قبل الإدارة الفورية لحسابك.")
    try:
        bot.send_photo(ADMIN_CHAT_ID, photo_id, caption=f"📥 وصل إيصال شحن جديد:\n🆔 ID المستخدم لنسخه وشحن حسابه: `{user_id}`\n👤 الاسم: {message.from_user.first_name}\n\nلشحن الرصيد اكتب:\n`/pay {user_id} [المبلغ]`")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Independent Mini App Server is running...")
    
    bot.delete_webhook()
    bot.infinity_polling()
