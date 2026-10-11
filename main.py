import os
import json
import random
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
SHAM_CASH_NUM = os.getenv("SHAM_CASH_NUM", "[09xxxxxxxx]")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = FastAPI()

# تهيئة سوبابيس
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

user_sessions = {}

payment_details = {
    "shamcash": {"name": "شام كاش (ShamCash)", "msg": f"يرجى التحويل إلى حساب شام كاش رقم: `{SHAM_CASH_NUM}`"},
    "cwallet": {"name": "محفظة CWallet (يدوي)", "msg": "يرجى التحويل إلى عنوان USDT (TRC20):\n`TYxxxxxxxxxxxxxxxxxxxxxxxx`"}
}

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.post(f"/{BOT_TOKEN}/")
async def process_webhook(request: Request):
    json_string = await request.body()
    update = telebot.types.Update.de_json(json_string.decode('utf-8'))
    bot.process_new_updates([update])
    return {"status": "ok"}

# أمر /start
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

    cache_buster = random.randint(1000, 9999)
    webapp_url = f"{RENDER_URL}/frontend/index.html?v={cache_buster}"
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    web_app_info = telebot.types.WebAppInfo(url=webapp_url)
    markup.add(KeyboardButton(text="🎮 فتح المتجر الإلكتروني", web_app=web_app_info))

    bot.reply_to(message, "👋 مرحباً بك في متجر شحن الألعاب الإلكترونية الاحترافي!\n\nاضغط على الزر بالأسفل لفتح المتجر واختيار باقاتك المفضلة:", reply_markup=markup)

# إضافة أمر /admin يدوي لعرض الطلبات المعلقة للأدمن
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص لمالك المتجر فقط!")
        return
    
    try:
        response = supabase.table("orders").select("*").eq("status", "بانتظار المراجعة").execute()
        orders = response.data
        
        if not orders:
            bot.reply_to(message, "🎉 لا توجد أي طلبات معلقة بانتظار المراجعة حالياً!")
            return
            
        bot.reply_to(message, f"📋 يوجد حالياً مجموع ({len(orders)}) طلبات بانتظار المراجعة والتفعيل. تفقد رسائل الدفع الواردة للتحكم بها.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء جلب البيانات: {e}")

# استقبال البيانات القادمة من واجهة الويب بعد الضغط على زر التأكيد
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    try:
        user_id = str(message.from_user.id)
        data = json.loads(message.web_app_data.data)

        # تفكيك الباقة والسعر بدقة بعد التعديل الثابت
        package_info = data["packageName"][0] if isinstance(data["packageName"], list) else data["packageName"]
        price_info = data["price"][1] if isinstance(data["price"], list) else data["price"]

        if "|" in package_info:
            qty, prc = package_info.split("|")
        else:
            qty = package_info
            prc = price_info

        user_sessions[user_id] = {
            "game": data["gameName"],
            "package": qty,
            "price": prc,
            "player_id": data["playerId"],
            "payment_method": data["paymentMethod"],
            "step": "WAITING_PROOF"
        }

        selected_pay = payment_details[data["paymentMethod"]]

        bot.reply_to(message, 
            f"📝 *تم استقبال تفاصيل طلبك بنجاح:*\n\n"
            f"🎮 اللعبة: {data['gameName']}\n"
            f"📦 الباقة المطلوبة: {qty}\n"
            f"🆔 معرف اللاعب (Player ID): `{data['playerId']}`\n"
            f"💰 الإجمالي المطلوب: {prc} دولار\n\n"
            f"-------------------------\n"
            f"⚙️ *تعليمات الدفع اليدوي المحمي عبر ({selected_pay['name']}):*\n"
            f"{selected_pay['msg']}\n\n"
            f"📥 *خطوة أخيرة:* يرجى إتمام عملية التحويل، ثم إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة في الشات لتأكيد الدفع:"
        )
    except Exception as e:
        print(f"WebApp Data Error: {e}")
        bot.reply_to(message, "❌ حدث خطأ غير متوقع أثناء معالجة طلبك، يرجى إعادة المحاولة.")

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

        order_data = response.data[0] if isinstance(response.data, list) else response.data
        bot.reply_to(message, "✅ شكراً لك! تم إرسال طلب الشحن وإثبات الدفع بنجاح. سيقوم الدعم بمراجعة عملية التحويل وتفعيل طلبك فوراً.")

        admin_msg = (
            f"🔔 *طلب شحن جديد بانتظار الموافقة (#{order_data['id']})*\n\n"
            f"👤 العميل: [{message.from_user.first_name}](tg://user?id={user_id})\n"
            f"🎮 اللعبة: {order_data['game']}\n"
            f"📦 الحزمة: {order_data['package']}\n"
            f"🆔 معرف اللاعب: `{order_data['player_id']}`\n"
            f"💰 السعر: {order_data['price']} دولار\n"
            f"💳 وسيلة الدفع: {order_data['payment_method']}\n"
            f"📝 الإثبات المرفق: {order_data['proof_text']}"
        )

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ موافقة وتفعيل الطلب", callback_data=f"admin_ok_{order_data['id']}_{user_id}"),
            InlineKeyboardButton("❌ رفض وإلغاء الطلب", callback_data=f"admin_no_{order_data['id']}_{user_id}")
        )

        if order_data.get("proof_photo"):
            bot.send_photo(ADMIN_ID, order_data["proof_photo"], caption=admin_msg, reply_markup=markup)
        else:
            bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

        del user_sessions[user_id]

    except Exception as e:
        print(f"Database/Admin Send Error: {e}")
        bot.reply_to(message, "❌ فشل تسجيل الطلب في قاعدة البيانات. يرجى إعادة المحاولة لاحقاً.")

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
        supabase.table("orders").update({"status": "مرفوض"}).eq("id", order_id).execute()
        
        if call.message.content_type == 'photo':
            bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, caption=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.")
        else:
            bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.")
            
        bot.send_message(client_id, f"⚠️ إشعار: تم رفض طلب الشحن رقم ({order_id}) بسبب عدم وصول قيمة التحويل أو خطأ بالإيصال المرفق. يرجى مراجعة الدعم الفني.")

@app.on_event("startup")
def startup_event():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}/"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook has been set successfully on: {webhook_url}")
