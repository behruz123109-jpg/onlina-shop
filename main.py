import asyncio
import logging
import math

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
)

# ──────────────────────────────────────────
# KONFIGURATSIYA
# ──────────────────────────────────────────
BOT_TOKEN = "8747604242:AAFj9oSG5txNx1Pw7UfCAc9WH_Em8tB73p0"
SUPER_ADMIN_ID = 8488028783
DB_PATH = "shop_pro.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

STATUSES = {
    "new": "⏳ Tasdiqlanmoqda",
    "pending_courier": "🔎 Kuryer kutilmoqda",
    "on_way": "🚚 Yo'lga chiqdi",
    "delivered": "🎉 Yetkazildi",
    "cancelled": "❌ Bekor qilingan"
}


# ──────────────────────────────────────────
# FSM HOLATLARI
# ──────────────────────────────────────────
class Reg(StatesGroup): name = State(); phone = State()


class Shop(StatesGroup): search = State()


class Checkout(StatesGroup): loc = State(); landmark = State(); payment = State(); receipt = State()


class ProfileSt(StatesGroup): new_name = State()


class ReviewSt(StatesGroup): rating = State(); comment = State()


class AdminSt(StatesGroup):
    cat_name = State();
    cat_edit_name = State()
    prod_cat = State();
    prod_name = State();
    prod_desc = State();
    prod_price = State();
    prod_stock = State();
    prod_photo = State()
    admin_add = State()
    pay_name = State();
    pay_details = State()
    set_fee = State();
    custom_msg = State()
    ban_user = State();
    bcast_msg = State()
    set_loc = State()


# ──────────────────────────────────────────
# BAZA VA YORDAMCHILAR
# ──────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, tg_id INTEGER UNIQUE, name TEXT, phone TEXT, is_blocked INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now','localtime')));
        CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, tg_id INTEGER UNIQUE, name TEXT, role TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, description TEXT, price INTEGER, stock INTEGER DEFAULT 0, photo_id TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS cart (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER DEFAULT 1, UNIQUE(user_id, product_id));
        CREATE TABLE IF NOT EXISTS payment_methods (id INTEGER PRIMARY KEY, type TEXT, name TEXT, details TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER, courier_id INTEGER DEFAULT 0, status TEXT DEFAULT 'new',
            total_amount INTEGER DEFAULT 0, delivery_fee INTEGER DEFAULT 0, payment_method_id TEXT, phone TEXT,
            lat REAL, lon REAL, landmark TEXT, receipt_id TEXT DEFAULT '', cancel_reason TEXT DEFAULT '',
            distance REAL DEFAULT 0.0, created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, quantity INTEGER, price INTEGER);
        CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, user_id INTEGER, order_id INTEGER, product_id INTEGER, rating INTEGER, comment TEXT);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        await db.execute("INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,'Super Admin','admin')",
                         (SUPER_ADMIN_ID,))

        pay_exists = await db.execute("SELECT id FROM payment_methods LIMIT 1")
        if not await pay_exists.fetchone():
            await db.execute(
                "INSERT INTO payment_methods(type, name, details) VALUES('card', 'Uzcard - Asosiy', '8600123456789012 (Eshmatov T.)')")

        defaults = [("shop_lat", "41.311081"), ("shop_lon", "69.240562"), ("fee_per_km", "5000"), ("is_open", "1")]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        await db.commit()


async def exe(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, params);
        await db.commit()


async def q1(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as c:
            r = await c.fetchone();
            return dict(r) if r else None


async def qall(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as c:
            return [dict(r) for r in await c.fetchall()]


def fmt(n): return f"{int(n or 0):,}".replace(",", " ")


def calc_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1);
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(
        dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def return_stock(oid: int):
    items = await qall("SELECT * FROM order_items WHERE order_id=?", (oid,))
    for i in items: await exe("UPDATE products SET stock=stock+? WHERE id=?", (i["quantity"], i["product_id"]))


async def is_shop_open():
    st = await q1("SELECT value FROM settings WHERE key='is_open'")
    return st and st['value'] == "1"


# ──────────────────────────────────────────
# BOT VA KLAVIATURALAR
# ──────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
dp = Dispatcher(storage=MemoryStorage())


def ik(*rows): return InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows])


def rk(*rows): return ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t) if isinstance(t, str) else t for t in row] for row in rows], resize_keyboard=True)


CANCEL_KB = rk(["❌ Bekor qilish"])


async def main_kb(tg_id: int):
    adm = await q1("SELECT role FROM admins WHERE tg_id=? AND is_active=1", (tg_id,))
    rows = [["🛍 Katalog", "🔍 Qidiruv"], ["🛒 Savatcha", "📦 Buyurtmalarim"], ["👤 Profilim", "🆘 Yordam"]]
    if adm and adm["role"] == "admin": rows.append(["⚙️ Admin Panel"])
    if adm and adm["role"] in ["admin", "courier"]: rows.append(["🚚 Kuryer Panel"])
    return rk(*rows)


def admin_kb():
    return rk(
        ["📂 Bo'limlar", "📦 Mahsulotlar"],
        ["💳 To'lov usullari", "👥 Xodimlar"],
        ["🚫 Ban/Unban", "📊 Statistika"],
        ["⚙️ Sozlamalar", "📨 Broadcast"],
        ["🔙 Asosiy menyu"]
    )


def courier_kb():
    return rk(["📋 Kuryer: Mening buyurtmalarim", "🔙 Asosiy menyu"])


async def check_user(msg: Message, state: FSMContext):
    u = await q1("SELECT * FROM users WHERE tg_id=?", (msg.from_user.id,))
    if not u:
        await msg.answer("Iltimos, avval /start ni bosing.")
        return None
    if u['is_blocked']:
        await msg.answer("❌ Kechirasiz, sizning hisobingiz bloklangan.")
        return "blocked"
    return u


async def build_cart_msg(user_id: int):
    items = await qall(
        "SELECT c.id, c.product_id, c.quantity, p.name, p.price, p.stock FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
        (user_id,))
    if not items: return "🛒 Savatingiz bo'sh.", None
    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    rows = []
    for i in items:
        tot += i['price'] * i['quantity']
        warn = " ⚠️(Qolmagan)" if i['quantity'] > i['stock'] else ""
        txt += f"• {i['name']} ({i['quantity']} ta) = {fmt(i['price'] * i['quantity'])} so'm{warn}\n"
        rows.append(
            [("➖", f"cxdec_{i['product_id']}"), (f"{i['name'][:12]}", "noop"), ("➕", f"cxinc_{i['product_id']}")])
    txt += f"\n💰 Jami: <b>{fmt(tot)} so'm</b>"
    rows.append([("✅ Buyurtma berish", "checkout"), ("🗑 Tozalash", "cart_clear")])
    return txt, ik(*rows)


# ──────────────────────────────────────────
# GLOBAL BEKOR QILISH
# ──────────────────────────────────────────
@router.message(F.text == "❌ Bekor qilish")
async def global_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🚫 Amal bekor qilindi.", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "🔙 Asosiy menyu")
async def go_home(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🏠 Asosiy menyu", reply_markup=await main_kb(msg.from_user.id))


# ──────────────────────────────────────────
# 1. MIJOZ: START, PROFIL, YORDAM
# ──────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    u = await q1("SELECT * FROM users WHERE tg_id=?", (msg.from_user.id,))
    if u and u['is_blocked']: return await msg.answer("❌ Hisobingiz bloklangan.")

    if not u:
        await msg.answer("👋 Xush kelibsiz! Ismingizni yozing:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Reg.name)
    else:
        shop_st = "🟢 Ochiq" if await is_shop_open() else "🔴 Yopiq"
        await msg.answer(f"👋 Salom, {u['name']}!\nDo'kon holati: {shop_st}",
                         reply_markup=await main_kb(msg.from_user.id))


@router.message(Reg.name)
async def reg_name(msg: Message, state: FSMContext):
    if len(msg.text) < 2: return await msg.answer("Iltimos, to'g'ri ism yozing:")
    await state.update_data(name=msg.text.strip().title())
    await msg.answer("📱 Telefon raqamingizni yuboring:",
                     reply_markup=rk([KeyboardButton(text="📱 Raqam yuborish", request_contact=True)]))
    await state.set_state(Reg.phone)


@router.message(Reg.phone)
async def reg_phone(msg: Message, state: FSMContext):
    ph = msg.contact.phone_number if msg.contact else msg.text
    if not str(ph).startswith("+"): ph = "+" + str(ph)
    d = await state.get_data()
    await exe("INSERT INTO users(tg_id,name,phone) VALUES(?,?,?)", (msg.from_user.id, d["name"], ph))
    await state.clear()
    await msg.answer("🎉 Muvaffaqiyatli ro'yxatdan o'tdingiz!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "👤 Profilim")
async def cmd_profile(msg: Message, state: FSMContext):
    u = await check_user(msg, state)
    if u and u != "blocked":
        await msg.answer(
            f"👤 <b>Profilingiz</b>\n\n🆔 Ism: {u['name']}\n📱 Telefon: {u['phone']}\n📅 Ro'yxatdan: {u['created_at'][:10]}",
            reply_markup=ik([("✏️ Ismni o'zgartirish", "edit_name")]))


@router.callback_query(F.data == "edit_name")
async def edit_name(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✏️ Yangi ismni yozing:", reply_markup=CANCEL_KB)
    await state.set_state(ProfileSt.new_name);
    await call.answer()


@router.message(ProfileSt.new_name)
async def save_name(msg: Message, state: FSMContext):
    await exe("UPDATE users SET name=? WHERE tg_id=?", (msg.text.strip(), msg.from_user.id))
    await state.clear();
    await msg.answer("✅ Saqlandi!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "🆘 Yordam")
async def cmd_help(msg: Message):
    await msg.answer("🆘 <b>Yordam markazi</b>\n\nSavollaringiz bo'lsa tezkor yordam uchun adminga yozing.")


# ──────────────────────────────────────────
# 2. KATALOG VA SAVAT
# ──────────────────────────────────────────
@router.message(F.text == "🛍 Katalog")
async def cmd_catalog(msg: Message, state: FSMContext):
    if await check_user(msg, state) == "blocked": return
    if not await is_shop_open(): return await msg.answer("🔴 Kechirasiz, do'kon hozir yopiq. Keyinroq urinib ko'ring.")
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    if not cats: return await msg.answer("Bo'limlar hozircha bo'sh.")
    await msg.answer("📂 <b>Bo'limni tanlang:</b>",
                     reply_markup=ik(*[[(f"📦 {c['name']}", f"cat_{c['id']}")] for c in cats]))


@router.callback_query(F.data.startswith("cat_"))
async def show_cat(call: CallbackQuery):
    prods = await qall("SELECT * FROM products WHERE category_id=? AND is_active=1", (int(call.data[4:]),))
    if not prods: return await call.answer("Bo'lim bo'sh.", show_alert=True)
    kb = ik(*[[(f"🛒 {p['name']} - {fmt(p['price'])} so'm", f"prod_{p['id']}")] for p in prods],
            [("🔙 Orqaga", "back_cats")])
    try:
        await call.message.edit_text("🛍 <b>Mahsulotlar:</b>", reply_markup=kb)
    except:
        pass
    await call.answer()


@router.callback_query(F.data == "back_cats")
async def back_cats(call: CallbackQuery):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    try:
        await call.message.edit_text("📂 <b>Bo'limni tanlang:</b>",
                                     reply_markup=ik(*[[(f"📦 {c['name']}", f"cat_{c['id']}")] for c in cats]))
    except:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("prod_"))
async def show_prod(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT * FROM products WHERE id=?", (pid,))
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    qty = ci["quantity"] if ci else 0
    txt = f"📦 <b>{p['name']}</b>\n\n{p['description']}\n\n💰 {fmt(p['price'])} so'm | Ombor: {p['stock']} ta"
    btns = [[("➖", f"cdec_{pid}"), (f"🛒 {qty} ta", "noop"), ("➕", f"cinc_{pid}")]] if qty > 0 else [
        [("🛒 Savatga qo'shish", f"cinc_{pid}")]]
    btns.append([("🔙 Orqaga", f"cat_{p['category_id']}")])
    try:
        await call.message.delete()
    except:
        pass
    if p["photo_id"]:
        await bot.send_photo(call.from_user.id, p["photo_id"], caption=txt, reply_markup=ik(*btns))
    else:
        await bot.send_message(call.from_user.id, txt, reply_markup=ik(*btns))
    await call.answer()


@router.callback_query(F.data.startswith("cinc_"))
async def cart_inc(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT stock FROM products WHERE id=?", (pid,))
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if p and ci and ci["quantity"] >= p["stock"]: return await call.answer(f"Omborda faqat {p['stock']} ta bor!",
                                                                           show_alert=True)
    await exe(
        "INSERT INTO cart(user_id,product_id,quantity) VALUES(?,?,1) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=quantity+1",
        (call.from_user.id, pid))
    await show_prod(call)


@router.callback_query(F.data.startswith("cdec_"))
async def cart_dec(call: CallbackQuery):
    pid = int(call.data[5:]);
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if ci and ci["quantity"] == 1:
        await exe("DELETE FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    elif ci:
        await exe("UPDATE cart SET quantity=quantity-1 WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    await show_prod(call)


@router.message(F.text == "🔍 Qidiruv")
async def cmd_search(msg: Message, state: FSMContext):
    if await check_user(msg, state) == "blocked": return
    await state.clear()
    await msg.answer("🔍 Qidirish uchun mahsulot nomini yozing:", reply_markup=CANCEL_KB)
    await state.set_state(Shop.search)


@router.message(Shop.search)
async def do_search(msg: Message, state: FSMContext):
    res = await qall("SELECT * FROM products WHERE is_active=1 AND name LIKE ? LIMIT 10", (f"%{msg.text.strip()}%",))
    if not res: return await msg.answer("❌ Topilmadi. Boshqa so'z yozing:")
    await msg.answer("🔍 Natijalar:",
                     reply_markup=ik(*[[(f"🛒 {p['name']} - {fmt(p['price'])}", f"prod_{p['id']}")] for p in res]))
    await state.clear()


@router.message(F.text == "🛒 Savatcha")
async def cmd_cart(msg: Message, state: FSMContext):
    if await check_user(msg, state) == "blocked": return
    txt, kb = await build_cart_msg(msg.from_user.id)
    if kb:
        await msg.answer(txt, reply_markup=kb)
    else:
        await msg.answer(txt)


@router.callback_query(F.data.startswith("cxinc_"))
async def cxinc(call: CallbackQuery):
    pid = int(call.data[6:]);
    p = await q1("SELECT stock FROM products WHERE id=?", (pid,))
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if p and ci and ci["quantity"] >= p["stock"]: return await call.answer("Omborda yetarli emas!", show_alert=True)
    await exe("UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    txt, kb = await build_cart_msg(call.from_user.id)
    try:
        await call.message.edit_text(txt, reply_markup=kb)
    except:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("cxdec_"))
async def cxdec(call: CallbackQuery):
    pid = int(call.data[6:]);
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if ci:
        if ci["quantity"] <= 1:
            await exe("DELETE FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
        else:
            await exe("UPDATE cart SET quantity=quantity-1 WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    txt, kb = await build_cart_msg(call.from_user.id)
    try:
        if kb:
            await call.message.edit_text(txt, reply_markup=kb)
        else:
            await call.message.edit_text(txt)
    except:
        pass
    await call.answer()


@router.callback_query(F.data == "cart_clear")
async def cart_clear(call: CallbackQuery):
    await exe("DELETE FROM cart WHERE user_id=?", (call.from_user.id,))
    await call.message.edit_text("🛒 Savat tozalandi.")
    await call.answer()


# ──────────────────────────────────────────
# 3. ZAKAZ BERISH (CHECKOUT)
# ──────────────────────────────────────────
@router.callback_query(F.data == "checkout")
async def checkout_start(call: CallbackQuery, state: FSMContext):
    if not await is_shop_open(): return await call.answer("🔴 Kechirasiz, do'kon hozir yopiq.", show_alert=True)
    uid = call.from_user.id
    items = await qall(
        "SELECT c.quantity, p.id, p.name, p.stock FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
        (uid,))
    if not items: return await call.answer("Savat bo'sh!", show_alert=True)
    for i in items:
        if i["quantity"] > i["stock"]: return await call.answer(f"❌ {i['name']} omborda yetarli emas!", show_alert=True)

    try:
        await call.message.delete()
    except:
        pass
    btn = [KeyboardButton(text="📍 Xaritadan lokatsiya yuborish", request_location=True),
           KeyboardButton(text="❌ Bekor qilish")]
    await call.message.answer("📍 <b>Xaritadan aniq lokatsiyangizni yuboring:</b>", reply_markup=rk(btn))
    await state.set_state(Checkout.loc)
    await call.answer()


@router.message(Checkout.loc)
async def checkout_loc(msg: Message, state: FSMContext):
    if not msg.location: return await msg.answer("❌ Iltimos, pastdagi '📍 Lokatsiya yuborish' tugmasini bosing!")
    await state.update_data(lat=msg.location.latitude, lon=msg.location.longitude)
    await msg.answer("🏠 Endi aniq manzil va <b>Mo'ljalni (orientir)</b> yozing:\n<i>(Masalan: 4-dom, Makro orqasi)</i>",
                     reply_markup=CANCEL_KB)
    await state.set_state(Checkout.landmark)


@router.message(Checkout.landmark)
async def checkout_landmark(msg: Message, state: FSMContext):
    await state.update_data(landmark=msg.text.strip())
    pms = await qall("SELECT * FROM payment_methods WHERE is_active=1")
    btns = [[("💵 Naqd pul", "pay_cash")]]
    for pm in pms:
        if pm['type'] == 'card':
            btns.append([(f"💳 {pm['name']}", f"pay_{pm['id']}")])
        elif pm['type'] in ['click', 'payme']:
            btns.append([(f"📱 {pm['name']}", f"pay_{pm['id']}")])
    await msg.answer("💳 To'lov usulini tanlang:", reply_markup=ik(*btns))
    await state.set_state(Checkout.payment)


@router.callback_query(F.data.startswith("pay_"), Checkout.payment)
async def checkout_payment(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id;
    pay_data = call.data[4:]
    d = await state.get_data()
    items = await qall("SELECT c.*, p.price, p.name FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
                       (uid,))
    tot = sum(i["price"] * i["quantity"] for i in items)
    await state.update_data(tot=tot, items=items, pm_id=pay_data)
    try:
        await call.message.delete()
    except:
        pass

    if pay_data == "cash":
        await finalize_order(call.message, state, uid, "Naqd", tot, d['lat'], d['lon'], d['landmark'], items, "")
    else:
        pm = await q1("SELECT * FROM payment_methods WHERE id=?", (int(pay_data),))
        if pm['type'] == 'card':
            await call.message.answer(
                f"💳 <b>Karta orqali to'lov</b>\n\n🛍 Summa: <b>{fmt(tot)} so'm</b>\n<i>(Yo'l haqi alohida hisoblanadi)</i>\n\n"
                f"Karta: <code>{pm['details']}</code>\n\n📸 <b>To'lov chekini rasmga olib shu yerga yuboring:</b>",
                reply_markup=CANCEL_KB
            )
            await state.set_state(Checkout.receipt)
        elif pm['type'] in ['click', 'payme']:
            await call.message.answer("📱 API integratsiyasi kutilmoqda. Hozircha buyurtma berish tugmasini bosing:",
                                      reply_markup=ik([("✅ Buyurtma berish", "force_checkout")]))
    await call.answer()


@router.message(Checkout.receipt, F.photo)
async def checkout_receipt(msg: Message, state: FSMContext):
    d = await state.get_data();
    pm = await q1("SELECT name FROM payment_methods WHERE id=?", (int(d['pm_id']),))
    await finalize_order(msg, state, msg.from_user.id, pm['name'], d['tot'], d['lat'], d['lon'], d['landmark'],
                         d['items'], msg.photo[-1].file_id)


@router.callback_query(F.data == "force_checkout")
async def force_checkout(call: CallbackQuery, state: FSMContext):
    d = await state.get_data();
    pm = await q1("SELECT name FROM payment_methods WHERE id=?", (int(d['pm_id']),))
    await finalize_order(call.message, state, call.from_user.id, pm['name'] + "(Kutilmoqda)", d['tot'], d['lat'],
                         d['lon'], d['landmark'], d['items'], "")
    try:
        await call.message.delete()
    except:
        pass
    await call.answer()


async def finalize_order(msg, state, uid, pay_name, tot, lat, lon, landmark, items, receipt_id):
    user = await q1("SELECT phone, name FROM users WHERE tg_id=?", (uid,))
    s_lat = float((await q1("SELECT value FROM settings WHERE key='shop_lat'"))["value"])
    s_lon = float((await q1("SELECT value FROM settings WHERE key='shop_lon'"))["value"])
    km = calc_km(s_lat, s_lon, lat, lon)

    await exe(
        "INSERT INTO orders(user_id, total_amount, payment_method_id, phone, lat, lon, landmark, receipt_id, distance) VALUES(?,?,?,?,?,?,?,?,?)",
        (uid, tot, pay_name, user["phone"], lat, lon, landmark, receipt_id, km))
    oid = (await q1("SELECT id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)))["id"]

    items_txt = ""
    for i in items:
        await exe("INSERT INTO order_items(order_id,product_id,product_name,quantity,price) VALUES(?,?,?,?,?)",
                  (oid, i['product_id'], i['name'], i['quantity'], i['price']))
        await exe("UPDATE products SET stock=MAX(0,stock-?) WHERE id=?", (i["quantity"], i["product_id"]))
        items_txt += f"▫️ {i['name']} x {i['quantity']} = {fmt(i['price'] * i['quantity'])}\n"

    await exe("DELETE FROM cart WHERE user_id=?", (uid,))
    await state.clear()
    await msg.answer(f"🎉 <b>Buyurtma #{oid} qabul qilindi!</b>\nTez orada admin yo'lkirani tasdiqlaydi.",
                     reply_markup=await main_kb(uid))

    adm_txt = f"🆕 <b>Yangi Buyurtma #{oid}</b>\n👤 {user['name']} | 📱 {user['phone']}\n🏠 Mo'ljal: {landmark}\n📏 Masofa: {km:.1f} km\n💳 To'lov: {pay_name}\n\n🛍 <b>Mahsulotlar:</b>\n{items_txt}\n💰 Summa: {fmt(tot)} so'm"
    adms = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in adms:
        try:
            await bot.send_location(a["tg_id"], lat, lon)
            btns = ik([("💰 Yo'lkira kiritish", f"asetfee_{oid}")], [("❌ Rad etish", f"acancel_{oid}")])
            if receipt_id:
                await bot.send_photo(a["tg_id"], receipt_id, caption=adm_txt, reply_markup=btns)
            else:
                await bot.send_message(a["tg_id"], adm_txt, reply_markup=btns)
        except:
            pass


# ──────────────────────────────────────────
# 4. BUYURTMALARIM VA SHARHLAR
# ──────────────────────────────────────────
@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(msg: Message, state: FSMContext):
    if await check_user(msg, state) == "blocked": return
    ords = await qall("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (msg.from_user.id,))
    if not ords: return await msg.answer("Sizda buyurtmalar yo'q.")
    for o in ords:
        st = STATUSES.get(o["status"], o["status"])
        txt = f"📦 #{o['id']} | Holati: {st}\n💵 Jami: {fmt(o['total_amount'] + o['delivery_fee'])} so'm"
        btns = []
        if o["status"] == "new":
            btns.append([("❌ Bekor qilish", f"ucancel_{o['id']}")])
        elif o["status"] == "delivered":
            if not await q1("SELECT id FROM reviews WHERE order_id=?", (o['id'],)): btns.append(
                [("⭐ Baho berish", f"ureview_{o['id']}")])
        if btns:
            await msg.answer(txt, reply_markup=ik(*btns))
        else:
            await msg.answer(txt)


@router.callback_query(F.data.startswith("ucancel_"))
async def ucancel(call: CallbackQuery):
    oid = int(call.data[8:])
    await exe("UPDATE orders SET status='cancelled', cancel_reason='Mijoz ozi bekor qildi' WHERE id=?", (oid,))
    await return_stock(oid);
    await call.message.edit_text("✅ Buyurtma bekor qilindi.");
    await call.answer()


@router.callback_query(F.data.startswith("ureview_"))
async def ureview(call: CallbackQuery, state: FSMContext):
    await state.update_data(rev_oid=int(call.data[8:]))
    await call.message.edit_text("⭐ Sifatga baho bering (1-5):", reply_markup=ik(
        [("⭐ 1", "rvstar_1"), ("⭐ 2", "rvstar_2"), ("⭐ 3", "rvstar_3"), ("⭐ 4", "rvstar_4"), ("⭐ 5", "rvstar_5")]))
    await call.answer()


@router.callback_query(F.data.startswith("rvstar_"))
async def urev_star(call: CallbackQuery, state: FSMContext):
    await state.update_data(rev_star=int(call.data[7:]))
    await call.message.edit_text("Fikringizni yozib yuboring (yoki ⏭ O'tkazish):",
                                 reply_markup=ik([("⏭ O'tkazish", "rv_skip")]))
    await state.set_state(ReviewSt.comment);
    await call.answer()


@router.message(ReviewSt.comment)
async def urev_comment(msg: Message, state: FSMContext):
    d = await state.get_data()
    oid = d['rev_oid']; rating = d['rev_star']; comment = msg.text

    await exe("INSERT INTO reviews(user_id, order_id, product_id, rating, comment) VALUES(?,?,0,?,?)", (msg.from_user.id, oid, rating, comment))
    await state.clear();
    await msg.answer("Rahmat, sharhingiz qabul qilindi! 🙏", reply_markup=await main_kb(msg.from_user.id))

    # 📢 ADMINGA SHARHNI YUBORISH
    u = await q1("SELECT name, phone FROM users WHERE tg_id=?", (msg.from_user.id,))
    adm_msg = f"📝 <b>YANGI SHARH (Zakaz #{oid})</b>\n👤 Mijoz: {u['name']} ({u['phone']})\n⭐ Baho: {rating}/5\n💬 Izoh: <i>{comment}</i>"
    adms = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in adms:
        try: await bot.send_message(a['tg_id'], adm_msg)
        except: pass

@router.callback_query(F.data == "rv_skip")
async def urev_skip(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    oid = d['rev_oid']; rating = d['rev_star']

    await exe("INSERT INTO reviews(user_id, order_id, product_id, rating) VALUES(?,?,0,?)", (call.from_user.id, oid, rating))
    await state.clear();
    await call.message.edit_text("Rahmat! 🙏")
    await call.answer()

    # 📢 ADMINGA SHARHNI YUBORISH (Izohsiz)
    u = await q1("SELECT name, phone FROM users WHERE tg_id=?", (call.from_user.id,))
    adm_msg = f"📝 <b>YANGI SHARH (Zakaz #{oid})</b>\n👤 Mijoz: {u['name']} ({u['phone']})\n⭐ Baho: {rating}/5\n💬 Izoh: <i>(Yozilmadi)</i>"
    adms = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in adms:
        try: await bot.send_message(a['tg_id'], adm_msg)
        except: pass


# ──────────────────────────────────────────
# 5. ADMIN TASDIQLASHI VA SHABLONLAR
# ──────────────────────────────────────────
@router.callback_query(F.data.startswith("asetfee_"))
async def admin_set_fee(call: CallbackQuery, state: FSMContext):
    oid = int(call.data[8:])
    km = (await q1("SELECT distance FROM orders WHERE id=?", (oid,)))['distance']
    f_per = float((await q1("SELECT value FROM settings WHERE key='fee_per_km'"))['value'])
    avt = int(max(1, math.ceil(km)) * f_per) if km > 0 else 15000

    await state.update_data(fee_oid=oid)
    await call.message.answer("🚚 <b>Yo'lkira qancha? Nima qilamiz?</b>", reply_markup=ik(
        [(f"🚀 Kuryerlarga tashlash ({fmt(avt)} so'm)", f"doconf_{oid}_{avt}")],
        [(f"🙋‍♂️ O'zim olib boraman ({fmt(avt)} so'm)", f"admself_{oid}_{avt}")],
        [("✏️ Boshqa narx yozish", "manual_fee")]
    ))
    await call.answer()


@router.callback_query(F.data == "manual_fee")
async def admin_manual_fee(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💰 Yo'lkira narxini raqamda yozing:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.set_fee);
    await call.answer()


@router.message(AdminSt.set_fee)
async def admin_manual_fee_input(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    d = await state.get_data();
    oid = d['fee_oid'];
    fee = int(msg.text)
    await msg.answer("Bu narx bilan nima qilamiz?", reply_markup=ik(
        [("🚀 Kuryerlarga tashlash", f"doconf_{oid}_{fee}")],
        [("🙋‍♂️ O'zim olib boraman", f"admself_{oid}_{fee}")]
    ))
    await state.clear()


@router.callback_query(F.data.startswith("doconf_"))
async def admin_auto_conf(call: CallbackQuery):
    parts = call.data.split("_");
    oid = int(parts[1]);
    fee = int(parts[2])
    await exe("UPDATE orders SET delivery_fee=?, status='pending_courier' WHERE id=?", (fee, oid))
    o = await q1("SELECT * FROM orders WHERE id=?", (oid,))

    # MIJOZGA XABAR (Foydalanuvchiga tasdiq)
    try:
        await bot.send_message(o['user_id'],
                               f"✅ Buyurtmangiz tasdiqlandi! Yo'lkira: <b>{fmt(fee)} so'm</b>.\nKuryer qidirilmoqda 🔎")
    except:
        pass

    # KURYERLARGA TARQATISH
    cs = await qall("SELECT tg_id FROM admins WHERE role='courier' AND is_active=1")
    txt = f"🔥 <b>YANGI BUYURTMA #{oid}</b>\n📍 Mo'ljal: {o['landmark']}\n📏 Masofa: {o['distance']:.1f} km\n💰 Yo'lkira: <b>{fmt(fee)} so'm</b>\nKim birinchi olsa o'shanga yoziladi!"
    for c in cs:
        try:
            await bot.send_location(c['tg_id'], o['lat'], o['lon'])
            await bot.send_message(c['tg_id'], txt, reply_markup=ik([("🙋 Men olaman", f"cgrab_{oid}")]))
        except:
            pass
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("✅ Buyurtma kuryerlarga yuborildi.")
    await call.answer()


@router.callback_query(F.data.startswith("admself_"))
async def admin_self_deliver(call: CallbackQuery):
    parts = call.data.split("_");
    oid = int(parts[1]);
    fee = int(parts[2]);
    uid = call.from_user.id
    await exe("UPDATE orders SET delivery_fee=?, status='on_way', courier_id=? WHERE id=?", (fee, uid, oid))
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))

    # MIJOZGA XABAR
    try:
        await bot.send_message(o['user_id'],
                               f"✅ Buyurtmangiz tasdiqlandi! Yo'lkira: <b>{fmt(fee)} so'm</b>.\nDo'kon xodimining o'zi siz tomonga yo'lga chiqdi 🚚")
    except:
        pass

    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(
        f"✅ <b>Buyurtma #{oid} sizning o'zingizga yozildi!</b>\nManzilga yetib borgach pastdagi tugmani bosing:",
        reply_markup=ik([("✅ Mijozga topshirdim", f"cdeliv_{oid}")]))
    await call.answer()


@router.callback_query(F.data.startswith("acancel_"))
async def admin_cancel_order(call: CallbackQuery):
    oid = int(call.data[8:])
    await exe("UPDATE orders SET status='cancelled', cancel_reason='Admin bekor qildi' WHERE id=?", (oid,))
    await return_stock(oid)
    await call.message.edit_text(f"❌ #{oid} Bekor qilindi.")
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))
    try:
        await bot.send_message(o['user_id'], f"❌ Buyurtmangiz (#{oid}) admin tomonidan bekor qilindi.")
    except:
        pass
    await call.answer()


# ──────────────────────────────────────────
# 6. KURYER POYGASI VA PANEL
# ──────────────────────────────────────────
@router.message(F.text == "🚚 Kuryer Panel")
async def cmd_courier(msg: Message):
    adm = await q1("SELECT role FROM admins WHERE tg_id=? AND is_active=1", (msg.from_user.id,))
    if not adm or adm['role'] not in ["admin", "courier"]: return
    await msg.answer("🚚 <b>Kuryer Paneliga xush kelibsiz!</b>", reply_markup=courier_kb())


@router.message(F.text == "📋 Kuryer: Mening buyurtmalarim")
async def courier_my_orders(msg: Message):
    ords = await qall("SELECT * FROM orders WHERE courier_id=? AND status IN ('assigned', 'on_way')",
                      (msg.from_user.id,))
    if not ords: return await msg.answer("Hozirda sizda faol buyurtmalar yo'q.")
    for o in ords:
        txt = f"📦 #{o['id']} | Mo'ljal: {o['landmark']}\n💰 Yo'lkira: {fmt(o['delivery_fee'])} so'm"
        btns = []
        if o['status'] == 'assigned':
            btns.append([("🛍 Do'kondan oldim", f"cpickup_{o['id']}")])
        elif o['status'] == 'on_way':
            btns.append([("✅ Mijozga topshirdim", f"cdeliv_{o['id']}")])
        await msg.answer(txt, reply_markup=ik(*btns))


@router.callback_query(F.data.startswith("cgrab_"))
async def courier_grab(call: CallbackQuery):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='courier'", (call.from_user.id,)): return
    oid = int(call.data[6:])
    o = await q1("SELECT status FROM orders WHERE id=?", (oid,))
    if o['status'] != 'pending_courier': return await call.answer("❌ Kechikdingiz, boshqa kuryer olib bo'ldi!",
                                                                  show_alert=True)

    await exe("UPDATE orders SET status='assigned', courier_id=? WHERE id=?", (call.from_user.id, oid))
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(f"✅ <b>Buyurtma #{oid} sizga yozildi!</b>\nEndi do'konga kelib olib keting.",
                              reply_markup=ik([("🛍 Do'kondan oldim", f"cpickup_{oid}")]))
    await call.answer()


@router.callback_query(F.data.startswith("cpickup_"))
async def courier_pickup(call: CallbackQuery):
    oid = int(call.data[8:])
    await exe("UPDATE orders SET status='on_way' WHERE id=?", (oid,))
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))
    c_name = (await q1("SELECT name FROM admins WHERE tg_id=?", (call.from_user.id,)))['name']
    try:
        await bot.send_message(o['user_id'], f"🚚 <b>Kuryer yo'lga chiqdi!</b>\nSizga {c_name} xizmat ko'rsatmoqda.")
    except:
        pass
    await call.message.edit_text(f"🚚 <b>#{oid} yo'lda!</b> Manzilga yetgach bosing:",
                                 reply_markup=ik([("✅ Mijozga topshirdim", f"cdeliv_{oid}")]))
    await call.answer()


@router.callback_query(F.data.startswith("cdeliv_"))
async def courier_deliver(call: CallbackQuery):
    oid = int(call.data[7:])  # <-- Kechagi xatoni ham 7 qilib qo'ydim
    await exe("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))

    # MIJOZGA JONLI XABAR VA TUGMALAR
    user_msg = (
        f"🎉 <b>Hurmatli mijoz!</b>\n"
        f"Kuryerimiz #{oid}-buyurtmani sizga yetkazganini xabar qildi.\n\n"
        f"Buyurtmani qo'lingizga oldingizmi?"
    )
    user_kb = ik(
        [("✅ Ha, oldim (Baho berish)", f"ureview_{oid}")],
        [("❌ Yo'q, menga kelmadi", f"not_recv_{oid}")]
    )
    try:
        await bot.send_message(o['user_id'], user_msg, reply_markup=user_kb)
    except:
        pass

    await call.message.edit_text(f"✅ #{oid} yetkazildi deb belgilandi.\nMijozga tasdiqlash so'rovi ketdi!")
    await call.answer()


# MIJOZ "OLMADIM" DESA ADMINGA TREVOGA URISH FUNKSIYASI:
@router.callback_query(F.data.startswith("not_recv_"))
async def not_received(call: CallbackQuery):
    oid = int(call.data[9:])
    await call.message.edit_text(
        "Ushbu noqulaylik uchun uzr so'raymiz! 🚨 Adminlarga xabar yuborildi, holatni darhol nazoratga olamiz.")

    # ADMINGA OGOHLANTIRISH
    adms = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in adms:
        try:
            await bot.send_message(a['tg_id'],
                                   f"🚨 <b>DIQQAT! JIDDIY MUAMMO:</b>\n\n#{oid} buyurtmani kuryer 'topshirdim' dedi, lekin mijoz 'olmadim' tugmasini bosdi!\nZudlik bilan kuryer va mijoz bilan bog'laning!")
        except:
            pass
    await call.answer()


# ──────────────────────────────────────────
# 7. ASOSIY ADMIN PANEL (CRUD, BANS, PAYMENTS, STAFF, SETTINGS)
# ──────────────────────────────────────────
@router.message(F.text == "⚙️ Admin Panel")
async def cmd_admin(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    await msg.answer("⚙️ <b>Admin Panel</b>", reply_markup=admin_kb())


# --- SETTINGS (LOKATSIYA VA OCHIQ/YOPIQ) ---
@router.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    shop_st = await q1("SELECT value FROM settings WHERE key='is_open'")
    st_text = "🟢 Ochiq" if shop_st['value'] == "1" else "🔴 Yopiq"
    await msg.answer(
        f"⚙️ <b>Do'kon sozlamalari:</b>\n\nHolat: {st_text}",
        reply_markup=ik(
            [("📍 Do'kon lokatsiyasini yangilash", "set_shop_loc")],
            [("🟢/🔴 Ochiq-Yopiq qilish", "toggle_shop")]
        )
    )


@router.callback_query(F.data == "toggle_shop")
async def toggle_shop(call: CallbackQuery):
    st = await q1("SELECT value FROM settings WHERE key='is_open'")
    new_val = "0" if st['value'] == "1" else "1"
    await exe("UPDATE settings SET value=? WHERE key='is_open'", (new_val,))
    txt = "🟢 Do'kon ochildi!" if new_val == "1" else "🔴 Do'kon yopildi!"
    await call.answer(txt, show_alert=True)
    await call.message.delete();
    await admin_settings(call.message)


@router.callback_query(F.data == "set_shop_loc")
async def set_shop_loc_start(call: CallbackQuery, state: FSMContext):
    btn = [KeyboardButton(text="📍 Xaritadan lokatsiya tashlash", request_location=True),
           KeyboardButton(text="❌ Bekor qilish")]
    await call.message.answer("Pastdagi tugma orqali do'konning yangi lokatsiyasini tashlang:", reply_markup=rk(btn))
    await state.set_state(AdminSt.set_loc);
    await call.answer()


@router.message(AdminSt.set_loc)
async def set_shop_loc_save(msg: Message, state: FSMContext):
    if not msg.location: return await msg.answer("Iltimos, lokatsiya tashlang!")
    await exe("UPDATE settings SET value=? WHERE key='shop_lat'", (str(msg.location.latitude),))
    await exe("UPDATE settings SET value=? WHERE key='shop_lon'", (str(msg.location.longitude),))
    await state.clear();
    await msg.answer("✅ Do'kon lokatsiyasi muvaffaqiyatli yangilandi!", reply_markup=admin_kb())


# --- QOLGAN ADMIN FUNKSIYALARI ---
@router.message(F.text == "👥 Xodimlar")
async def admin_staff(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    stf = await qall("SELECT * FROM admins")
    txt = "👥 <b>Xodimlar:</b>\n\n"
    for s in stf: txt += f"{'👑 Admin' if s['role'] == 'admin' else '🚚 Kuryer'} | <code>{s['tg_id']}</code> | {s['name']}\n"
    await msg.answer(txt, reply_markup=ik([("➕ Kuryer qo'shish", "add_cour")], [("➕ Admin qo'shish", "add_adm")]))


@router.callback_query(F.data.in_(["add_cour", "add_adm"]))
async def add_staff(call: CallbackQuery, state: FSMContext):
    role = "courier" if call.data == "add_cour" else "admin"
    await state.update_data(staff_role=role)
    await call.message.answer(f"🆔 Yangi xodimning Telegram ID sini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.admin_add);
    await call.answer()


@router.message(AdminSt.admin_add)
async def save_staff(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    d = await state.get_data();
    role = d['staff_role']
    name = "Kuryer" if role == "courier" else "Admin"
    await exe("INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,?,?)", (int(msg.text), name, role))
    await state.clear();
    await msg.answer("✅ Xodim qo'shildi!", reply_markup=admin_kb())


@router.message(F.text == "🚫 Ban/Unban")
async def admin_ban_menu(msg: Message, state: FSMContext):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    await msg.answer("🚫 Bloklash yoki ochish uchun Mijozning Telegram ID sini yozing:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.ban_user)


@router.message(AdminSt.ban_user)
async def save_ban(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    tg_id = int(msg.text);
    u = await q1("SELECT is_blocked FROM users WHERE tg_id=?", (tg_id,))
    if not u: return await msg.answer("Mijoz topilmadi.")
    new_st = 0 if u['is_blocked'] else 1
    await exe("UPDATE users SET is_blocked=? WHERE tg_id=?", (new_st, tg_id))
    await state.clear()
    await msg.answer(f"✅ Mijoz {'Blokdan chiqarildi' if new_st == 0 else 'Bloklandi'}!", reply_markup=admin_kb())


@router.message(F.text == "💳 To'lov usullari")
async def admin_payments(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    pms = await qall("SELECT * FROM payment_methods")
    rows = []
    for p in pms:
        st = "✅" if p['is_active'] else "❌"
        rows.append([InlineKeyboardButton(text=f"{st} {p['name']} ({p['type']})", callback_data=f"epay_{p['id']}")])
    rows.append([InlineKeyboardButton(text="➕ Yangi usul qo'shish", callback_data="add_pay")])
    await msg.answer("💳 <b>To'lov usullari:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("epay_"))
async def edit_pay(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT is_active FROM payment_methods WHERE id=?", (pid,))
    await exe("UPDATE payment_methods SET is_active=? WHERE id=?", (0 if p['is_active'] else 1, pid))
    try:
        await call.message.delete()
    except:
        pass
    await admin_payments(call.message);
    await call.answer("Holat o'zgardi")


@router.callback_query(F.data == "add_pay")
async def add_pay_type(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Turini tanlang:", reply_markup=ik([("💳 Karta", "ptype_card")],
                                                                 [("📱 Click", "ptype_click"),
                                                                  ("📱 Payme", "ptype_payme")]))
    await call.answer()


@router.callback_query(F.data.startswith("ptype_"))
async def add_pay_name(call: CallbackQuery, state: FSMContext):
    await state.update_data(ptype=call.data[6:])
    await call.message.answer("✏️ Nomi qanday ko'rinsin? (Masalan: Humo - Toshmat):", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.pay_name);
    await call.answer()


@router.message(AdminSt.pay_name)
async def add_pay_details(msg: Message, state: FSMContext):
    await state.update_data(pname=msg.text.strip());
    d = await state.get_data()
    hint = "Karta raqami va FIO ni yozing:" if d['ptype'] == 'card' else "Merchant Tokenni (API kalitni) yozing:"
    await msg.answer(hint, reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.pay_details)


@router.message(AdminSt.pay_details)
async def save_pay(msg: Message, state: FSMContext):
    d = await state.get_data()
    await exe("INSERT INTO payment_methods(type, name, details) VALUES(?,?,?)",
              (d['ptype'], d['pname'], msg.text.strip()))
    await state.clear();
    await msg.answer("✅ Saqlandi!", reply_markup=admin_kb())


# ─── BO'LIMLARNI BOSHQARISH ───────────────────────────────────────────────────
@router.message(F.text == "📂 Bo'limlar")
async def adm_cats(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    cats = await qall("SELECT * FROM categories")
    btns = [[(f"📦 {c['name']}", f"acat_{c['id']}")] for c in cats]
    btns.append([("➕ Yangi bo'lim", "add_cat")])
    await msg.answer("Bo'limlar (Tahrirlash uchun ustiga bosing):", reply_markup=ik(*btns))


@router.callback_query(F.data == "add_cat")
async def add_cat(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yozing:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.cat_name)
    await call.answer()


@router.message(AdminSt.cat_name)
async def save_cat(msg: Message, state: FSMContext):
    await exe("INSERT INTO categories(name) VALUES(?)", (msg.text.strip(),));
    await state.clear();
    await msg.answer("✅ Qo'shildi", reply_markup=admin_kb())


@router.callback_query(F.data.startswith("acat_"))
async def admin_cat_detail(call: CallbackQuery):
    cid = int(call.data[5:]);
    c = await q1("SELECT * FROM categories WHERE id=?", (cid,))
    if not c: return await call.answer("Topilmadi", show_alert=True)
    await call.message.edit_text(f"📦 <b>{c['name']}</b>\nNima qilamiz?",
                                 reply_markup=ik([("✏️ Nomni o'zgartirish", f"acatedit_{cid}")],
                                                 [("🗑 O'chirish", f"acatdel_{cid}")]))
    await call.answer()


@router.callback_query(F.data.startswith("acatdel_"))
async def admin_cat_delete(call: CallbackQuery):
    cid = int(call.data[8:])
    await exe("DELETE FROM categories WHERE id=?", (cid,));
    await call.message.edit_text("✅ Bo'lim o'chirildi.");
    await call.answer()


@router.callback_query(F.data.startswith("acatedit_"))
async def admin_cat_edit(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[9:])
    await state.update_data(edit_cat_id=cid)
    await call.message.answer("✏️ Bo'limning yangi nomini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.cat_edit_name);
    await call.answer()


@router.message(AdminSt.cat_edit_name)
async def admin_cat_edit_name_save(msg: Message, state: FSMContext):
    d = await state.get_data()
    await exe("UPDATE categories SET name=? WHERE id=?", (msg.text.strip(), d["edit_cat_id"]))
    await state.clear();
    await msg.answer(f"✅ O'zgartirildi!", reply_markup=admin_kb())


# ─── MAHSULOTLARNI BOSHQARISH ───────────────────────────────────────────────────
@router.message(F.text == "📦 Mahsulotlar")
async def adm_prods(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    prods = await qall(
        "SELECT p.*, c.name as cname FROM products p LEFT JOIN categories c ON p.category_id=c.id LIMIT 40")
    btns = []
    for p in prods:
        st = "✅" if p['is_active'] else "❌"
        btns.append([(f"{st} {p['name']} ({p['cname']})", f"admp_{p['id']}")])
    btns.append([("➕ Yangi mahsulot qo'shish", "add_prod")])
    await msg.answer("📦 <b>Mahsulotlar:</b>", reply_markup=ik(*btns))


@router.callback_query(F.data == "add_prod")
async def add_prod_cb(call: CallbackQuery, state: FSMContext):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    if not cats: return await call.answer("Bo'lim yo'q!", show_alert=True)
    await call.message.answer("Qaysi bo'limga qo'shamiz?",
                              reply_markup=ik(*[[(c["name"], f"selc_{c['id']}")] for c in cats]));
    await state.set_state(AdminSt.prod_cat)
    await call.answer()


@router.callback_query(StateFilter(AdminSt.prod_cat), F.data.startswith("selc_"))
async def p_cat(call: CallbackQuery, state: FSMContext):
    await state.update_data(cid=int(call.data[5:]));
    await call.message.answer("📝 Nomi:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.prod_name);
    await call.answer()


@router.message(AdminSt.prod_name)
async def p_name(msg: Message, state: FSMContext):
    await state.update_data(pname=msg.text.strip());
    await msg.answer("📄 Tavsifi (yoki 'yoq'):");
    await state.set_state(AdminSt.prod_desc)


@router.message(AdminSt.prod_desc)
async def p_desc(msg: Message, state: FSMContext):
    await state.update_data(pdesc="" if msg.text.lower() == 'yoq' else msg.text.strip());
    await msg.answer("💰 Narxi (raqam):");
    await state.set_state(AdminSt.prod_price)


@router.message(AdminSt.prod_price)
async def p_price(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    await state.update_data(pprice=int(msg.text.strip()));
    await msg.answer("📦 Ombor miqdori (raqam):");
    await state.set_state(AdminSt.prod_stock)


@router.message(AdminSt.prod_stock)
async def p_stock(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    await state.update_data(pstock=int(msg.text.strip()));
    await msg.answer("🖼 Rasm yuboring (yoki 'yoq'):");
    await state.set_state(AdminSt.prod_photo)


@router.message(AdminSt.prod_photo)
async def p_photo(msg: Message, state: FSMContext):
    d = await state.get_data();
    file_id = msg.photo[-1].file_id if msg.photo else ""
    await exe("INSERT INTO products(category_id,name,description,price,stock,photo_id) VALUES(?,?,?,?,?,?)",
              (d["cid"], d["pname"], d["pdesc"], d["pprice"], d["pstock"], file_id))
    await state.clear();
    await msg.answer("✅ Mahsulot qo'shildi!", reply_markup=admin_kb())


@router.callback_query(F.data.startswith("admp_"))
async def adm_p_det(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT * FROM products WHERE id=?", (pid,))
    if not p: return await call.answer("Topilmadi", show_alert=True)
    st = "✅ Faol" if p['is_active'] else "❌ O'chirilgan"
    txt = f"📦 {p['name']}\nNarx: {p['price']}\nOmbor: {p['stock']}\nHolat: {st}"
    await call.message.edit_text(txt, reply_markup=ik(
        [("🟢/🔴 Yoqish/O'chirish", f"ptog_{pid}"), ("🗑 O'chirish", f"pdel_{pid}")]))
    await call.answer()


@router.callback_query(F.data.startswith("ptog_"))
async def ptog(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT is_active FROM products WHERE id=?", (pid,))
    await exe("UPDATE products SET is_active=? WHERE id=?", (0 if p['is_active'] else 1, pid));
    await call.message.delete();
    await call.answer("O'zgardi")


@router.callback_query(F.data.startswith("pdel_"))
async def pdel(call: CallbackQuery):
    await exe("DELETE FROM products WHERE id=?", (int(call.data[5:]),));
    await call.message.edit_text("✅ O'chirildi.");
    await call.answer()


# --- STATISTIKA VA BROADCAST ---
@router.message(F.text == "📊 Statistika")
async def adm_stats(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    u_c = (await q1("SELECT COUNT(*) as n FROM users"))['n']
    o_c = (await q1("SELECT COUNT(*) as n FROM orders WHERE status='delivered'"))['n']
    o_sum = (await q1("SELECT SUM(total_amount) as s FROM orders WHERE status='delivered'"))['s'] or 0
    await msg.answer(
        f"📊 <b>Statistika</b>\n\n👥 Mijozlar: {u_c}\n📦 Yetkazilgan: {o_c}\n💰 Umumiy savdo: {fmt(o_sum)} so'm")


@router.message(F.text == "📨 Broadcast")
async def adm_bcast(msg: Message, state: FSMContext):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    await msg.answer("📢 Tarqatiladigan xabarni yozing:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.bcast_msg)


@router.message(AdminSt.bcast_msg)
async def send_bcast(msg: Message, state: FSMContext):
    users = await qall("SELECT tg_id FROM users WHERE is_blocked=0")
    ok = 0
    await msg.answer("⏳ Yuborilmoqda...")
    for u in users:
        try:
            await bot.send_message(u['tg_id'], f"📢 {msg.text}"); ok += 1
        except:
            pass
        await asyncio.sleep(0.05)
    await state.clear();
    await msg.answer(f"✅ {ok} kishiga yuborildi.", reply_markup=admin_kb())


# ──────────────────────────────────────────
# USHLAB QOLUVCHI (CATCH-ALL)
# ──────────────────────────────────────────
@router.callback_query(F.data == "noop")
async def noop_cb(call: CallbackQuery): await call.answer()


async def check_admin(id):
    pass


@router.message()
async def catch_all(msg: Message, state: FSMContext):
    st = await state.get_state()
    if st is None:
        kb = admin_kb() if await check_admin(msg.from_user.id) else await main_kb(msg.from_user.id)
        await msg.answer("❓ Tushunmadim. Menyudan foydalaning:", reply_markup=kb)


async def main():
    await init_db()
    dp.include_router(router)
    await bot.set_my_commands([BotCommand(command="start", description="Boshlash")])
    print("🚀 Enterprise Pro Bot ishga tushdi...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())