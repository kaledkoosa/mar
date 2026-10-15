import os
import random
from fastapi import FastAPI, Request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "[09xxxxxxxx]")
CWALLET_ACCOUNT_ID = os.getenv("CWALLET_ID", "[رقم المعرف غير مضاف]")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = FastAPI()

# تهيئة سوبابيس المستقرة
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# الذاكرة المؤقتة لخطوات المستخدمين داخل الشات
user_sessions = {}

# قائمة الألعاب والأسعار والكميات (تمت إعادة الـ 100 جوهرة فري فاير)
games_menu = {
    "pubg": {
        "name": "ببجي موبايل (PUBG MOBILE)",
        "packages": {"60 شدة": "1", "325 شدة": "5", "660 شدة": "10"}
    },
    "ff": {
        "name": "فري فاير (FREE FIRE)",
        "packages": {"100 جوهرة": "1", "210 جوهرة": "2", "530 جوهرة": "5"}
    }
}

payment_details = {
    "shamcash": {"name": "شام كاش (ShamCash)", "msg": f"يرجى التحويل إلى حساب شام كاش رقم: `{SHAM_CASH_NUM}`"},
    "cwallet": {"name": "محفظة CWallet (يدوي)", "msg": f"💡 *توفير الرسوم:* يرجى التحويل الداخلي المجاني (0 رسوم) داخل تطبيق CWallet إلى المعرف الخاص بنا:\n\n👉 معرف الحساب (CWallet ID): `{CWALLET_ACCOUNT_ID}`"}
}

@app.get("/ping")
def ping_server():
    return {"status": "alive", "msg": "إشعار نشاط تلقائي لمنع النوم"}

@app.post(f"/{BOT_TOKEN}/")
async def process_webhook(request: Request):
    json_string = await request.body()
    update = telebot.types.Update.de_json(json_string.decode('utf-8'))
    bot.process_new_updates([update])
    return {"status": "ok"}

# 1. أمر البداية مع دعم روابط الإحالة وعرض الألعاب
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    user_sessions[user_id] = {}

    # التحقق من وجود كود إحالة في الرابط (مثال: /start ref_123456)
    referred_by = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('ref_'):
        ref_id = args[1].replace('ref_', '')
        if ref_id != user_id:  # منع المستخدم من إحالة نفسه
            referred_by = ref_id

    try:
        # جلب المستخدم للتأكد إذا كان مسجلاً مسبقاً لمنع تكرار الإحالات لشخص قديم
        user_check = supabase.table("users").select("user_id").eq("user_id", user_id).execute()
        
        if not user_check.data:
            supabase.table("users").insert({
                "user_id": user_id,
                "username": message.from_user.username or "N/A",
                "full_name": message.from_user.first_name or "N/A",
                "referred_by": referred_by,
                "balance": 0.0
            }).execute()
        else:
            supabase.table("users").update({
                "username": message.from_user.username or "N/A",
                "full_name": message.from_user.first_name or "N/A"
            }).eq("user_id", user_id).execute()
            
    except Exception as e:
        print(f"Supabase Error: {e}")

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🎮 ببجي موبايل (PUBG MOBILE)", callback_data="game_pubg"),
        InlineKeyboardButton("🔥 فري فاير (FREE FIRE)", callback_data="game_ff")
    )
    bot.reply_to(message, "👋 مرحباً بك في متجر شحن الألعاب السريع والأكثر استقراراً!\n\n🕹️ من فضلك اختر اللعبة المستهدفة من الأزرار أدناه للبدء:\n\n🔗 للحصول على رابط إحالتك الخاص اكتب أمر: /share", reply_markup=markup)

# أمر توليد ومشاركة رابط الإحالة
@bot.message_handler(commands=['share'])
def share_referral(message):
    user_id = str(message.from_user.id)
    bot_info = bot.get_me()
    ref_link = f"https://t.me{bot_info.username}?start=ref_{user_id}"
    
    try:
        user_data = supabase.table("users").select("balance").eq("user_id", user_id).execute()
        balance = user_data.data[0]["balance"] if user_data.data else 0.0
    except:
        balance = 0.0

    msg = (
        f"🔗 **رابط الإحالة الخاص بك:**\n`{ref_link}`\n\n"
        f"💰 **نظام الأرباح:** شارك الرابط مع أصدقائك، وستحصل على عمولة قدرها **0.01$** تلقائياً عن كل صديق يقوم بأول عملية شحن ناجحة من البوت!\n\n"
        f"💳 رصيدك الحالي من الإحالات: **{balance}$**"
    )
    bot.reply_to(message, msg)

# 2. معالجة اختيار اللعبة وعرض الباقات والأسعار
@bot.callback_query_handler(func=lambda call: call.data.startswith('game_'))
def handle_game_selection(call):
    user_id = str(call.from_user.id)
    game_key = call.data.split('_')[1]
    
    user_sessions[user_id] = {"game_key": game_key, "game_name": games_menu[game_key]["name"]}
    
    markup = InlineKeyboardMarkup(row_width=1)
    for pkg, price in games_menu[game_key]["packages"].items():
        markup.add(InlineKeyboardButton(f"💎 {pkg} ── {price} دولار", callback_data=f"pkg_{pkg}_{price}"))
        
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"📦 ممتاز! لقد اخترت: *{games_menu[game_key]['name']}*\n\n📥 الآن، اختر كمية الشحن والسعر المناسب لك:", reply_markup=markup, parse_mode="Markdown")

# 3. معالجة اختيار الباقة وطلب الـ Player ID
@bot.callback_query_handler(func=lambda call: call.data.startswith('pkg_'))
def handle_package_selection(call):
    user_id = str(call.from_user.id)
    if user_id not in user_sessions or not user_sessions[user_id]:
        bot.send_message(call.message.chat.id, "❌ انتهت الجلسة، يرجى كتابة /start من جديد.")
        return
        
    data_parts = call.data.split('_')
    pkg_name = data_parts[1]
    price = data_parts[2]
    
    user_sessions[user_id]["package"] = pkg_name
    user_sessions[user_id]["price"] = price
    user_sessions[user_id]["step"] = "WAITING_ID"
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"🆔 حزمة الاختيار: *{pkg_name}* بسعر *{price} دولار*\n\n✍️ من فضلك، قم بكتابة وإرسال معرف اللاعب (Player ID) الخاص بك هنا في المحادثة مباشرة:")

# 4. استقبال الـ Player ID وعرض وسائل الدفع
@bot.message_handler(func=lambda message: user_sessions.get(str(message.from_user.id), {}).get("step") == "WAITING_ID")
def handle_player_id(message):
    user_id = str(message.from_user.id)
    player_id = message.text.strip()
    
    user_sessions[user_id]["player_id"] = player_id
    user_sessions[user_id]["step"] = "WAITING_PAYMENT"
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💳 شحن عبر شام كاش (ShamCash)", callback_data="pay_shamcash"),
        InlineKeyboardButton("💰 محفظة CWallet", callback_data="pay_cwallet")
    )
    bot.reply_to(message, f"🎯 معرف اللاعب: `{player_id}`\n\n👇 اختر وسيلة الدفع المناسبة لإتمام الشحن:", reply_markup=markup)

# 5. معالجة اختيار وسيلة الدفع وطلب إثبات التحويل
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def handle_payment_selection(call):
    user_id = str(call.from_user.id)
    if user_id not in user_sessions or not user_sessions[user_id]:
        bot.send_message(call.message.chat.id, "❌ انتهت الجلسة، يرجى كتابة /start من جديد.")
        return
        
    pay_key = call.data.split('_')[1]
    user_sessions[user_id]["payment_key"] = pay_key
    user_sessions[user_id]["payment_name"] = payment_details[pay_key]["name"]
    user_sessions[user_id]["step"] = "WAITING_PROOF"
    
    msg_text = payment_details[pay_key]["msg"]
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"{msg_text}\n\n📸 بعد إتمام التحويل، **قم بإرسال صورة الإشعار (لقطة الشاشة)** هنا مباشرة لتأكيد طلبك:")

# 6. استقبال إشعار الدفع وإرسال الطلب للأدمن
@bot.message_handler(content_types=['photo'], func=lambda message: user_sessions.get(str(message.from_user.id), {}).get("step") == "WAITING_PROOF")
def handle_payment_proof(message):
    user_id = str(message.from_user.id)
    session = user_sessions[user_id]
    
    order_id = random.randint(100000, 999999)
    photo_id = message.photo[-1].file_id
    
    try:
        supabase.table("orders").insert({
            "order_id": order_id,
            "user_id": user_id,
            "game": session["game_name"],
            "package": session["package"],
            "player_id": session["player_id"],
            "price": session["price"],
            "payment_method": session["payment_name"],
            "status": "pending"
        }).execute()
    except Exception as e:
        print(f"Supabase Order Error: {e}")

    bot.reply_to(message, f"⏳ **تم استلام طلبك بنجاح!**\nرقم الطلب: `#{order_id}`\nيتم الآن مراجعته من قبل الإدارة وسنقوم بإشعارك فور تفعيله.")

    admin_markup = InlineKeyboardMarkup(row_width=2)
    admin_markup.add(
        InlineKeyboardButton("✅ موافقة وتفعيل الطلب", callback_data=f"approve_{order_id}_{user_id}"),
        InlineKeyboardButton("❌ رفض وإلغاء الطلب", callback_data=f"reject_{order_id}_{user_id}")
    )
    
    admin_msg = (
        f"🔔 **طلب شحن جديد سحابي ومضمون (#{order_id})**\n\n"
        f"👤 العميل: {message.from_user.first_name}\n"
        f"🕹️ اللعبة: {session['game_name']}\n"
        f"📦 الحزمة: {session['package']}\n"
        f"🆔 معرف اللاعب: `{session['player_id']}`\n"
        f"💰 السعر: {session['price']} دولار\n"
        f"💳 وسيلة الدفع: {session['payment_name']}\n"
        f"🧾 الإثبات المرفق: تم إرفاق صورة إشعار التحويل"
    )
    
    try:
        bot.send_photo(int(ADMIN_ID), photo_id, caption=admin_msg, reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to send to admin: {e}")
        
    user_sessions.pop(user_id, None)

# 7. معالجة أزرار الأدمن وتوزيع مكافأة الإحالة عند الموافقة
