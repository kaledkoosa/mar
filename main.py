import telebot
from telebot import types
import sqlite3
import os

# --- إعدادات الحماية والأمان (متوافقة مع السيرفرات) ---
# يقوم بقراءة التوكن والـ ID من السيرفر، وإذا لم يجدهم يستخدم القيم الافتراضية للتجربة المحلية
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_توكن_البوت_الخاص_بـك_هنا")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "123456789")) # ضع الـ ID الخاص بحسابك التلغرام هنا

bot = telebot.TeleBot(BOT_TOKEN)

# --- معلومات الدفع الخاصة بك (عدلها بما يناسبك) ---
PAYMENT_METHODS = (
    "💳 **طرق الشحن المتوفرة:**\n\n"
    "1️⃣ **فودافون كاش (مصر):** `010xxxxxxx`\n"
    "2️⃣ **زين كاش (العراق):** `077xxxxxxx`\n"
    "3️⃣ **محفظة باير (Payeer):** `P10234567`\n"
    "4️⃣ **عملة رقمية (USDT-TRC20):** `Txxxxxxxxxxxxxx`\n\n"
    "📌 قم بتحويل المبلغ الذي تريده إلى أحد الحسابات أعلاه، "
    "ثم أرسل **صورة إيصال التحويل (وصل الدفع)** هنا في الشات فوراً ليتم مراجعة طلبك وإضافة الرصيد لحسابك تلقائياً."
)

# --- باقات الشحن والأسعار ---
PRICES = {
    "pubg_60": {"name": "60 شدة PUBG", "price": 1.0},
    "pubg_325": {"name": "325 شدة PUBG", "price": 5.0},
    "ff_100": {"name": "100 جوهرة Free Fire", "price": 1.0},
    "ff_310": {"name": "310 جوهرة Free Fire", "price": 3.0}
}

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect("manual_shop.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_balance(user_id):
    conn = sqlite3.connect("manual_shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return balance

def update_user_balance(user_id, amount):
    conn = sqlite3.connect("manual_shop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- أمر البدء /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    welcome_text = (
        f"👋 أهلاً بك في بوت شحن الألعاب الأسرع!\n\n"
        f"💰 رصيدك الحالي: {balance} \$\n\n"
        f"الرجاء اختيار اللعبة المراد شحنها أو شحن رصيد حسابك:"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎮 ببجي موبايل (PUBG)", callback_data="menu_pubg"),
        types.InlineKeyboardButton("🔥 فري فاير (Free Fire)", callback_data="menu_ff"),
        types.InlineKeyboardButton("💳 شحن رصيد الحساب", callback_data="menu_deposit")
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# --- معالجة الأزرار الشفافة ---
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if call.data == "menu_pubg":
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, item in PRICES.items():
            if "pubg" in key:
                markup.add(types.InlineKeyboardButton(f"{item['name']} ({item['price']}\$)", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 العودة لتقائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text("اختر باقة الشدات المناسبة لـ PUBG:", chat_id, call.message.message_id, reply_markup=markup)
        
    elif call.data == "menu_ff":
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, item in PRICES.items():
            if "ff" in key:
                markup.add(types.InlineKeyboardButton(f"{item['name']} ({item['price']}\$)", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text("اختر باقة الجواهر المناسبة لـ Free Fire:", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data == "main_menu":
        balance = get_user_balance(user_id)
        welcome_text = f"💰 رصيدك الحالي: {balance} \$\n\nالرجاء اختيار اللعبة أو الخدمة:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎮 ببجي موبايل (PUBG)", callback_data="menu_pubg"),
            types.InlineKeyboardButton("🔥 فري فاير (Free Fire)", callback_data="menu_ff"),
            types.InlineKeyboardButton("💳 شحن رصيد الحساب", callback_data="menu_deposit")
        )
        bot.edit_message_text(welcome_text, chat_id, call.message.message_id, reply_markup=markup)

    # طلب شحن الرصيد من قبل الزبون
    elif call.data == "menu_deposit":
        msg = bot.send_message(chat_id, PAYMENT_METHODS, parse_mode="Markdown")
        # ننتظر من الزبون إرسال صورة إيصال التحويل
        bot.register_next_step_handler(msg, process_deposit_receipt)

    # معالجة طلبات شراء الألعاب
    elif call.data.startswith("buy_"):
        item_key = call.data.replace("buy_", "")
        item = PRICES[item_key]
        balance = get_user_balance(user_id)
        
        if balance >= item["price"]:
            msg = bot.send_message(chat_id, f"🔄 لقد اخترت {item['name']}.\nالرجاء إرسال الـ ID الخاص بحسابك في اللعبة الآن:")
            bot.register_next_step_handler(msg, process_manual_delivery, item_key, item)
        else:
            bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ! يرجى شحن حسابك أولاً بالضغط على 'شحن رصيد الحساب'.", show_alert=True)

    # معالجة قرار الإدارة بخصوص إيصال إيداع المال
    elif call.data.startswith("deposit_"):
        # الصيغة: deposit_ACTION_USERID
        _, action, customer_id = call.data.split("_")
        customer_id = int(customer_id)
        
        if action == "approve":
            # اطلب من الأدمن إدخال القيمة التي يريد إضافتها للزبون
            msg = bot.send_message(chat_id, f"كم القيمة بالدولار (\$) التي تريد إضافتها لحساب المستخدم `{customer_id}`؟")
            bot.register_next_step_handler(msg, confirm_deposit_amount, customer_id, call.message.message_id)
        elif action == "reject":
            try:
                bot.send_message(customer_id, "❌ نعتذر منك، تم رفض إيصال الشحن الخاص بك من قبل الإدارة. يرجى التأكد من تفاصيل العملية أو التواصل مع الدعم للشكاوى.")
                bot.edit_message_text(f"❌ تم رفض إيصال المستخدم {customer_id} وإبلاغه بنجاح.", chat_id, call.message.message_id)
            except:
                bot.edit_message_text(f"⚠️ تم الرفض في السيرفر لكن تعذر مراسلة المستخدم {customer_id}.", chat_id, call.message.message_id)

    # معالجة إتمام شحن الألعاب من الأدمن
    elif call.data.startswith("done_"):
        _, customer_id, item_key = call.data.split("_")
        customer_id = int(customer_id)
        item_name = PRICES[item_key]["name"]
        
        try:
            bot.send_message(customer_id, f"✅ بشرى سارة! تم شحن باقة **{item_name}** لحسابك في اللعبة بنجاح. العب واستمتع! 🎮")
            bot.edit_message_text(f"✅ قمت بالموافقة وشحن الطلب للمستخدم {customer_id} بنجاح.", chat_id, call.message.message_id)
        except:
            bot.send_message(chat_id, f"⚠️ تم تحديث العملية ولكن تعذر إرسال رسالة للزبون {customer_id}.")

# --- دالة استلام إيصال الشحن وإرساله للأدمن ---
def process_deposit_receipt(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # التحقق من أن المستخدم أرسل صورة بالفعل
    if message.content_type != 'photo':
        bot.send_message(chat_id, "❌ خطأ! يجب إرسال **صورة** واضحة للإيصال. يرجى الضغط على زر الشحن والمحاولة مجدداً.")
        return

    # نأخذ أكبر حجم للصورة مرسلة
    photo_id = message.photo[-1].file_id
    
    # إشعار للزبون
    bot.send_message(chat_id, "⏳ جاري رفع إيصالك ومراجعته من قبل الإدارة. سيتم إضافة الرصيد لحسابك فور التأكيد.")
    
    # إرسال الصورة للأدمن مع الأزرار لاتخاذ القرار
    admin_markup = types.InlineKeyboardMarkup()
    admin_markup.add(
        types.InlineKeyboardButton("✅ قبول وإضافة رصيد", callback_data=f"deposit_approve_{user_id}"),
        types.InlineKeyboardButton("❌ رفض الإيصال", callback_data=f"deposit_reject_{user_id}")
    )
    
    bot.send_photo(
        ADMIN_CHAT_ID, 
        photo_id, 
        caption=f"💰 **إشعار إيداع رصيد جديد**\n\n👤 المستخدم: [{message.from_user.first_name}](tg://user?id={user_id})\n🆔 رقم حسابه: `{user_id}`\n\nتأكد من وصول المال لحسابك الحقيقي ثم اتخذ القرار:", 
        parse_mode="Markdown", 
        reply_markup=admin_markup
    )

# --- دالة تأكيد كمية رصيد الشحن المضاف من الأدمن ---
def confirm_deposit_amount(message, customer_id, original_msg_id):
    chat_id = message.chat.id
    try:
        amount = float(message.text)
        update_user_balance(customer_id, amount)
        new_balance = get_user_balance(customer_id)
        
        # إرسال للزبون
        bot.send_message(customer_id, f"🎉 أخبار رائعة! تم تأكيد إيداعك وإضافة **{amount} \$** لحسابك في البوت بنجاح.\n💰 رصيدك الحالي أصبح: {new_balance} \$")
        
        # تحديث شاشة الأدمن
        bot.send_message(chat_id, f"✅ بنجاح! قمت بإضافة {amount}\$ لحساب المستخدم `{customer_id}`. رصيده الحالي الآن هو: {new_balance}\$")
    except ValueError:
        bot.send_message(chat_id, "❌ خطأ في القيمة، يجب إرسال رقم فقط (مثال: 5 أو 10.5). يرجى إعادة المحاولة من البداية.")

# --- دالة معالجة طلب شحن اللعبة وإرساله للأدمن ---
def process_manual_delivery(message, item_key, item):
    user_id = message.from_user.id
    chat_id = message.chat.id
    player_id = message.text
    
    balance = get_user_balance(user_id)
    if balance < item["price"]:
        bot.send_message(chat_id, "❌ حدث خطأ، رصيدك غير كافٍ.")
        return

    # خصم من البوت
    update_user_balance(user_id, -item["price"])
    new_balance = get_user_balance(user_id)
    
