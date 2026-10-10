import telebot
from telebot import types
import psycopg2  
import os
import threading
import json
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات السرية بأمان تام من Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

# 🔒 الرابط السحابي الكوري الحتمي والمباشر المدمج بأعلى معايير التشفير (SSL) للأرصدة
DATABASE_URL = "postgresql://postgres.aeozpoldsypsketsmzym:kaledkoosa12@://supabase.com"

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

PRICES = {
    "pubg_60": {"name": "60 شدة PUBG", "price": 1.0},
    "pubg_325": {"name": "325 شدة PUBG", "price": 5.0},
    "ff_100": {"name": "100 جوهرة Free Fire", "price": 1.0},
    "ff_310": {"name": "310 جوهرة Free Fire", "price": 3.0}
}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, 
                balance REAL DEFAULT 0.0
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ SUCCESS: Database tables connected and created successfully on Supabase (Korea)!")
    except Exception as e:
        print(f"❌ DATABASE ERROR: Connection failed. Reason: {str(e)}")

# إطلاق قنوات الفحص التلقائي للربط عند إقلاع السيرفر
init_db()

def get_user_balance(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (%s, 0.0)", (user_id,))
            conn.commit()
            balance = 0.0
        else:
            balance = row[0]  # استخراج صافي ومضمون لمنع الـ Tuples والانهيار
        cursor.close()
        conn.close()
        return float(balance)
    except Exception as e:
        print(f"Error fetching balance: {str(e)}")
        return 0.0

def update_user_balance(user_id, amount):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (%s, 0.0)", (user_id,))
            conn.commit()
            
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Successfully updated balance for user {user_id} on Cloud.")
    except Exception as e:
        print(f"Error updating balance on Cloud: {str(e)}")

def get_total_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        conn.close()
        return count
    except:
        return 0

# --- استقبال تحديثات الـ Webhook الفورية ---
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
        return f"Error inside database fetching: {str(e)}"
        
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
            f"🆔 **ID اللاعب في اللعبة:** `{player_id}`\n\n"
            f"📌 يرجى الدخول وشحن الباقة فوراً!"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg)
        
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        
        user_msg = f"🔄 تم خصم {item['price']} دولار وشراء **{item['name']}** بنجاح!\n🎮 الـ ID المستهدف للشحن: `{player_id}`\n💰 رصيدك المتبقي الحالي: {new_balance} دولار\n\n⏳ جاري تسليم الشحنة من قبل الإدارة."
        bot.send_message(user_id, user_msg)
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
            return jsonify({"success": False, "message": "عذراً! رصيدك الحالي غير كافٍ لإتمام العملية."})
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
            
        response = jsonify({"success": True})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
    except Exception as e:
        response = jsonify({"success": False, "message": str(e)})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

@app.route('/')
def home():
    return "السيرفر مستقر ويعمل بنجاح كامل على قاعدة بيانات PostgreSQL السحابية الكورية الآمنة للأرصدة!!"

@bot.message_handler(commands=['pay'])
def pay_user_balance(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID:
        try:
            parts = message.text.split()
            if len(parts) < 3:
                bot.send_message(message.chat.id, "⚠️ صيغة الأمر خاطئة! يرجى الكتابة بالشكل التالي:\n\n`/pay [ID المستخدم] [المبلغ]`", parse_mode="Markdown")
                return
            
            target_id = int(parts[1]) 
            amount = float(parts[2])  
            
            update_user_balance(target_id, amount)
            new_balance = get_user_balance(target_id)
            
            bot.send_message(message.chat.id, f"✅ تم بنجاح إضافة **{amount}** دولار للمستخدم `{target_id}` في السحابة الكورية.\n💰 رصيده الثابت الحالي الآن أصبح: **{new_balance}** دولار", parse_mode="Markdown")
            
            try:
                bot.send_message(target_id, f"🎉 أخبار رائعة! تم تأكيد إيداعك وإضافة **{amount}** دولار لحسابك بنجاح.\n💰 رصيدك الحالي بداخل المتجر أصبح: **{new_balance}** دولار", parse_mode="Markdown")
            except:
                pass
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء تنفيذ الأمر. تأكد من صحة الـ ID والمبلغ.\nوصف الخطأ: {str(e)}")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID:
        total_users = get_total_users()
        admin_text = (
            f"👑 **لوحة تحكم الإدارة لمتجر عبد البصير** 👑\n\n"
            f"👥 إجمالي المستخدمين في السحابة الكورية: `{total_users}` مستخدم.\n\n"
            f"💡 **لشحن رصيد مستخدم:**\n"
            f"`/pay [ID المستخدم] [المبلغ]`"
        )
        bot.send_message(message.chat.id, admin_text, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    base_url = RENDER_WEB_URL.strip()
    while base_url.endswith('/'):
        base_url = base_url[:-1]
        
    web_app_url = f"{base_url}/shop/{user_id}"
    
    welcome_text = f"👋 أهلاً بك في متجر عبد البصير للشحن!\n\n💰 رصيدك الحالي المثبّت سحابياً: {balance} دولار\n\nاضغط على الزر الشفاف أدناه لفتح واجهة المتجر وتفعيل أزرار الشراء الفورية الحتمية:"
    
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
    bot.remove_webhook()
    base_url = RENDER_WEB_URL.strip()
    while base_url.endswith('/'):
        base_url = base_url[:-1]
    bot.set_webhook(url=f"{base_url}/{BOT_TOKEN}")
