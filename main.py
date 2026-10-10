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
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://mar-eox3.onrender.com")

# 🔒 رابط قاعدة البيانات يتم جلبه من متغيرات البيئة لحمايته
DATABASE_URL = os.environ.get("DATABASE_URL", "")

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
            balance = row[0]  # ✅ تم الإصلاح: جلب القيمة الرقمية من الـ Tuple مباشرة
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

# 🛠️ ✅ تم الإصلاح: إضافة المسار الرئيسي لمنع ظهور خطأ 404 (غير موجود) في المتصفح
@app.route('/')
def home():
    return "🚀 السيرفر يعمل بنجاح والبوت متصل بقاعدة البيانات!", 200

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
        user_msg = f"🔄 تم خصم {item['price']} دولار وشراء **{item['name']}** بنجاح!\n🎮 الـ ID: `{player_id}`\n💰 رصيدك: {new_balance} دولار"
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
            return jsonify({"success": False, "message": "عذراً، رصيدك غير كافٍ لإتمام هذه العملية!"})
            
        threading.Thread(target=async_send_order, args=(user_id, item, player_id)).start()
        return jsonify({"success": True, "message": "جاري معالجة طلبك بنجاح!"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"حدث خطأ في النظام: {str(e)}"})

# --- معالجة أمر الدفع المالي الموجه للمستخدمين /pay ---
@bot.message_handler(commands=['pay'])
def handle_pay_command(message):
    try:
        # التحقق من أن مرسل الأمر هو الآدمن المسؤول فقط لحماية البوت من التلاعب بالأرصدة
        if message.chat.id != ADMIN_CHAT_ID:
            bot.reply_to(message, "❌ عذراً، هذا الأمر مخصص لإدارة المتجر فقط!")
            return

        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ **الصيغة الصحيحة:**\n`/pay [ID] [المبلغ]`")
            return
            
        target_user_id = int(parts[1])
        amount = float(parts[2])
        
        if amount <= 0:
            bot.reply_to(message, "❌ لا يمكن تحويل مبلغ يساوي أو أقل من صفر!")
            return
            
        if update_user_balance(target_user_id, amount):
            new_balance = get_user_balance(target_user_id)
            success_msg = f"✅ تم إضافة {amount} دولار للمستخدم `{target_user_id}`\n💰 رصيده الحالي: {new_balance} دولار"
            bot.send_message(message.chat.id, success_msg)
            
            # إشعار المستخدم المستهدف
            try:
                bot.send_message(target_user_id, f"🎉 تم إيداع {amount} دولار لحسابك بنجاح.\n💰 رصيدك الحالي: {new_balance} دولار")
            except:
                pass  # في حال لم يقم المستخدم ببدء المحادثة مع البوت بعد
        else:
            bot.reply_to(message, "❌ فشل تحديث الرصيد، يرجى التحقق من اتصال قاعدة البيانات.")
            
    except ValueError:
        bot.reply_to(message, "❌ خطأ: يرجى التأكد من كتابة ID والمبلغ كأرقام صحيحة.")
    except Exception as e:
        print(f"Error in pay command: {str(e)}")

# دالة لتسجيل الـ Webhook تلقائياً عند بدء التشغيل
def set_webhook():
    try:
        webhook_url = f"{RENDER_WEB_URL}/{BOT_TOKEN}"
        url = f"https://telegram.org{BOT_TOKEN}/setWebhook?url={webhook_url}"
        response = requests.get(url).json()
        print(f"📡 Webhook Setup Status: {response}")
    except Exception as e:
        print(f"❌ Failed to set Webhook: {str(e)}")

if __name__ == "__main__":
    # تشغيل الـ Webhook في خيط منفصل لتجنب تعليق السيرفر
    threading.Thread(target=set_webhook).start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
