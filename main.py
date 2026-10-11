import os
import json
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client
from supabase.client import ClientOptions
from dotenv import load_dotenv

load_dotenv()

# قراءة المتغيرات البيئية من موقع Render مباشرة
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "[09xxxxxxxx]")

# تهيئة البوت وخادم الويب
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = FastAPI()

# تهيئة Supabase مع حل مشكلة الـ proxy وتحديد المهلة لتفادي الأخطاء
supabase: Client = create_client(
    SUPABASE_URL, 
    SUPABASE_KEY, 
    options=ClientOptions(postgrest_client_timeout=10)
)

# ذاكرة مؤقتة لحفظ حالات المستخدمين بانتظار رفع الإشعار اليدوي
user_sessions = {}

# تفاصيل التحويل اليدوي
payment_details = {
    "shamcash": {"name": "شام كاش (ShamCash)", "msg": f"يرجى التحويل إلى حساب شام كاش رقم: `{SHAM_CASH_NUM}`"},
    "cwallet": {"name": "محفظة CWallet (يدوي)", "msg": "يرجى التحويل إلى عنوان USDT (TRC20):\n`TYxxxxxxxxxxxxxxxxxxxxxxxx`"}
}

# تشغيل خادم الويب لتقديم ملفات واجهة المتجر تلقائياً من مجلد frontend
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# 1. مسار تلقي طلبات التليجرام (Webhook Route)
@app.post(f"/{BOT_TOKEN}/")
async def process_webhook(request: Request):
    json_string = await request.body()
    update = telebot.types.Update.de_json(json_string.decode('utf-8'))
    bot.process_new_updates([update])
    return {"status": "ok"}

# 2. أمر التشغيل /start وعرض زر واجهة الويب
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    user_sessions[user_id] = {} # تصفير الجلسة

    try:
        # حفظ أو تحديث بيانات العميل في Supabase
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": message.from_user.username or "N/A",
            "full_name": message.from_user.first_name or "N/A"
        }).execute()
    except Exception as e:
        print(f"Supabase Error: {e}")

    # إنشاء زر فتح واجهة الويب التفاعلية
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    webapp_url = f"{RENDER_URL}/frontend/index.html"
    web_app_info = telebot.types.WebAppInfo(url=webapp_url)
    markup.add(KeyboardButton(text="🎮 فتح المتجر الإلكتروني", web_app=web_app_info))

    bot.reply_to(message, "👋 مرحباً بك في متجر شحن الألعاب الإلكترونية!\n\nاضغط على الزر بالأسفل لفتح المتجر واختيار عروضك المفضلة عبر واجهة ويب سريعة:", reply_markup=markup)

# 3. استقبال وقراءة البيانات القادمة من واجهة الويب (Web App Data)
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    try:
        user_id = str(message.from_user.id)
        data = json.loads(message.web_app_data.data)

        # حفظ تفاصيل الطلب مؤقتاً لحين رفع إشعار التحويل اليدوي
        user_sessions[user_id] = {
            "game": data["gameName"],
            "package": data["packageName"],
            "price": data["price"],
            "player_id": data["playerId"],
            "payment_method": data["paymentMethod"],
            "step": "WAITING_PROOF"
        }

        selected_pay = payment_details[data["paymentMethod"]]

        bot.reply_to(message, 
            f"📝 *تم استلام تفاصيل باقة الشحن:*\n\n"
            f"🎮 اللعبة: {data['gameName']}\n"
            f"📦 الباقة: {data['packageName']}\n"
            f"🆔 معرف اللاعب: `{data['playerId']}`\n"
            f"💰 الإجمالي المطلوب: {data['price']} دولار\n\n"
            f"-------------------------\n"
            f"⚙️ *تعليمات الدفع اليدوي عبر ({selected_pay['name']}):*\n"
            f"{selected_pay['msg']}\n\n"
            f"📥 *خطوة أخيرة:* بعد إتمام عملية التحويل بنجاح، يرجى إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة في الشات لتأكيد طلبك:"
        )
    except Exception as e:
        print(f"WebApp Data Error: {e}")
        bot.reply_to(message, "❌ حدث خطأ أثناء قراءة بيانات طلبك، يرجى إعادة المحاولة.")

# 4. استقبال صورة الإشعار أو النص كإثبات دفع يدوي
@bot.message_handler(content_types=['photo', 'text'])
def handle_payment_proof(message):
    user_id = str(message.from_user.id)
    session = user_sessions.get(user_id)

    if not session or session.get("step") != "WAITING_PROOF":
        return

    if message.content_type == 'photo':
        session["proof_photo"] = message.photo[-1].file_id
        session["proof_text"] = message.caption or "تم إرفاق صورة إشعار التحويل"
    else:
        session["proof_photo"] = None
        session["proof_text"] = message.text

    process_and_send_to_admin(message, user_id, session)

def process_and_send_to_admin(message, user_id, session):
    try:
        method_title = payment_details[session["payment_method"]]["name"]

        # تسجيل وحفظ الطلب في قاعدة بيانات Supabase
        response = supabase.table("orders").insert({
            "user_id": user_id,
            "game": session["game"],
            "package": session["package"],
            "price": session["price"],
            "player_id": session["player_id"],
            "payment_method": method_title,
            "proof_text": session["proof_text"],
            "proof_photo": session["proof_photo"],
            "status": "بانتظار المراجعة"
        }).execute()

        order_data = response.data[0]
        bot.reply_to(message, "✅ شكراً لك! تم رفع إثبات الدفع وإرسال طلبك للإدارة بنجاح. سيتم مراجعة حسابنا وشحن حسابك وتنبيهك فوراً.")

        # صياغة رسالة التحكم الخاصة بالأدمن
        admin_msg = (
            f"🔔 *طلب شحن جديد رقم (#{order_data['id']})*\n\n"
            f"👤 العميل: [{message.from_user.first_name}](tg://user?id={user_id})\n"
            f"🎮 اللعبة: {order_data['game']}\n"
            f"📦 الحزمة: {order_data['package']}\n"
            f"🆔 معرف اللاعب: `{order_data['player_id']}`\n"
            f"💰 السعر المطلوب: {order_data['price']} دولار\n"
            f"💳 وسيلة الدفع: {order_data['payment_method']}\n"
            f"📝 الإثبات: {order_data['proof_text']}"
        )

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ موافقة وشحن", callback_data=f"admin_ok_{order_data['id']}_{user_id}"),
            InlineKeyboardButton("❌ رفض وإلغاء", callback_data=f"admin_no_{order_data['id']}_{user_id}")
        )

        if order_data["proof_photo"]:
            bot.send_photo(ADMIN_ID, order_data["proof_photo"], caption=admin_msg, reply_markup=markup)
        else:
            bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

        del user_sessions[user_id]

    except Exception as e:
        print(f"Database/Admin Send Error: {e}")
        bot.reply_to(message, "❌ فشل تسجيل الطلب في قاعدة البيانات. يرجى إعادة المحاولة لاحقاً.")

# 5. معالجة أزرار تحكم الأدمن (موافقة / رفض)
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
        
        if call.message.content_type == 'photo':
            bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, caption=f"✅ تم قبول وشحن الطلب رقم #{order_id} بنجاح.")
        else:
            bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=f"✅ تم قبول وشحن الطلب رقم #{order_id} بنجاح.")
            
        bot.send_message(client_id, f"🎉 بشرى سارة! تم التحقق من دفعتك اليدوية وشحن حسابك بالباقة المطلوبة للطلب رقم ({order_id}). نتمنى لك وقتاً ممتعاً!")
    
    elif action == "no":
        supabase.table("orders").update({"status": "mrfod"}).eq("id", order_id).execute()
        
        if call.message.content_type == 'photo':
            bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, caption=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.")
        else:
            bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.")
            
        bot.send_message(client_id, f"⚠️ إشعار: تم رفض طلب الشحن رقم ({order_id}) بسبب عدم وصول قيمة التحويل أو خطأ بالإيصال المرفق. يرجى مراجعة الدعم الفني.")

# 6. تفعيل الـ Webhook عند بدء تشغيل تطبيق الـ FastAPI على سيرفر Render
@app.on_event("startup")
def startup_event():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}/"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook has been set successfully on: {webhook_url}")
