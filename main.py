import telebot
from telebot import types
import json
import os
import threading
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات البيئية المطابقة لوحتك في Render ---
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

# --- أوامر تيلجرام للعملاء ---
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
        f"💰 رصيدك الحالي: **{balance} $**\n\n"
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

# --- لوحة تحكم المسؤول (Admin) ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    data = load_data()
    total_users = len(data)
    total_balances = sum(data.values())
    
    admin_text = (
        f"⚙️ **لوحة تحكم مدير متجر عبد البصير** ⚙️\n\n"
        f"👥 إجمالي المستخدمين: `{total_users}`\n"
        f"💰 إجمالي الأرصدة المودعة: `{total_balances} $`\n\n"
        f"✍️ صيغة شحن الرصيد المباشر لزبون:\n"
        f"`/pay USER_ID AMOUNT`"
    )
    bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")

@bot.message_handler(commands=['pay', 'deposit'])
def manual_admin_deposit(message):
    if message.chat.id != ADMIN_CHAT_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            raise ValueError()
            
        target_user_id = int(parts[1])
        amount = float(parts[2])
        
        update_user_balance(target_user_id, amount)
        new_balance = get_user_balance(target_user_id)
        
        bot.send_message(ADMIN_CHAT_ID, f"✅ **عملية ناجحة**\n\n👤 العميل: `{target_user_id}`\n➕ تم إضافة: `{amount} $`\n💰 الرصيد الحالي: `{new_balance} $`", parse_mode="Markdown")
        bot.send_message(target_user_id, f"🎉 تم تأكيد دفعتك اليدوية ونزولها في حسابك بنجاح!\n➕ الرصيد المضاف: {amount} $\n💰 رصيدك الإجمالي الحالي: **{new_balance} $**")
    except:
        bot.send_message(ADMIN_CHAT_ID, f"❌ الصيغة الصحيحة: `/pay USER_ID AMOUNT`", parse_mode="Markdown")

# --- نظام معالجة أزرار القبول والرفض للآدمن (تم تصحيح مصفوفة التفكيك الجذري هنا) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_")))
def handle_order_status(call):
    if call.message.chat.id != ADMIN_CHAT_ID:
        return
        
    try:
        parts = call.data.split("_")
        action = parts[0]
        user_id = int(parts[1])
        item_key = parts[2]
        price = float(parts[3])
        player_id = "_".join(parts[4:])
        
        item_name = PRICES.get(item_key, {}).get("name", "باقة رقمية")
        
        if action == "app":
            bot.edit_message_text(
                chat_id=ADMIN_CHAT_ID,
                message_id=call.message.message_id,
                text=f"🟢 **تم تسليم وشحن الطلب بنجاح** 🟢\n\n👤 المشتري ID: `{user_id}`\n📦 الباقة: **{item_name}**\n🆔 معرف اللاعب: `{player_id}`\n\n⚙️ تمت العملية بواسطة الآدمن المعتمد."
            )
            bot.send_message(user_id, f"✅ **بشرى سارة! تم شحن طلبك الآن بنجاح** 🎉\n\n📦 الباقة: **{item_name}**\n🎮 الـ ID المشحون: `{player_id}`\n\nنشكرك على ثقتك بمتجرنا عبد البصير! 🎮✨")
            
        elif action == "rej":
            update_user_balance(user_id, price)
            new_balance = get_user_balance(user_id)
            
            bot.edit_message_text(
                chat_id=ADMIN_CHAT_ID,
                message_id=call.message.message_id,
                text=f"🔴 **تم رفض الطلب وإرجاع الرصيد** 🔴\n\n👤 المشتري ID: `{user_id}`\n📦 الباقة: **{item_name}**\n🆔 معرف اللاعب: `{player_id}`\n\n⚙️ تم الرفض وإعادة `{price} $` لحسابه بنجاح."
            )
            bot.send_message(user_id, f"❌ **تنويه: تم رفض طلب الشحن الخاص بك**\n\n📦 الباقة: **{item_name}**\n🎮 الـ ID المستهدف: `{player_id}`\n\n💰 **ملاحظة:** تم إلغاء العملية وإرجاع مبلغ `{price} $` إلى رصيدك في البوت تلقائياً.")
    except Exception as e:
        print(f"Callback error: {str(e)}")

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
            bot.reply_to(message, "✅ تم استعادة كافة أرصدة المستخدمين بنجاح!")
        except Exception as e:
            bot.reply_to(message, f"❌ فشل: {str(e)}")

# --- ربط واجهات الويب والـ API للتطبيق المصغر ---
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

def async_send_order(user_id, item_key, item, player_id):
    try:
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        
        callback_approve = f"app_{user_id}_{item_key}_{item['price']}_{player_id}"
        callback_reject = f"rej_{user_id}_{item_key}_{item['price']}_{player_id}"
        
        markup = types.InlineKeyboardMarkup()
        btn_approve = types.InlineKeyboardButton(text="✅ قبول وتأكيد الشحن", callback_data=callback_approve)
        btn_reject = types.InlineKeyboardButton(text="❌ رفض الطلب وإرجاع المال", callback_data=callback_reject)
        markup.add(btn_approve, btn_reject)
        
        admin_msg = (
            f"📥 **وصل طلب مبيعات جديد من المتجر المصغر** 📥\n\n"
            f"👤 حساب المشتري ID: `{user_id}`\n"
            f"📦 الباقة المطلوبة: **{item['name']}**\n"
            f"🆔 **ID اللاعب في اللعبة:** `{player_id}`\n\n"
            f"📌 يرجى شحن الـ ID يدوياً داخل اللعبة ثم الضغط على زر التحكم المناسب أدناه لتنبيه الزبون آلياً:"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg, reply_markup=markup, parse_mode="Markdown")
        
        user_msg = (
            f"🔄 **تم استلام طلبك وبانتظار المراجعة**\n\n"
            f"📦 الباقة: **{item['name']}**\n"
            f"🎮 الـ ID المطلوب شحنه: `{player_id}`\n"
            f"💰 رصيدك الحالي بعد الخصم المبدئي: {new_balance} $\n\n"
            f"⏳ جاري مراجعة الشحنة وتنفيذها من قِبل الإدارة فوراً وسيصلك إشعار بنجاح العملية هنا."
        )
