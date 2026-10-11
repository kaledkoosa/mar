const { Telegraf, Markup } = require('telegraf');
const { createClient } = require('@supabase/supabase-js');
const path = require('path');
const express = require('express');
require('dotenv').config();

// إعداد خادم الويب والمكتبات الأساسية
const app = express();
const bot = new Telegraf(process.env.BOT_TOKEN);
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);
const ADMIN_ID = process.env.ADMIN_ID;

// ذاكرة تخزين مؤقتة لحالات المستخدمين الحالية (User Sessions)
const userSessions = {};

// معلومات وسائل الدفع اليدوية
const paymentDetails = {
  shamcash: { name: 'شام كاش (ShamCash)', msg: 'يرجى التحويل إلى حساب شام كاش رقم: [09xxxxxxxx]' },
  cwallet: { name: 'محفظة CWallet (يدوي)', msg: 'يرجى التحويل إلى عنوان USDT (TRC20):\n`TYxxxxxxxxxxxxxxxxxxxxxxxx`' }
};

// تشغيل ميزة تقديم صفحة الويب تلقائياً من مجلد frontend
app.use(express.static(path.join(__dirname, 'frontend')));

// 1. أمر التشغيل الأولي للمستخدم /start
bot.start(async (ctx) => {
  const userId = ctx.from.id.toString();
  userSessions[userId] = {}; // إعادة تعيين جلسة المستخدم لتفادي الأخطاء

  try {
    // حفظ أو تحديث بيانات العميل في قاعدة بيانات Supabase
    await supabase.from('users').upsert({ 
      user_id: userId, 
      username: ctx.from.username || 'N/A',
      full_name: ctx.from.first_name || 'N/A'
    });
  } catch (dbError) {
    console.error('Supabase Error:', dbError);
  }

  // إرسال زر فتح واجهة الويب واستخدام رابط Render تلقائياً كمصدر للموقع
  ctx.reply(`👋 مرحباً بك في متجر شحن الألعاب الإلكترونية!\n\nاضغط على الزر بالأسفل لفتح المتجر واختيار عروضك المفضلة:`,
    Markup.keyboard([
      [Markup.button.webApp('🎮 فتح المتجر الإلكتروني', process.env.RENDER_EXTERNAL_URL)]
    ]).resize()
  );
});

// 2. استقبال وقراءة البيانات القادمة من واجهة الويب (Web App Data)
bot.on('web_app_data', async (ctx) => {
  try {
    const data = JSON.parse(ctx.message.web_app_data.data);
    const userId = ctx.from.id.toString();

    // حفظ تفاصيل الطلب مؤقتاً في السيرفر بانتظار رفع الإثبات اليدوي
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
              `📥 *خطوة أخيرة:* بعد إتمام عملية التحويل بنجاح، يرجى إرسال صورة إيصال التحويل (إشعار) أو كتابة رقم العملية هنا مباشرة كرسالة لتأكيد طلبك:`, 
      { parse_mode: 'Markdown' }
    );

  } catch (err) {
    console.error('Error handling WebApp Data:', err);
    ctx.reply('❌ حدث خطأ غير متوقع أثناء قراءة بيانات طلبك، يرجى إعادة المحاولة من داخل واجهة المتجر.');
  }
});

// 3. استقبال صورة الإشعار المرفوعة من العميل كإثبات دفع
bot.on('photo', async (ctx) => {
  const userId = ctx.from.id.toString();
  const session = userSessions[userId];

  if (session && session.step === 'WAITING_PROOF') {
    session.proofPhoto = ctx.message.photo[ctx.message.photo.length - 1].file_id;
    session.proofText = ctx.message.caption || 'تم إرفاق صورة إشعار التحويل اليدوي';
    await processAndSendToAdmin(ctx, userId, session);
  }
});

// 4. استقبال النص كإثبات دفع في حال كتب العميل رقم العملية كتابةً
bot.on('text', async (ctx) => {
  const userId = ctx.from.id.toString();
  const session = userSessions[userId];

  if (!session || session.step !== 'WAITING_PROOF') return;

  session.proofPhoto = null;
  session.proofText = ctx.message.text;
  await processAndSendToAdmin(ctx, userId, session);
});

// دالة معالجة وحفظ الطلب وإرساله إلى حساب الأدمن للمراجعة
async function processAndSendToAdmin(ctx, userId, session) {
  try {
    const methodTitle = paymentDetails[session.paymentMethod].name;

    // تسجيل وحفظ الطلب في قاعدة بيانات Supabase بحالة "بانتظار المراجعة"
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

    if (error) throw error;

    ctx.reply('✅ شكراً لك! تم رفع إثبات الدفع وإرسال طلبك للإدارة بنجاح. سيتم مراجعة حسابنا وشحن حسابك وتنبيهك فوراً.');

    // صياغة رسالة التحكم والتحقق الخاصة بالأدمن (صاحب المتجر)
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

    // تنظيف الجلسة المؤقتة بعد رفع الطلب بنجاح للعميل
    delete userSessions[userId];

  } catch (err) {
    console.error('Database insertion error:', err);
    ctx.reply('❌ فشل تسجيل الطلب في قاعدة البيانات. يرجى إعادة المحاولة لاحقاً.');
  }
}

// 5. زر لوحة تحكم الأدمن: موافقة وتفعيل الطلب وشحن الجواهر للاعب
bot.action(/admin_ok_(.+)_(.+)/, async (ctx) => {
  if (ctx.from.id.toString() !== ADMIN_ID) return ctx.answerCbQuery('❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!');
  const [_, orderId, clientId] = ctx.match;

  await supabase.from('orders').update({ status: 'مكتمل' }).eq('id', orderId);

  ctx.editMessageCaption ? await ctx.editMessageCaption(`✅ تم قبول وشحن الطلب رقم #${orderId} بنجاح.`) : await ctx.editMessageText(`✅ تم قبول وشحن الطلب رقم #${orderId} بنجاح.`);
  
  bot.telegram.sendMessage(clientId, `🎉 بشرى سارة! تم التحقق من دفعتك اليدوية وشحن حسابك بالباقة المطلوبة للطلب رقم (#${orderId}). نتمنى لك وقتاً ممتعاً!`);
});

// 6. زر لوحة تحكم الأدمن: رفض وإلغاء الطلب في حال وجود خطأ في التحويل
bot.action(/admin_no_(.+)_(.+)/, async (ctx) => {
  if (ctx.from.id.toString() !== ADMIN_ID) return ctx.answerCbQuery('❌ عذراً، هذا الإجراء مخصص لمالك المتجر فقط!');
  const [_, orderId, clientId] = ctx.match;

  await supabase.from('orders').update({ status: 'مرفوض' }).eq('id', orderId);

  ctx.editMessageCaption ? await ctx.editMessageCaption(`❌ تم رفض وإلغاء الطلب رقم #${orderId}.`) : await ctx.editMessageText(`❌ تم رفض وإلغاء الطلب رقم #${orderId}.`);
  
  bot.telegram.sendMessage(clientId, `⚠️ إشعار: تم رفض طلب الشحن رقم (#${orderId}) بسبب عدم وصول قيمة التحويل أو خطأ بالإيصال المرفق. يرجى مراجعة الدعم الفني.`);
});

// 7. تهيئة وتشغيل الـ Webhook المتقدم والمتطابق مع سيرفرات Render لتجنب الـ Timeout
const PORT = process.env.PORT || 3000;
const secretPath = `/telegraf/${bot.secretPathComponent()}`;

app.use(bot.webhookCallback(secretPath));

// التحقق من المتغير البيئي لرابط ريندر قبل تعيين الـ Webhook
if (process.env.RENDER_EXTERNAL_URL) {
  bot.telegram.setWebhook(`${process.env.RENDER_EXTERNAL_URL}${secretPath}`)
    .then(() => console.log('✅ Webhook has been set successfully on Render!'));
} else {
  console.log('⚠️ Warning: RENDER_EXTERNAL_URL is not defined. Bot will look for it upon deployment.');
}

app.listen(PORT, () => {
  console.log(`🚀 Server is listening for both WebApp and Bot on port ${PORT}`);
});

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
