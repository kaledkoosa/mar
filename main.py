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

# قائمة الألعاب والأسعار والكميات
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

# 1. أمر البداية وعرض الألعاب بأزرار شفافة
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    user_sessions[user_id] = {}

    try:
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": message.from_user.username or "N/A",
            "full_name": message.from_user.first_name or "N/A"
        }).execute()
    except Exception as e:
        print(f"Supabase Error: {e}")

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🎮 ببجي موبايل (PUBG MOBILE)", callback_data="game_pubg"),
        InlineKeyboardButton("🔥 فري فاير (FREE FIRE)", callback_data="game_ff")
    )
    bot.reply_to(message, "👋 مرحباً بك في متجر شحن الألعاب السريع والأكثر استقراراً!\n\n🕹️ من فضلك اختر اللعبة المستهدفة من الأزرار أدناه للبدء:", reply_markup=markup)

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
    if user_id not in user_sessions:
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
    player_id = message.text.trim() if hasattr(message.text, 'trim') else message.text.strip()
    
    user_sessions[user_id]["player_id"] = player_id
    user_sessions[user_id]["step"] = "WAITING_PAYMENT"
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💳 شحن عبر شام كاش (ShamCash)", callback_data="pay_shamcash"),
        InlineKeyboardButton("🪙 شحن عبر محفظة CWallet (USDT)", callback_data="pay_cwallet")
    )
    bot.reply_to(message, f"✅ تم حفظ معرف اللاعب: `{player_id}`\n\n💰 الإجمالي المطلوب: *{user_sessions[user_id]['price']} دولار*\n\n👇 اختر وسيلة التحويل والدفع اليدوية المناسبة لك لتأكيد الطلب:", reply_markup=markup)

# 5. معالجة وسيلة الدفع وعرض بيانات التحويل وطلب الإشعار
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def handle_payment_selection(call):
    user_id = str(call.from_user.id)
    if user_id not in user_sessions:
        bot.send_message(call.message.chat.id, "❌ انتهت الجلسة، يرجى كتابة /start من جديد.")
        return
        
    pay_key = call.data.split('_')[1]
    selected_pay = payment_details[pay_key]
    
    user_sessions[user_id]["payment_method"] = pay_key
    user_sessions[user_id]["step"] = "WAITING_PROOF"
    
    # حفظ مسودة سحابية أولية في Supabase لتأمين الطلب
    try:
        supabase.table("orders").insert({
            "user_id": user_id,
            "game": user_sessions[user_id]["game_name"],
            "package": user_sessions[user_id]["package"],
            "price": user_sessions[user_id]["price"],
            "player_id": user_sessions[user_id]["player_id"],
            "payment_method": selected_pay["name"],
            "status": "مسودة"
        }).execute()
    except Exception as e:
        print(f"Draft Insert Error: {e}")

    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"⚙️ *بيانات التحويل عبر ({selected_pay['name']}):*\n\n{selected_pay['msg']}\n\n📥 *خطوة حاسمة وأخيرة:* يرجى إتمام عملية التحويل، ثم إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة كرسالة لتأكيد الدفع ومراجعة طلبك:")

# 6. استقبال إثبات الدفع وتحديث الطلب وتنبيه الأدمن
@bot.message_handler(content_types=['photo', 'text'])
def handle_payment_proof(message):
    user_id = str(message.from_user.id)
    session = user_sessions.get(user_id, {})
    
    if session.get("step") != "WAITING_PROOF":
        return

    try:
        # جلب أحدث مسودة طلب من قاعدة البيانات
        response = supabase.table("orders").select("*").eq("user_id", user_id).eq("status", "مسودة").order("created_at", desc=True).limit(1).execute()
        orders = response.data
        if not orders:
            return

        order_data = orders[0]
        proof_photo = message.photo[-1].file_id if message.content_type == 'photo' else None
        proof_text = message.caption or "تم إرفاق صورة إشعار التحويل" if message.content_type == 'photo' else message.text

        # تحديث حالة الطلب سحابياً بانتظار المراجعة
        update_res = supabase.table("orders").update({
            "proof_text": proof_text,
            "proof_photo": proof_photo,
            "status": "بانتظار المراجعة"
        }).eq("id", order_data["id"]).execute()
        
        final_order = update_res.data[0]

        bot.reply_to(message, "✅ شكراً لك! تم تثبيت إثبات الدفع سحابياً وإرسال طلبك للإدارة بنجاح. سيتم مراجعة حسابنا وشحن حسابك وتنبيهك فوراً.")

        admin_msg = (
            f"🔔 *طلب شحن جديد سحابي ومضمون (#{final_order['id']})*\n\n"
            f"👤 العميل: [{message.from_user.first_name}](tg://user?id={user_id})\n"
            f"🎮 اللعبة: {final_order['game']}\n"
            f"📦 الحزمة: {final_order['package']}\n"
            f"🆔 معرف اللاعب: `{final_order['player_id']}`\n"
            f"💰 السعر: {final_order['price']} دولار\n"
            f"💳 وسيلة الدفع: {final_order['payment_method']}\n"
            f"📝 الإثبات المرفق: {final_order['proof_text']}"
        )

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ موافقة وتفعيل الطلب", callback_data=f"admin_ok_{final_order['id']}_{user_id}"),
            InlineKeyboardButton("❌ رفض وإلغاء الطلب", callback_data=f"admin_no_{final_order['id']}_{user_id}")
        )

        if final_order.get("proof_photo"):
            bot.send_photo(ADMIN_ID, final_order["proof_photo"], caption=admin_msg, reply_markup=markup)
        else:
            bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

        del user_sessions[user_id]
    except Exception as e:
        print(f"Database/Admin Proof Error: {e}")

# 7. لوحة تحكم الأدمن (الموافقة والرفض)
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_actions(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!")
        return
    data_parts = call.data.split('_')
    action = data_parts[1]
    order_id = data_parts[2]
    client_id = data_parts[3]

    if action == "ok":
        supabase.table("orders").update({"status": "مكتمل"}).eq("id", order_id).execute()
