import os
import json
import random
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
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

# قراءة معرف الحساب لـ CWallet كمتغير بيئي آمن من موقع Render
CWALLET_ACCOUNT_ID = os.getenv("CWALLET_ID", "[رقم المعرف غير مضاف]")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = FastAPI()

# تهيئة سوبابيس المستقرة
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

payment_details = {
    "shamcash": {"name": "شام كاش (ShamCash)", "msg": f"يرجى التحويل إلى حساب شام كاش رقم: `{SHAM_CASH_NUM}`"},
    "cwallet": {"name": "محفظة CWallet (يدوي)", "msg": f"💡 *توفير الرسوم:* يرجى التحويل الداخلي المجاني (0 رسوم) داخل تطبيق CWallet إلى المعرف الخاص بنا:\n\n👉 معرف الحساب (CWallet ID): `{CWALLET_ACCOUNT_ID}`"}
}

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/ping")
def ping_server():
    return {"status": "alive", "msg": "إشعار نشاط تلقائي لمنع النوم"}

@app.post(f"/{BOT_TOKEN}/")
async def process_webhook(request: Request):
    json_string = await request.body()
    update = telebot.types.Update.de_json(json_string.decode('utf-8'))
    bot.process_new_updates([update])
    return {"status": "ok"}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)

    try:
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": message.from_user.username or "N/A",
            "full_name": message.from_user.first_name or "N/A"
        }).execute()
        
        supabase.table("orders").delete().eq("user_id", user_id).eq("status", "مسودة").execute()
    except Exception as e:
        print(f"Supabase Error: {e}")

    cache_buster = random.randint(1000, 9999)
    webapp_url = f"{RENDER_URL}/frontend/index.html?v={cache_buster}"
    
    markup = InlineKeyboardMarkup()
    web_app_info = telebot.types.WebAppInfo(url=webapp_url)
    markup.add(InlineKeyboardButton(text="🎮 فتح المتجر الإلكتروني ⚡", web_app=web_app_info))

    bot.reply_to(message, "👋 مرحباً بك في متجر شحن الألعاب الإلكترونية الاحترافي المستقر!\n\nاضغط على الزر بالأسفل لفتح المتجر المباشر وتأكيد طلبك فورا وسيتجاوب معك السيرفر في أي وقت:", reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص لمالك المتجر فقط!")
        return
    
    try:
        response = supabase.table("orders").select("*").eq("status", "بانتظار المراجعة").execute()
        orders = response.data
        bot.reply_to(message, f"📋 لوحة التحكم مستقرة وسحابية بالكامل.\n\nيوجد حالياً مجموع ({len(orders)}) طلبات معلقة بانتظار تفعيلك.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ سحابي: {e}")

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    try:
        user_id = str(message.from_user.id)
        data = json.loads(message.web_app_data.data)

        package_info = data["packageName"] if isinstance(data["packageName"], list) else data["packageName"]
        price_info = data["price"] if isinstance(data["price"], list) else data["price"]

        qty = package_info.split("|") if "|" in package_info else package_info
        prc = package_info.split("|") if "|" in package_info else price_info

        method_title = payment_details[data["paymentMethod"]]["name"]

        supabase.table("orders").insert({
            "user_id": user_id,
            "game": data["gameName"],
            "package": qty,
            "price": prc,
            "player_id": data["playerId"],
            "payment_method": method_title,
            "status": "مسودة"
        }).execute()

        selected_pay = payment_details[data["paymentMethod"]]

        bot.reply_to(message, 
            f"📝 *تم استقبال تفاصيل طلبك بنجاح:*\n\n"
            f"🎮 اللعبة: {data['gameName']}\n"
            f"📦 الباقة المطلوبة: {qty}\n"
            f"🆔 معرف اللاعب (Player ID): `{data['playerId']}`\n"
            f"💰 الإجمالي المطلوب: {prc} دولار\n\n"
            f"-------------------------\n"
            f"⚙️ *بيانات التحويل عبر ({selected_pay['name']}):*\n"
            f"{selected_pay['msg']}\n\n"
            f"📥 *خطوة أخيرة وحاسمة:* يرجى إتمام عملية التحويل (بدون رسوم)، ثم إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة لتأكيد الدفع:"
        )
    except Exception as e:
        print(f"WebApp Data Error: {e}")
        bot.reply_to(message, "❌ حدث خطأ غير متوقع، يرجى إعادة محاولة فتح المتجر.")

@bot.message_handler(content_types=['photo', 'text'])
def handle_payment_proof(message):
    user_id = str(message.from_user.id)
    
    try:
        response = supabase.table("orders").select("*").eq("user_id", user_id).eq("status", "مسودة").order("created_at", desc=True).limit(1).execute()
        orders = response.data
        
        if not orders:
            return

        order_data = orders
        
        proof_photo = message.photo[-1].file_id if message.content_type == 'photo' else None
        proof_text = message.caption or "تم إرفاق صورة إشعار التحويل" if message.content_type == 'photo' else message.text

        update_res = supabase.table("orders").update({
            "proof_text": proof_text,
            "proof_photo": proof_photo,
            "status": "بانتظار المراجعة"
        }).eq("id", order_data["id"]).execute()
        
        final_order = update_res.data

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

    except Exception as e:
        print(f"Database/Admin Proof Error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_actions(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!")
        return

    data_parts = call.data.split('_')
    action = data_parts
    order_id = data_parts
    client_id = data_parts

    if action == "ok":
        supabase.table("orders").update({"status": "مكتمل"}).eq("id", order_id).execute()
        bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, caption=f"✅ تم قبول وشحن الطلب رقم #{order_id} بنجاح.") if call.message.content_type == 'photo' else bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=f"✅ تم قبول وشحن الطلب رقم #{order_id} بنجاح.")
        bot.send_message(client_id, f"🎉 بشرى سارة! تم التحقق من دفعتك اليدوية وشحن حسابك بالباقة المطلوبة للطلب رقم ({order_id}). نتمنى لك وقتاً ممتعاً!")
    
    elif action == "no":
        supabase.table("orders").update({"status": "مرفوض"}).eq("id", order_id).execute()
        bot.edit_message_caption(chat_id=ADMIN_ID, message_id=call.message.message_id, caption=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.") if call.message.content_type == 'photo' else bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=f"❌ تم رفض وإلغاء الطلب رقم #{order_id}.")
        bot.send_message(client_id, f"⚠️ إشعار: تم رفض طلب الشحن رقم ({order_id}) بسبب عدم وصول قيمة التحويل أو خطأ بالإيصال الفني.")

@app.on_event("startup")
def startup_event():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}/"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook has been set successfully on: {webhook_url}")
