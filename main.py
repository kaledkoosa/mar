import telebot
from telebot import types
import psycopg2  
import os
import threading
import json
import requests
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات السرية بأمان تام من Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# 💳 بيانات محفظة شام كاش الخاصة بك استقبال الأموال
SHAM_CASH_NUMBER = os.environ.get("SHAM_CASH_NUMBER", "09XXXXXXXX")  # ضع رقم حسابك هنا
SHAM_CASH_NAME = os.environ.get("SHAM_CASH_NAME", "اسم صاحب الحساب") # اسم الحساب الثنائي أو الثلاثي
USD_TO_SYP = float(os.environ.get("USD_TO_SYP", "15000")) # سعر صرف الدولار مقابل الليرة السورية داخل البوت

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
        cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, balance REAL DEFAULT 0.0)')
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ SUCCESS: Connected to Database!")
    except Exception as e:
        print(f"❌ DATABASE ERROR: {str(e)}")

if DATABASE_URL:
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
            balance = row[0]
        cursor.close()
        conn.close()
        return float(balance)
    except Exception as e:
        print(f"Error getting balance: {str(e)}")
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
        return True
    except Exception as e:
        print(f"Error updating balance: {str(e)}")
        return False

@app.route('/')
def home():
    return "🚀 سيرفر متجر عبد البصير يعمل بنجاح بنظام إيداع شام كاش اليدوي!", 200

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
            return jsonify({"success": False, "message": "بيانات فارغة!"})
            
        user_id = int(data.get("user_id"))
        item_key = data.get("item")
        player_id = data.get("player_id")
        
        item = PRICES.get(item_key)
        if not item:
            return jsonify({"success": False, "message": "العنصر غير موجود!"})
            
        current_balance = get_user_balance(user_id)
        if current_balance < item["price"]:
            return jsonify({"success": False, "message": "عذراً، رصيدك غير كافٍ لإتمام هذه العملية! يرجى شحن حسابك أولاً."})
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
        return jsonify({"success": True, "message": "جاري معالجة طلبك بنجاح!"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"حدث خطأ في النظام: {str(e)}"})

# --- معالجة أمر بدء التشغيل والترحيب (/start) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user_id = message.chat.id
        user_name = message.from_user.first_name if message.from_user.first_name else "عزيزي"
        
        welcome_text = (
            f"👋 أهلاً بك يا {user_name} في **متجر عبد البصير لشحن الألعاب لسوريا**!\n\n"
            f"🛒 شحن فوري وآمن لشدات ببجي وجواهر فري فاير بالليرة السورية عبر شام كاش.\n\n"
            f"🆔 حسابك الرقمي: `{user_id}`\n\n"
            f"اضغط على الزر أدناه لشراء المنتجات، أو اختر شحن الرصيد من الأزرار المتاحة 👇"
        )
        
        user_shop_url = f"{RENDER_WEB_URL}/shop/{user_id}"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        shop_button = types.InlineKeyboardButton(text="🛍️ فتح المتجر الإلكتروني", web_app=types.WebAppInfo(url=user_shop_url))
        deposit_button = types.InlineKeyboardButton(text="💳 شحن رصيد حسابي (شام كاش)", callback_data="sham_cash_deposit")
        
        markup.add(shop_button, deposit_button)
        bot.send_message(user_id, text=welcome_text, reply_markup=markup, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error in start command: {str(e)}")

# --- التعامل مع ضغطة زر شحن الرصيد من قبل العميل ---
@bot.callback_query_handler(func=lambda call: call.data == "sham_cash_deposit")
def process_deposit_click(call):
    try:
        user_id = call.message.chat.id
        deposit_instruction = (
            f"🇸🇾 **تعليمات الشحن اليدوي عبر محفظة شام كاش:**\n\n"
            f"1️⃣ قم بالتحويل إلى رقم المحفظة التالي:\n"
            f"📞 الرقم: `{SHAM_CASH_NUMBER}`\n"
            f"👤 الاسم: **{SHAM_CASH_NAME}**\n\n"
            f"2️⃣ قيمة الصرف المعتمدة في المتجر:\n"
            f"💵 **1 دولار متجر = {int(USD_TO_SYP):,} ليرة سورية**\n\n"
            f"3️⃣ بعد إتمام التحويل الناجح من تطبيقك، يرجى **إرسال رقم العملية (المرجع) في رسالة نصية مباشرة للبوت هنا**، أو إرسال صورة واضحة لإيصال التحويل لإتمام تأكيد طلبك."
        )
        # فتح مرحلة انتظار استقبال إشعار الشحن من العميل
        msg = bot.send_message(user_id, text=deposit_instruction, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_receipt_submission)
    except Exception as e:
        print(f"Error in deposit callback: {str(e)}")

# دالة استقبال إثبات التحويل المالي من العميل وإرساله للآدمن
def process_receipt_submission(message):
    try:
        user_id = message.chat.id
        user_name = message.from_user.first_name
        
        admin_markup = types.InlineKeyboardMarkup()
        # زر مدمج للموافقة الفورية من قبل الآدمن وإضافة الرصيد يدويًا
        # سيقوم الأمر بتهيئة نص جاهز لتسريع عملية الشحن
        approve_button = types.InlineKeyboardButton(text="✅ موافقة وشحن الحساب", callback_data=f"admin_approve_prompt_{user_id}")
        admin_markup.add(approve_button)

        admin_alert_text = (
            f"🚨 **إشعار تحويل مالي جديد (شام كاش)** 🚨\n\n"
            f"👤 العميل: {user_name}\n"
            f"🆔 معرف العميل ID: `{user_id}`\n"
        )

        if message.content_type == 'text':
            admin_alert_text += f"📝 **نص الإرسال (رقم العملية):** {message.text}"
            bot.send_message(ADMIN_CHAT_ID, text=admin_alert_text, reply_markup=admin_markup, parse_mode="Markdown")
        elif message.content_type == 'photo':
            photo_id = message.photo[-1].file_id
            admin_alert_text += f"📸 **العميل أرسل صورة إشعار التحويل المرفقة.**"
            bot.send_photo(ADMIN_CHAT_ID, photo=photo_id, caption=admin_alert_text, reply_markup=admin_markup, parse_mode="Markdown")
        else:
            bot.send_message(user_id, "❌ صيغة غير مدعومة. يرجى إرسال رقم العملية كنص أو صورة الإيصال فقط.")
            return

        bot.send_message(user_id, "⏳ تم إرسال إثبات التحويل الخاص بك إلى إدارة المتجر بنجاح. سيتم مراجعة الطلب وإضافة الرصيد إلى حسابك فوراً بمجرد التأكيد.")
    except Exception as e:
        print(f"Error in process_receipt: {str(e)}")

# معالجة تفاعل الآدمن مع طلبات الشحن
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_approve_prompt_"))
def admin_prompt_amount(call):
    if call.message.chat.id != ADMIN_CHAT_ID:
        return
    try:
        target_user_id = call.data.split("_")[-1]
        msg = bot.send_message(ADMIN_CHAT_ID, f"يرجى كتابة القيمة المراد إضافتها لحساب المستخدم `{target_user_id}` **بالدولار** مباشرة (مثال: 5 أو 1.5):")
        bot.register_next_step_handler(msg, lambda m: execute_admin_deposit(m, target_user_id))
    except Exception as e:
        print(f"Error in admin prompt: {str(e)}")

