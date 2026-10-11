const { Telegraf, Markup } = require('telegraf');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const bot = new Telegraf(process.env.BOT_TOKEN);
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);
const ADMIN_ID = process.env.ADMIN_ID;

// ذاكرة تخزين مؤقتة للتحقق من خطوة تسليم الإشعار اليدوي للعميل
const userSessions = {};

const paymentDetails = {
  shamcash: { name: 'شام كاش (ShamCash)', msg: 'يرجى التحويل إلى حساب شام كاش رقم: [09xxxxxxxx]' },
  cwallet: { name: 'محفظة CWallet (يدوي)', msg: 'يرجى التحويل إلى عنوان USDT (TRC20):\n`TYxxxxxxxxxxxxxxxxxxxxxxxx`' }
};

// 1. أمر التشغيل /start وعرض زر فتح واجهة الويب
bot.start(async (ctx) => {
  const userId = ctx.from.id.toString();
  userSessions[userId] = {}; // تصفير الجلسة

  // حفظ بيانات العميل في Supabase
  await supabase.from('users').upsert({ 
    user_id: userId, 
    username: ctx.from.username || 'N/A',
    full_name: ctx.from.first_name || 'N/A'
  });

  ctx.reply(`👋 مرحباً بك في متجر شحن الألعاب الإلكترونية!\n\nاضغط على الزر بالأسفل لفتح المتجر التفاعلي واختيار عروضك المفضلة:`,
    Markup.keyboard([
      [Markup.button.webApp('🎮 فتح المتجر الإلكتروني', process.env.VERCEL_URL)]
    ]).resize()
  );
});

// 2. الاستماع واستقبال البيانات القادمة من واجهة الويب (Web App Data)
bot.on('web_app_data', async (ctx) => {
  try {
    const data = JSON.parse(ctx.message.web_app_data.data);
    const userId = ctx.from.id.toString();

    // تخزين تفاصيل الطلب مؤقتاً في السيرفر لحين قيام العميل برفع إثبات الدفع
    userSessions[userId] = {
      game: data.gameName,
      package: data.packageName,
      price: data.price,
      playerId: data.playerId,
      paymentMethod: data.paymentMethod,
      step: 'WAITING_PROOF'
    };

    const selectedPay = paymentDetails[data.paymentMethod];

    ctx.reply(`📝 *تم استلام تفاصيل باقة الشحن:*\n\n` +
              `🎮 اللعبة: ${data.gameName}\n` +
              `📦 الباقة: ${data.packageName}\n` +
              `🆔 معرف اللاعب: \`\${data.playerId}\`\n` +
              `💰 الإجمالي المطلوب: *$${data.price}*\n\n` +
              `-------------------------\n` +
              `⚙️ *تعليمات الدفع اليدوي عبر (${selectedPay.name}):*\n` +
              `${selectedPay.msg}\n\n` +
              `📥 *خطوة أخيرة:* بعد إتمام عملية التحويل بنجاح، يرجى إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة في الشات لتأكيد طلبك:`, 
      { parse_mode: 'Markdown' }
    );

  } catch (err) {
    console.error('Error handling WebApp Data:', err);
    ctx.reply('❌ حدث خطأ غير متوقع أثناء قراءة بيانات طلبك، يرجى إعادة المحاولة من داخل واجهة المتجر.');
  }
});

// 3. استقبال صورة الإشعار (الدفع اليدوي)
bot.on('photo', async (ctx) => {
  const userId = ctx.from.id.toString();
  const session = userSessions[userId];

  if (session && session.step === 'WAITING_PROOF') {
    session.proofPhoto = ctx.message.photo[ctx.message.photo.length - 1].file_id;
    session.proofText = ctx.message.caption || 'تم إرفاق صورة إشعار التحويل اليدوي';
    await processAndSendToAdmin(ctx, userId, session);
  }
});

// 4. استقبال نص الإشعار في حال كتب العميل رقم العملية نصاً
bot.on('text', async (ctx) => {
  const userId = ctx.from.id.toString();
  const session = userSessions[userId];

  if (!session || session.step !== 'WAITING_PROOF') return;

  session.proofPhoto = null;
  session.proofText = ctx.message.text;
  await processAndSendToAdmin(ctx, userId, session);
});

// دالة معالجة وحفظ الطلب وإرساله إلى الأدمن للمراجعة
async function processAndSendToAdmin(ctx, userId, session) {
  const methodTitle = paymentDetails[session.paymentMethod].name;

  // حفظ الطلب في قاعدة بيانات Supabase بوضع "بانتظار المراجعة"
  const { data, error } = await supabase.from('orders').insert({
    user_id: userId,
    game: session.game,
    package: session.package,
    price: session.price,
    player_id: session.playerId,
    payment_method: methodTitle,
    proof_text: session.proofText,
    proof_photo: session.proofPhoto,
    status: 'بانتظار المراجعة'
  }).select().single();

  if (error) {
    console.error(error);
    return ctx.reply('❌ فشل تسجيل الطلب في قاعدة البيانات. يرجى إعادة المحاولة لاحقاً.');
  }

  ctx.reply('✅ شكراً لك! تم رفع إثبات الدفع وإرسال طلبك للإدارة بنجاح. سيتم مراجعة حسابنا وشحن حسابك وتنبيهك فوراً.');

  // صياغة رسالة التحكم الخاصة بك (الأدمن)
  const adminMsg = `🔔 *طلب شحن جديد رقم (#${data.id})*\n\n` +
                    `👤 العميل: [${ctx.from.first_name}](tg://user?id=${userId})\n` +
                    `🎮 اللعبة: ${data.game}\n` +
                    `📦 الحزمة: ${data.package}\n` +
                    `🆔 معرف اللاعب: \`\${data.player_id}\`\n` +
                    `💰 السعر المطلوب: $${data.price}\n` +
                    `💳 وسيلة الدفع: ${data.payment_method}\n` +
                    `📝 الإثبات النصي: ${data.proof_text}`;

  const adminActions = Markup.inlineKeyboard([
    [Markup.button.callback('✅ موافقة وتفعيل وشحن', `admin_ok_${data.id}_${userId}`)],
    [Markup.button.callback('❌ رفض وإلغاء الطلب', `admin_no_${data.id}_${userId}`)]
  ]);

  if (data.proof_photo) {
    await bot.telegram.sendPhoto(ADMIN_ID, data.proof_photo, { caption: adminMsg, parse_mode: 'Markdown', ...adminActions });
  } else {
    await bot.telegram.sendMessage(ADMIN_ID, adminMsg, { parse_mode: 'Markdown', ...adminActions });
  }

  // تنظيف الجلسة المؤقتة بعد رفع الطلب بنجاح
  delete userSessions[userId];
}

// 5. نظام أزرار الأدمن لوحة التحكم: الموافقة
bot.action(/admin_ok_(.+)_(.+)/, async (ctx) => {
  if (ctx.from.id.toString() !== ADMIN_ID) return ctx.answerCbQuery('❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!');
  const [_, orderId, clientId] = ctx.match;

  await supabase.from('orders').update({ status: 'مكتمل' }).eq('id', orderId);

  ctx.editMessageCaption ? await ctx.editMessageCaption(`✅ تم قبول وشحن الطلب رقم #${orderId} بنجاح.`) : await ctx.editMessageText(`✅ تم قبول وشحن الطلب رقم #${orderId} بنجاح.`);
  
  bot.telegram.sendMessage(clientId, `🎉 بشرى سارة! تم التحقق من دفعتك اليدوية وشحن حسابك بالباقة المطلوبة للطلب رقم (#${orderId}). نتمنى لك وقتاً ممتعاً!`);
});

// 6. نظام أزرار الأدمن لوحة التحكم: الرفض
bot.action(/admin_no_(.+)_(.+)/, async (ctx) => {
  if (ctx.from.id.toString() !== ADMIN_ID) return ctx.answerCbQuery('❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!');
  const [_, orderId, clientId] = ctx.match;

  await supabase.from('orders').update({ status: 'مرفوض' }).eq('id', orderId);

  ctx.editMessageCaption ? await ctx.editMessageCaption(`❌ تم رفض وإلغاء الطلب رقم #${orderId}.`) : await ctx.editMessageText(`❌ تم رفض وإلغاء الطلب رقم #${orderId}.`);
  
  bot.telegram.sendMessage(clientId, `⚠️ إشعار: تم رفض طلب الشحن رقم (#${orderId}) بسبب عدم وصول قيمة التحويل أو خطأ بالإيصال المرفق. يرجى مراجعة الدعم الفني.`);
});

// تشغيل البوت المتوافق مع سرفرات الويب وهندسة Render المستمرة عبر Webhook
const PORT = process.env.PORT || 3000;
bot.launch({
  webhook: {
    domain: process.env.RENDER_EXTERNAL_URL,
    port: PORT
  }
}).then(() => console.log(`🚀 Telegram Game-Shop WebApp Backend is online via Webhook on port ${PORT}`));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
