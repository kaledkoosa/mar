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
        bot.send_message(target_user_id, f"🎉 تم تأكيد دفعتك اليدوية ونزولها في حسابك بنجاح!\n➕ الرصيد المضاف: {amount} \(\n💰 رصيدك الإجمالي الحالي: {new_balance} \)", parse_mode="Markdown")
        
    except ValueError:
        bot.send_message(ADMIN_CHAT_ID, "⚠️ **خطأ في الصيغة المستخدمة!**\n\nيرجى استخدام الصيغة الصحيحة تماماً:\n`/pay USER_ID AMOUNT`", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(ADMIN_CHAT_ID, f"❌ حدث خطأ غير متوقع أثناء المعالجة:\n`{str(e)}`", parse_mode="Markdown")
