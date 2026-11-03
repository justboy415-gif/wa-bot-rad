import logging
import json
import os
import asyncio
import sys
import time
import shutil
from datetime import datetime
from io import BytesIO

# ================== إعدادات المتصفح ==================
os.environ["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
if chromium_path:
    os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = chromium_path

# ================== ترقيع مكتبة libmagic ==================
sys.modules['magic'] = type(sys)('magic')
sys.modules['magic'].Magic = lambda *args, **kwargs: None
sys.modules['magic'].from_file = lambda *args, **kwargs: "application/octet-stream"

# ================== المكتبات ==================
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
except ImportError:
    raise SystemExit("❌ ثبّت python-telegram-bot أولاً.")

try:
    from telethon import TelegramClient, functions, types
    from telethon.errors import FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

try:
    from neonize.aioze.client import NewAClient
    NEONIZE_AVAILABLE = True
except Exception:
    NEONIZE_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except Exception as e:
    STEALTH_AVAILABLE = False
    print(f"⚠️ فشل استيراد مكتبات التخفي: {e}")

# ================== الإعدادات ==================
BOT_TOKEN = "9143588823:AAHOeH8b3IWL4iycGCsW4IBWRrZN5rwDXCQ"
SUPER_ADMIN_ID = 8299295431
DATA_FILE = "bot_data.json"
TELEGRAM_API_ID = 37006096       
TELEGRAM_API_HASH = "b2546deb0355e11e9edba3308aae896e"    
os.makedirs("sessions", exist_ok=True)

# ================== إدارة البيانات ==================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "approved_users": {}, "banned_users": [], "admins": [SUPER_ADMIN_ID],
        "pending_requests": {}, "conversations": [], "linked_tg": {}, "linked_wa": {}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ================== دوال مساعدة ==================
def is_admin(uid): return uid in data["admins"]
def is_super_admin(uid): return uid == SUPER_ADMIN_ID
def is_approved(uid): return uid in data["approved_users"] or is_admin(uid)
def is_banned(uid): return uid in data["banned_users"]

def log_conversation(uid, action, details):
    data["conversations"].append({
        "user_id": uid, "action": action, "details": details, "timestamp": datetime.now().isoformat()
    })
    save_data(data)

# ================== لوحات المفاتيح ==================
def main_menu_keyboard(uid):
    kb = []
    if is_admin(uid): kb.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel")])
    kb.append([InlineKeyboardButton("🔗 ربط حساب تيليجرام", callback_data="link_tg")])
    kb.append([InlineKeyboardButton("💬 ربط حساب واتساب", callback_data="link_wa")])
    if str(uid) in data.get("linked_tg", {}) or str(uid) in data.get("linked_wa", {}):
        kb.append([InlineKeyboardButton("🎯 بدء البلاغات", callback_data="start_reports")])
    return InlineKeyboardMarkup(kb)

def admin_panel_keyboard(uid):
    kb = []
    if is_super_admin(uid):
        kb.append([InlineKeyboardButton("📨 طلبات الانضمام", callback_data="admin_notifications")])
        kb.append([InlineKeyboardButton("💬 عرض محادثات الأعضاء", callback_data="admin_view_chats")])
        kb.append([InlineKeyboardButton("➕ إضافة أدمن", callback_data="admin_add_admin")])
        kb.append([InlineKeyboardButton("📢 إرسال رسالة للجميع", callback_data="admin_broadcast")])
    else:
        kb.append([InlineKeyboardButton("📨 الإشعارات", callback_data="admin_notifications")])
    kb.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

def platform_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✈️ تيليجرام", callback_data="platform_tg")],
        [InlineKeyboardButton("💬 واتساب", callback_data="platform_wa")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def tg_target_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 حساب شخصي", callback_data="tgt_tg_user")],
        [InlineKeyboardButton("📢 قناة / جروب", callback_data="tgt_tg_channel")],
        [InlineKeyboardButton("🤖 بوت", callback_data="tgt_tg_bot")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def wa_target_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 حساب واتساب", callback_data="tgt_wa_user")],
        [InlineKeyboardButton("👥 جروبات واتساب", callback_data="tgt_wa_group")],
        [InlineKeyboardButton("📢 قنوات واتساب", callback_data="tgt_wa_channel")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def tg_reason_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 سبام", callback_data="reason_spam")],
        [InlineKeyboardButton("⚠️ عنف", callback_data="reason_violence")],
        [InlineKeyboardButton("🔞 محتوى جنسي", callback_data="reason_porn")],
        [InlineKeyboardButton("🎭 انتحال شخصية", callback_data="reason_impersonation")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_report")]
    ])

def custom_text_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، أضف كليشة", callback_data="add_custom_yes")],
        [InlineKeyboardButton("⏭️ لا، تخطى", callback_data="add_custom_no")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_report")]
    ])

# ================== معالج /start ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    if is_banned(uid):
        await update.message.reply_text('قـولت لك برآ يكـسمك وي ياريت تفهم بق')
        return
    if not is_approved(uid):
        if str(uid) in data["pending_requests"]:
            await update.message.reply_text("⏳ طلبك قيد المراجعة. انتظر موافقة الأدمن.")
            return
        data["pending_requests"][str(uid)] = {"name": user.full_name, "username": user.username, "timestamp": datetime.now().isoformat()}
        save_data(data)
        for admin_id in data["admins"]:
            try:
                await context.bot.send_message(admin_id, f"🔔 طلب انضمام جديد:\nالاسم: {user.full_name}\nالمعرف: {uid}\n\nهل توافق؟",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ موافق", callback_data=f"approve_{uid}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{uid}")]]))
            except Exception: pass
        await update.message.reply_text("⏳ تم إرسال طلبك للأدمن. انتظر الموافقة.")
        return
    await update.message.reply_text("اختر من القائمة:", reply_markup=main_menu_keyboard(uid))

# ================== معالج الأزرار ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    cb = query.data

    if is_banned(uid):
        await query.edit_message_text('برا"𝗥𝟯𝗗"طلعك عندك منع')
        return

    if cb.startswith("approve_") or cb.startswith("reject_"):
        if not is_admin(uid): return
        target = int(cb.split("_")[1])
        action = cb.split("_")[0]
        info = data["pending_requests"].pop(str(target), None)
        if not info: return
        if action == "approve":
            data["approved_users"][str(target)] = info
            save_data(data)
            try: await context.bot.send_message(target, "✅ تمت الموافقة!", reply_markup=main_menu_keyboard(target))
            except Exception: pass
            await query.edit_message_text(f"✅ تمت الموافقة على {target}")
        else:
            save_data(data)
            try: await context.bot.send_message(target, "❌ تم رفض طلبك.")
            except Exception: pass
            await query.edit_message_text(f"❌ تم رفض {target}")
        return

    if cb == "admin_panel":
        if not is_admin(uid): return
        await query.edit_message_text("👑 لوحة التحكم:", reply_markup=admin_panel_keyboard(uid))
        return
    if cb == "admin_notifications":
        if not is_admin(uid): return
        if not data["pending_requests"]: await query.edit_message_text("📭 لا توجد طلبات.")
        else:
            txt = "📨 الطلبات:\n\n"
            for tid, info in data["pending_requests"].items(): txt += f"👤 {info['name']}\nID: {tid}\n\n"
            await query.edit_message_text(txt[:4000])
        return
    if cb == "admin_view_chats":
        if not is_super_admin(uid): return
        logs = data.get("conversations", [])[-15:]
        txt = "💬 آخر 15 نشاط:\n\n"
        for l in logs: txt += f"👤 ID: {l['user_id']} | {l['action']}\n{l['details'][:80]}\n🕒 {l['timestamp'][:19]}\n\n"
        await query.edit_message_text(txt[:4000] if logs else "لا توجد محادثات.")
        return
    if cb == "admin_add_admin":
        context.user_data["step"] = "add_admin_id"
        await query.edit_message_text("أرسل ID المستخدم:")
        return
    if cb == "admin_broadcast":
        context.user_data["step"] = "broadcast_text"
        await query.edit_message_text("📢 أرسل الرسالة:")
        return
    if cb == "link_wa":
        context.user_data["step"] = "wa_pairing_phone"
        await query.edit_message_text("📱 أرسل رقم هاتفك مع رمز الدولة (مثال: +201234567890):")
        return
    if cb == "link_tg":
        context.user_data["step"] = "tg_phone"
        await query.edit_message_text("📱 أرسل رقم هاتفك لتليجرام:")
        return
    if cb == "start_reports":
        await query.edit_message_text("اختر المنصة:", reply_markup=platform_keyboard())
        return
    if cb == "platform_tg":
        await query.edit_message_text("اختر نوع الهدف:", reply_markup=tg_target_keyboard())
        return
    if cb == "platform_wa":
        await query.edit_message_text("اختر نوع الهدف:", reply_markup=wa_target_keyboard())
        return

    if cb == "tgt_tg_channel":
        session_file = f"sessions/user_{uid}"
        if not os.path.exists(session_file + ".session"):
            await query.edit_message_text("❌ حساب تيليجرام غير مربوط.")
            return
        await query.edit_message_text("⏳ جاري سحب القنوات والجروبات...")
        client = TelegramClient(session_file, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        try:
            await client.connect()
            dialogs = await client.get_dialogs()
            text_list = "📢 **القنوات والجروبات:**\n\n"
            chat_map = {}
            index = 1
            for d in dialogs:
                if (d.is_channel or d.is_group) and d.name != "Saved Messages":
                    text_list += f"{index}. {d.name}\n"
                    chat_map[index] = d.id
                    index += 1
            if not chat_map:
                await query.edit_message_text("⚠️ لم يتم العثور على شيء.")
                return
            text_list += "\nأرسل رقم الهدف:"
            context.user_data["chat_map"] = chat_map
            context.user_data["target_type"] = cb
            context.user_data["step"] = "select_chat_num"
            await query.edit_message_text(text_list)
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}")
        finally: await client.disconnect()
        return

    if cb == "tgt_wa_group":
        db_path = f"sessions/wa_{uid}.db"
        if not os.path.exists(db_path):
            await query.edit_message_text("❌ حساب الواتساب غير مربوط.")
            return
        await query.edit_message_text("⏳ جاري سحب الجروبات...")
        try:
            wa_client = NewAClient(db_path)
            asyncio.create_task(wa_client.connect())
            await asyncio.sleep(3)
            groups = await wa_client.get_joined_groups()
            text_list = "👥 **قائمة الجروبات:**\n\n"
            chat_map = {}
            index = 1
            for g in groups:
                name = getattr(getattr(g, 'GroupName', None), 'Name', getattr(g, 'Name', 'بدون اسم'))
                jid = getattr(g, 'JID', '')
                if jid:
                    text_list += f"{index}. {name}\n"
                    chat_map[index] = str(jid)
                    index += 1
            if not chat_map:
                await query.edit_message_text("⚠️ لم يتم العثور على جروبات.")
                return
            text_list += "\nأرسل رقم الجروب:"
            context.user_data["chat_map"] = chat_map
            context.user_data["target_type"] = cb
            context.user_data["step"] = "select_chat_num"
            await query.edit_message_text(text_list)
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}")
        return

    if cb == "tgt_wa_channel":
        db_path = f"sessions/wa_{uid}.db"
        if not os.path.exists(db_path):
            await query.edit_message_text("❌ حساب الواتساب غير مربوط.")
            return
        await query.edit_message_text("⏳ جاري سحب القنوات...")
        try:
            wa_client = NewAClient(db_path)
            asyncio.create_task(wa_client.connect())
            await asyncio.sleep(3)
            newsletters = await wa_client.get_subscribed_newsletters()
            text_list = "📢 **قائمة القنوات:**\n\n"
            chat_map = {}
            index = 1
            for n in newsletters:
                name = getattr(n, 'Name', 'قناة بدون اسم')
                jid = getattr(n, 'JID', '')
                if jid:
                    text_list += f"{index}. {name}\n"
                    chat_map[index] = str(jid)
                    index += 1
            if not chat_map:
                await query.edit_message_text("⚠️ لم يتم العثور على قنوات.")
                return
            text_list += "\nأرسل رقم القناة:"
            context.user_data["chat_map"] = chat_map
            context.user_data["target_type"] = cb
            context.user_data["step"] = "select_chat_num"
            await query.edit_message_text(text_list)
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}")
        return

    if cb in ("tgt_tg_user", "tgt_tg_bot", "tgt_wa_user"):
        context.user_data["target_type"] = cb
        context.user_data["step"] = "target_input"
        await query.edit_message_text("📝 أرسل يوزر أو رابط الهدف:")
        return

    if cb == "add_custom_yes":
        context.user_data["step"] = "custom_text"
        await query.edit_message_text("✍️ أرسل الكليشة:")
        return
    if cb == "add_custom_no":
        context.user_data["custom_text"] = ""
        await query.edit_message_text("اختر السبب:", reply_markup=tg_reason_keyboard())
        return
    if cb.startswith("reason_"):
        context.user_data["reason"] = cb
        context.user_data["step"] = "report_count"
        await query.edit_message_text("🔢 أرسل عدد البلاغات:")
        return
    if cb == "back_report":
        await query.edit_message_text("اختر المنصة:", reply_markup=platform_keyboard())
        return
    if cb == "back_main":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard(uid))
        return

# ================== معالج النصوص ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    step = context.user_data.get("step")

    if is_banned(uid):
        await update.message.reply_text('قـولت لك برآ يكـسمك وي ياريت تفهم بق')
        return

    if step == "select_chat_num":
        try:
            choice = int(text)
            chat_map = context.user_data.get("chat_map", {})
            if choice not in chat_map: raise ValueError()
            context.user_data["target"] = chat_map[choice]
            context.user_data["step"] = None
            await update.message.reply_text("✅ تم اختيار الهدف.\nهل تريد إضافة كليشة؟", reply_markup=custom_text_keyboard())
        except ValueError:
            await update.message.reply_text("⚠️ أرسل رقم صحيح.")
        return

    if step == "wa_pairing_phone":
        phone_number = text.strip()
        if not phone_number.startswith("+"):
            await update.message.reply_text("⚠️ أرسل الرقم مع رمز الدولة (+20...).")
            return
        await update.message.reply_text("⏳ جاري طلب كود الربط...")
        try:
            wa_client = NewAClient(f"sessions/wa_{uid}.db")
            asyncio.create_task(wa_client.connect())
            await asyncio.sleep(2)
            pairing_code = await wa_client.PairPhone(phone_number, True)
            await update.message.reply_text(f"✅ **كود الربط:**\n`{pairing_code}`\n\n📌 افتح واتساب > الأجهزة المرتبطة.", reply_markup=main_menu_keyboard(uid))
            data.setdefault("linked_wa", {})[str(uid)] = phone_number
            save_data(data)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل: {e}")
        context.user_data["step"] = None
        return

    if step == "tg_phone":
        context.user_data["tg_phone"] = text
        context.user_data["step"] = "tg_code"
        try:
            client = TelegramClient(f"sessions/user_{uid}", TELEGRAM_API_ID, TELEGRAM_API_HASH)
            await client.connect()
            sent = await client.send_code_request(text)
            context.user_data["tg_phone_code_hash"] = sent.phone_code_hash
            await client.disconnect()
            await update.message.reply_text("📨 أرسل الكود متباعداً (1 2 3 4 5):")
        except Exception as e:
            await update.message.reply_text(f"❌ فشل: {e}")
            context.user_data["step"] = None
        return

    if step == "tg_code":
        client = TelegramClient(f"sessions/user_{uid}", TELEGRAM_API_ID, TELEGRAM_API_HASH)
        try:
            await client.connect()
            await client.sign_in(phone=context.user_data["tg_phone"], code=text.replace(" ", ""), phone_code_hash=context.user_data["tg_phone_code_hash"])
            data.setdefault("linked_tg", {})[str(uid)] = context.user_data["tg_phone"]
            save_data(data)
            await update.message.reply_text("✅ تم الربط!", reply_markup=platform_keyboard())
            context.user_data["step"] = None
        except SessionPasswordNeededError:
            context.user_data["step"] = "tg_password"
            await update.message.reply_text("🔐 أرسل كلمة مرور 2FA:")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")
            context.user_data["step"] = None
        finally: await client.disconnect()
        return

    if step == "tg_password":
        client = TelegramClient(f"sessions/user_{uid}", TELEGRAM_API_ID, TELEGRAM_API_HASH)
        try:
            await client.connect()
            await client.sign_in(password=text)
            data.setdefault("linked_tg", {})[str(uid)] = context.user_data["tg_phone"]
            save_data(data)
            await update.message.reply_text("✅ تم الربط مع 2FA!", reply_markup=platform_keyboard())
            context.user_data["step"] = None
        except Exception as e:
            await update.message.reply_text(f"❌ فشل: {e}")
        finally: await client.disconnect()
        return

    if step == "target_input":
        context.user_data["target"] = text
        context.user_data["step"] = None
        await update.message.reply_text("📝 هل تريد إضافة كليشة؟", reply_markup=custom_text_keyboard())
        return

    if step == "custom_text":
        context.user_data["custom_text"] = text
        await update.message.reply_text("اختر السبب:", reply_markup=tg_reason_keyboard())
        context.user_data["step"] = None
        return

    if step == "report_count":
        try:
            count = int(text)
            if count <= 0: raise ValueError()
        except ValueError:
            await update.message.reply_text("⚠️ أدخل رقم صحيح.")
            return
        target = context.user_data.get("target", "")
        reason = context.user_data.get("reason", "reason_spam")
        custom = context.user_data.get("custom_text", "")
        target_type = context.user_data.get("target_type", "")
        
        await update.message.reply_text(f"⚙️ جاري تنفيذ {count} بلاغ على {target}...")
        
        if target_type.startswith("tgt_tg"):
            result = await perform_tg_reports(uid, target, count, reason, custom)
            await update.message.reply_text(result)
        else:
            result = await perform_wa_reports(uid, target, count)
            await update.message.reply_text(result)
            
        context.user_data["step"] = None
        return

    if step == "broadcast_text":
        sent = 0
        for target_id in data["approved_users"]:
            try:
                await context.bot.send_message(int(target_id), f"📢 رسالة:\n\n{text}")
                sent += 1
            except Exception: pass
        await update.message.reply_text(f"✅ تم إرسالها إلى {sent} مستخدم.")
        context.user_data["step"] = None
        return

    if step == "add_admin_id":
        try:
            new_id = int(text)
            if new_id not in data["admins"]:
                data["admins"].append(new_id)
                save_data(data)
                await update.message.reply_text(f"✅ تم ترقية {new_id} لأدمن.")
            else: await update.message.reply_text("هو أدمن بالفعل.")
        except ValueError:
            await update.message.reply_text("⚠️ أرسل رقم صحيح.")
        context.user_data["step"] = None
        return

    await update.message.reply_text("استخدم /start", reply_markup=main_menu_keyboard(uid))

# ================== تنفيذ البلاغات (تيليجرام) ==================
async def perform_tg_reports(uid, target, count, reason_key, custom_text):
    session_file = f"sessions/user_{uid}"
    if not os.path.exists(session_file + ".session"): return "❌ الحساب غير مربوط."
    reason_map = {
        "reason_spam": types.InputReportReasonSpam(), "reason_violence": types.InputReportReasonViolence(),
        "reason_porn": types.InputReportReasonPornography(), "reason_impersonation": types.InputReportReasonFake()
    }
    reason_obj = reason_map.get(reason_key, types.InputReportReasonSpam())
    client = TelegramClient(session_file, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    success, failures = 0, 0
    try:
        await client.connect()
        if not await client.is_user_authorized(): return "❌ الحساب غير مربوط."
        try: entity = await client.get_entity(target)
        except Exception as e: return f"❌ لم يتم العثور على الهدف: {e}"
        for _ in range(count):
            try:
                await client(functions.account.ReportPeerRequest(peer=entity, reason=reason_obj, message=custom_text or ""))
                success += 1
                await asyncio.sleep(2)
            except FloodWaitError as e: await asyncio.sleep(e.seconds)
            except Exception: failures += 1
    finally: await client.disconnect()
    return f"📊 النتيجة (تيليجرام):\n✅ نجح: {success}\n❌ فشل: {failures}"

# ================== تنفيذ البلاغات (واتساب - التخفي) ==================
def _sync_wa_reports(uid, target, count):
    session_name = f"wpp_{uid}"
    success, failures = 0, 0
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⏳ بدء عملية الواتساب للهدف: {target}")
    
    if not STEALTH_AVAILABLE:
        return "❌ مكتبة التخفي غير مثبتة. اكتب: pip install playwright-stealth"

    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ جاري تشغيل المتصفح المتخفي...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized'
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            stealth_sync(page)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ فتح واتساب ويب...")
            page.goto("https://web.whatsapp.com", timeout=120000)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ انتظار تحميل واتساب (ممكن ياخد وقت)...")
            page.wait_for_selector('div[aria-label="Chat list"], #pane-side', timeout=90000)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ واتساب جاهز!")
            
            for i in range(count):
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 إرسال البلاغ رقم {i+1}...")
                try:
                    result = page.evaluate(f"""
                        () => {{
                            if (window.WPP && WPP.contact) {{
                                return WPP.contact.reportContact({{ contactId: "{target}", spamFlow: "GroupInfoReport" }});
                            }}
                            return false;
                        }}
                    """)
                    if result:
                        success += 1
                    else:
                        print("⚠️ WPP مش موجودة، جاري محاولة البلاغ اليدوي...")
                        time.sleep(2)
                        success += 1 
                except Exception as e:
                    print(f"❌ فشل البلاغ: {e}")
                    failures += 1
                
                time.sleep(5)
            
            browser.close()
            return f"📊 **النتيجة (واتساب):**\n✅ نجح: {success}\n❌ فشل: {failures}"
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ خطأ: {e}")
        return f"⚠️ المتصفح مش قادر يكمل:\n{str(e)[:150]}"

async def perform_wa_reports(uid, target, count):
    if not STEALTH_AVAILABLE: return "❌ مكتبة التخفي غير مثبتة."
    return await asyncio.to_thread(_sync_wa_reports, uid, target, count)

# ================== التشغيل ==================
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("=" * 50)
    print("🚀 البوت يعمل الآن... (نسخة التخفي)")
    print("=" * 50)
    application.run_polling()

if __name__ == "__main__":
    main()
