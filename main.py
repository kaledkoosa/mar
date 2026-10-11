import telebot
from telebot import types
import json
import os
import threading
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات البيئية المطابقة للوحتك في Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Your_Telegram_Username")

SHAM_CASH_NUMBER = os.environ.get("SHAM_CASH_NUMBER", "0900000000")
SHAM_CASH_NAME = os.environ.get("SHAM_CASH_NAME", "عبد البصير")
USD_TO_SYP = os.environ.get("USD_TO_SYP", "15000")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

PRICES = {
    "pubg_60": {"name": "60 شدة PUBG", "price": 1.0},
    "pubg_325": {"name": "325 شدة PUBG", "price": 5.0},
    "ff_100": {"name": "100 جوهرة Free Fire", "price": 1.0},
    "ff_310": {"name": "310 جوهرة Free Fire", "price": 3.0}
}

DATA_FILE = "users_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    try:
        with open(DATA_FILE, "rb") as f:
            bot.send_document(ADMIN_CHAT_ID, f, caption="💾 نسخة احتياطية تلقائية ومحدثة لأرصدة المتجر.")
    except:
        pass

def get_user_balance(user_id):
    data = load_data()
    uid_str = str(user_id)
    if uid_str not in data:
        data[uid_str] = 0.0
        save_data(data)
    return float(data[uid_str])

def update_user_balance(user_id, amount):
    data = load_data()
    uid_str = str(user_id)
    if uid_str not in data:
        data[uid_str] = 0.0
    data[uid_str] = round(data[uid_str] + amount, 2)
    save_data(data)

# --- أوامر تيلجرام ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    web_app_url = f"{RENDER_WEB_URL}/shop/{user_id}"
    web_app_info = types.WebAppInfo(web_app_url)
    shop_button = types.InlineKeyboardButton(text="🛒 فتح متجر عبد البصير", web_app=web_app_info)
    deposit_button = types.InlineKeyboardButton(text="💳 شحن حسابي (شام كاش)", callback_data="deposit_info")
    
    markup.add(shop_button, deposit_button)
    
    welcome_text = (
        f"👋 مرحباً بك في متجر عبد البصير للشحن الفوري!\n\n"
        f"🆔 حسابك: `{user_id}`\n"
        f"💰 رصيدك الحالي: **{balance} \$**\n\n"
        f"اضغط على الخيارات أدناه لتصفح المتجر أو تعبئة رصيدك يدويّاً 👇"
    )
    bot.send_message(user_id, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "deposit_info")
def show_deposit_details(call):
    deposit_text = (
        f"⚠️ **خطوات الشحن اليدوي عبر شام كاش:**\n\n"
        f"1️⃣ قم بتحويل قيمة الرصيد المطلوبة بحساب (الدولار المحتسب بـ {USD_TO_SYP} ل.س):\n"
        f"📱 رقم محفظة شام كاش: `{SHAM_CASH_NUMBER}`\n"
        f"👤 اسم صاحب الحساب: **{SHAM_CASH_NAME}**\n\n"
        f"2️⃣ بعد التحويل، التقط صورة للإيصال وأرسلها مع الـ ID الخاص بك (`{call.from_user.id}`) إلى الدعم الفني فوراً لرفع رصيدك:\n"
        f"👤 حساب الإدارة للتفعيل: @{ADMIN_USERNAME}\n\n"
        f"⚙️ يتم التحقق وتأكيد الرصيد يدوياً من الإدارة خلال دقائق قليلة."
    )
    bot.send_message(call.from_user.id, deposit_text, parse_mode="Markdown")

# ⭐ تفعيل أمر /admin لعرض لوحة تحكم المسؤول والإحصائيات
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    
    data = load_data()
    total_users = len(data)
    total_balances = sum(data.values())
    
    admin_text = (
        f"⚙️ **لوحة تحكم مدير متجر عبد البصير** ⚙️\n\n"
        f"👥 إجمالي المستخدمين المسجلين: `{total_users}`\n"
        f"💰 إجمالي الأرصدة المودعة حالياً: `{total_balances} \$`\n\n"
        f"📥 **طريقة شحن رصيد لزبون:**\n"
        f"استخدم أمر `/pay` أو `/deposit` متبوعاً بالـ ID ثم المبلغ.\n"
        f"✍️ صيغة الأمر الصحيحة:\n"
        f"`/pay 5522345582 10`\n"
        f"أو\n"
        f"`/deposit 5522345582 10`"
    )
    bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")

# ⭐ تعديل وتصحيح أمر إضافة الرصيد ليدعم كلا اللفظين /pay و /deposit وبدون أخطاء
@bot.message_handler(commands=['pay', 'deposit'])
def manual_admin_deposit(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
        
    try:
        # تقسيم الرسالة النصية بشكل آمن مدمج
        parts = message.text.split()
        if len(parts) < 3:
            raise ValueError("صيغة ناقصة")
            
        target_user_id = int(parts[1])
        amount = float(parts[2])
        
        update_user_balance(target_user_id, amount)
        new_balance = get_user_balance(target_user_id)
        
        bot.send_message(ADMIN_CHAT_ID, f"✅ **عملية ناجحة**\n\n👤 العميل: `{target_user_id}`\n➕ تم إضافة: `{amount} \$`\n💰 الرصيد الحالي: `{new_balance} \$`", parse_mode="Markdown")
        bot.send_message(target_user_id, f"🎉 تم تأكيد دفعتك اليدوية ونزولها في حسابك بنجاح!\n➕ الرصيد المضاف: {amount} \$\n💰 رصيدك الإجمالي الحالي: **{new_balance} \$**")
    except Exception as e:
        bot.send_message(ADMIN_CHAT_ID, f"❌ **خطأ في صيغة الأمر!**\n\nيرجى الكتابة تماماً كالتالي:\n`/pay USER_ID AMOUNT`\n\nمثال شحن 10 دولار:\n`/pay 5522345582 10`", parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_backup_restore(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    if message.document.file_name == DATA_FILE:
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with open(DATA_FILE, "wb") as f:
                f.write(downloaded_file)
            bot.reply_to(message, "✅ تم استعادة كافة أرصدة وبيانات المستخدمين بنجاح من ملف النسخة الاحتياطية!")
        except Exception as e:
            bot.reply_to(message, f"❌ فشل استعادة الملف: {str(e)}")

@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/shop/<int:user_id>')
def shop_interface(user_id):
    balance = get_user_balance(user_id)
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
        return response

    try:
        data = request.json
        user_id = int(data.get("user_id"))
        item_key = data.get("item")
        player_id = data.get("player_id")
        
        item = PRICES.get(item_key)
        balance = get_user_balance(user_id)
        if balance < item["price"]:
            return jsonify({"success": False, "message": "عذراً! رصيدك غير كافٍ."})
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
        return jsonify({"success": True, "message": "تم تسجيل طلبك!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/')
def home():
    return "All commands are working flawlessly!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
