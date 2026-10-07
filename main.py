import telebot
from telebot import types
import psycopg2
import os
import threading
import json
from flask import Flask, render_template_string, request, jsonify

app = Flask('')

# --- جلب المتغيرات السرية بأمان تام من Render ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "placeholder_token")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
RENDER_WEB_URL = os.environ.get("RENDER_WEB_URL", "https://onrender.com")

# الفكس الأول: قراءة الرابط الصحيح من البيئة وضبط البديل بصياغة سليمة (تأكد من تعديله في إعدادات Render)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "postgresql://postgres.aeozpoldsypsketsmzym:koosasy0980@://supabase.com"
)

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
        print("Database initialized successfully on Supabase Cloud.")
    except Exception as e:
        print(f"Database Init Error: {str(e)}")

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
        print(f"Error fetching balance: {str(e)}")
        return 0.0

def update_user_balance(user_id, amount):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error updating balance: {str(e)}")

def get_total_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        conn.close()
        return count
    except:
        return 0

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
        return f"Error inside database fetching: {str(e)}"
        
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
            f"🆔 **ID اللاعب في اللعبة:** `{player_id}`\n\n"
            f"📌 يرجى الدخول وشحن الباقة فوراً!"
        )
        bot.send_message(ADMIN_CHAT_ID, text=admin_msg)
        
        update_user_balance(user_id, -item["price"])
        new_balance = get_user_balance(user_id)
        
        # الفكس الثاني: إزالة الـ \ الخاطئة من أمام علامات الدولار \$ لمنع الـ SyntaxWarning
        user_msg = (
            f"🔄 تم خصم {item['price']} \$ وشراء **{item['name']}** بنجاح!\n"
            f"🎮 الـ ID المستهدف للشحن: `{player_id}`\n"
            f"💰 رصيدك المتبقي الحالي: {new_balance} \$\n\n"
            f"⏳ جاري تسليم الشحنة من قبل الإدارة."
        )
        bot.send_message(user_id, user_msg)
    except Exception as e:
        print(f"Async Notification Error: {str(e)}")

@app.route('/api/buy', methods=['POST', 'OPTIONS'])
def api_buy_item():
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response
