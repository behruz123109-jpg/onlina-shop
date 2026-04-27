import asyncio
import logging
import math
from datetime import datetime
from os import getenv

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
# SOZLAMALAR
# ──────────────────────────────────────────
BOT_TOKEN = getenv("bot_token")
ADMIN_IDS = [8488028783]
DB_PATH = "shop.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ──────────────────────────────────────────
# STATUSLAR (Tarjimalar)
# ──────────────────────────────────────────
STATUSES = {
    "new": "⏳ Tasdiqlanmoqda",
    "pending_courier": "✅ Kuryer kutilmoqda",
    "on_way": "🚚 Yo'lda",
    "delivered": "🎉 Yetkazildi",
    "cancelled": "❌ Bekor qilingan"
}


# ──────────────────────────────────────────
# FSM HOLATLARI
# ──────────────────────────────────────────
class Reg(StatesGroup): name = State(); phone = State()


class Shop(StatesGroup): search = State()


class Checkout(StatesGroup): loc = State(); apt = State(); payment = State(); receipt = State()


class ProfileSt(StatesGroup): new_name = State()


class AdminSt(StatesGroup):
    cat_name = State();
    edit_cat_name = State()
    prod_cat = State();
    prod_name = State();
    prod_desc = State()
    prod_price = State();
    prod_stock = State();
    prod_photo = State()
    edit_prod_val = State();
    admin_add = State()
    courier_add = State();
    set_coord = State();
    cancel_reason = State()
    set_card_num = State();
    set_card_name = State();
    set_fee = State()


class ReviewSt(StatesGroup): comment = State()


# ──────────────────────────────────────────
# BAZA VA YORDAMCHILAR
# ──────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, tg_id INTEGER UNIQUE, name TEXT, phone TEXT);
        CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, tg_id INTEGER UNIQUE, name TEXT, role TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, description TEXT, price INTEGER, stock INTEGER DEFAULT 0, photo_id TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS cart (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER DEFAULT 1, UNIQUE(user_id, product_id));
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER, courier_id INTEGER DEFAULT 0, status TEXT DEFAULT 'new',
            total_amount INTEGER DEFAULT 0, delivery_fee INTEGER DEFAULT 0, payment_method TEXT, phone TEXT,
            lat REAL, lon REAL, address TEXT, apt TEXT, receipt_id TEXT DEFAULT '', cancel_reason TEXT DEFAULT '',
            distance REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, quantity INTEGER, price INTEGER);
        CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, user_id INTEGER, order_id INTEGER, rating INTEGER, comment TEXT);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        for a in ADMIN_IDS:
            await db.execute("INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,'Super Admin','admin')", (a,))
        defaults = [("shop_lat", "39.6542"), ("shop_lon", "66.9597"), ("fee_per_km", "5000"),
                    ("admin_card", "Kiritilmagan"), ("admin_card_name", "Kiritilmagan")]
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
    R = 6371.0;
    dlat = math.radians(lat2 - lat1);
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(
        dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def return_stock(oid: int):
    items = await qall("SELECT * FROM order_items WHERE order_id=?", (oid,))
    for i in items:
        await exe("UPDATE products SET stock=stock+? WHERE id=?", (i["quantity"], i["product_id"]))


# ──────────────────────────────────────────
# BOT VA KLAVIATURALAR
# ──────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
dp = Dispatcher(storage=MemoryStorage())


def ik(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows])


def rk(*rows) -> ReplyKeyboardMarkup:
    keyboard = []
    for row in rows:
        button_row = []
        for item in row:
            if isinstance(item, KeyboardButton):
                button_row.append(item)
            else:
                button_row.append(KeyboardButton(text=str(item)))
        keyboard.append(button_row)
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


CANCEL_KB = rk(["❌ Bekor qilish"])


async def main_kb(tg_id: int):
    adm = await q1("SELECT role FROM admins WHERE tg_id=? AND is_active=1", (tg_id,))
    rows = [["🛍 Katalog", "🔍 Qidiruv"], ["🛒 Savatcha", "📦 Buyurtmalarim"], ["👤 Profilim"]]
    if adm and adm["role"] == "admin":
        rows.append(["⚙️ Admin Panel"])
    elif adm and adm["role"] == "courier":
        rows.append(["🚚 Kuryer Panel"])
    return rk(*rows)


async def safe_delete(message: Message):
    try:
        await message.delete()
    except:
        pass


async def safe_edit(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await safe_delete(message)
        await message.answer(text, reply_markup=reply_markup)


async def build_cart_msg(user_id: int):
    items = await qall(
        "SELECT c.id, c.product_id, c.quantity, p.name, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
        (user_id,))
    if not items: return "🛒 Savatingiz bo'sh.", None
    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    rows = []
    for i in items:
        line = i["price"] * i["quantity"];
        tot += line
        txt += f"• {i['name']} ({i['quantity']} ta) = {fmt(line)} so'm\n"
        rows.append(
            [("➖", f"cxdec_{i['product_id']}"), (f"{i['name'][:12]}", "noop"), ("➕", f"cxinc_{i['product_id']}")])
    txt += f"\n💰 Jami: <b>{fmt(tot)} so'm</b>"
    rows.append([("✅ Buyurtma berish", "checkout"), ("🗑 Tozalash", "cart_clear")])
    return txt, ik(*rows)


async def refresh_cart(call: CallbackQuery):
    txt, kb = await build_cart_msg(call.from_user.id)
    if kb is None:
        await safe_edit(call.message, txt)
    else:
        try:
            await call.message.edit_text(txt, reply_markup=kb)
        except Exception:
            pass


# ──────────────────────────────────────────
# GLOBAL BEKOR QILISH
# ──────────────────────────────────────────
@router.message(F.text == "❌ Bekor qilish")
async def global_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🚫 Amal bekor qilindi.", reply_markup=await main_kb(msg.from_user.id))


# ──────────────────────────────────────────
# 1. START VA PROFIL
# ──────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = await q1("SELECT * FROM users WHERE tg_id=?", (msg.from_user.id,))
    if not user:
        await msg.answer("👋 Assalomu alaykum! Ismingizni yozing:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Reg.name)
    else:
        await msg.answer(f"👋 Salom, {user['name']}!", reply_markup=await main_kb(msg.from_user.id))


@router.message(Reg.name)
async def reg_name(msg: Message, state: FSMContext):
    if not msg.text or len(msg.text) < 2 or msg.text.isdigit(): return await msg.answer("❌ Ismingizni to'g'ri yozing:")
    await state.update_data(name=msg.text.strip().title())
    await msg.answer("Raqamingizni yuboring:",
                     reply_markup=rk([KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]))
    await state.set_state(Reg.phone)


@router.message(Reg.phone)
async def reg_phone(msg: Message, state: FSMContext):
    ph = msg.contact.phone_number if msg.contact else msg.text
    if not str(ph).startswith("+"): ph = "+" + str(ph)
    d = await state.get_data()
    await exe("INSERT INTO users(tg_id,name,phone) VALUES(?,?,?)", (msg.from_user.id, d["name"], ph))
    await state.clear()
    await msg.answer("🎉 Ro'yxatdan o'tdingiz!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "👤 Profilim")
async def cmd_profile(msg: Message, state: FSMContext):
    user = await q1("SELECT * FROM users WHERE tg_id=?", (msg.from_user.id,))
    if user: await msg.answer(f"👤 {user['name']}\n📱 {user['phone']}",
                              reply_markup=ik([("✏️ Ismni o'zgartirish", "edit_name")]))


@router.callback_query(F.data == "edit_name")
async def edit_name(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi ismingizni yozing:", reply_markup=CANCEL_KB);
    await state.set_state(ProfileSt.new_name);
    await call.answer()


@router.message(ProfileSt.new_name)
async def save_new_name(msg: Message, state: FSMContext):
    await exe("UPDATE users SET name=? WHERE tg_id=?", (msg.text.strip(), msg.from_user.id))
    await state.clear();
    await msg.answer("✅ Yangilandi!", reply_markup=await main_kb(msg.from_user.id))


# ──────────────────────────────────────────
# 2. KATALOG, QIDIRUV, SAVAT
# ──────────────────────────────────────────
@router.message(F.text == "🛍 Katalog")
async def cmd_catalog(msg: Message):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    if not cats: return await msg.answer("Bo'limlar yo'q.")
    await msg.answer("📂 <b>Bo'limni tanlang:</b>",
                     reply_markup=ik(*[[(f"📦 {c['name']}", f"cat_{c['id']}")] for c in cats]))


@router.callback_query(F.data.startswith("cat_"))
async def show_cat(call: CallbackQuery):
    prods = await qall("SELECT * FROM products WHERE category_id=? AND is_active=1", (int(call.data[4:]),))
    if not prods: return await call.answer("Bo'lim bo'sh.", show_alert=True)
    await safe_edit(call.message, "🛍 <b>Mahsulotlar:</b>",
                    reply_markup=ik(*[[(f"🛒 {p['name']} - {fmt(p['price'])}", f"prod_{p['id']}")] for p in prods],
                                    [("🔙 Orqaga", "back_cats")]))


@router.callback_query(F.data == "back_cats")
async def back_cats(call: CallbackQuery):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    await safe_edit(call.message, "📂 <b>Bo'limni tanlang:</b>",
                    reply_markup=ik(*[[(f"📦 {c['name']}", f"cat_{c['id']}")] for c in cats]))


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
    await safe_delete(call.message)
    if p["photo_id"]:
        await bot.send_photo(call.from_user.id, p["photo_id"], caption=txt, reply_markup=ik(*btns))
    else:
        await bot.send_message(call.from_user.id, txt, reply_markup=ik(*btns))


@router.callback_query(F.data.startswith("cinc_"))
async def cart_inc(call: CallbackQuery):
    pid = int(call.data[5:]);
    p = await q1("SELECT stock FROM products WHERE id=?", (pid,))
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if p and ci and ci["quantity"] + 1 > p["stock"]: return await call.answer("Omborda qolmadi!", show_alert=True)
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
    await state.clear();
    await msg.answer("🔍 Nomini yozing:", reply_markup=CANCEL_KB);
    await state.set_state(Shop.search)


@router.message(Shop.search)
async def do_search(msg: Message, state: FSMContext):
    q = f"%{msg.text.strip()}%";
    res = await qall("SELECT * FROM products WHERE is_active=1 AND name LIKE ? LIMIT 10", (q,))
    if not res: return await msg.answer("❌ Topilmadi.")
    await msg.answer(f"🔍 Topildi:",
                     reply_markup=ik(*[[(f"🛒 {p['name']} - {fmt(p['price'])}", f"prod_{p['id']}")] for p in res]));
    await state.clear()


@router.message(F.text == "🛒 Savatcha")
async def cmd_cart(msg: Message):
    txt, kb = await build_cart_msg(msg.from_user.id);
    await msg.answer(txt, reply_markup=kb)


@router.callback_query(F.data.startswith("cxinc_"))
async def cxinc(call: CallbackQuery):
    pid = int(call.data[6:]);
    p = await q1("SELECT stock FROM products WHERE id=?", (pid,))
    ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, pid))
    if p and ci and ci["quantity"] + 1 > p["stock"]: return await call.answer("Omborda qolmadi!", show_alert=True)
    await exe(
        "INSERT INTO cart(user_id,product_id,quantity) VALUES(?,?,1) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=quantity+1",
        (call.from_user.id, pid))
    await refresh_cart(call);
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
    await refresh_cart(call);
    await call.answer()


@router.callback_query(F.data == "cart_clear")
async def cart_clear(call: CallbackQuery):
    await exe("DELETE FROM cart WHERE user_id=?", (call.from_user.id,));
    await safe_edit(call.message, "🛒 Savat tozalandi.")


# ──────────────────────────────────────────
# 3. ZAKAZ BERISH (LOKATSIYA -> CHEK)
# ──────────────────────────────────────────
@router.callback_query(F.data == "checkout")
async def start_checkout(call: CallbackQuery, state: FSMContext):
    items = await qall("SELECT id FROM cart WHERE user_id=?", (call.from_user.id,))
    if not items: return await call.answer("Savat bo'sh!", show_alert=True)
    btn = [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True), KeyboardButton(text="❌ Bekor qilish")]
    await safe_delete(call.message);
    await call.message.answer("📍 Kuryer adashmasligi uchun xaritadan lokatsiyangizni yuboring:", reply_markup=rk(btn));
    await state.set_state(Checkout.loc);
    await call.answer()


@router.message(Checkout.loc)
async def process_location(msg: Message, state: FSMContext):
    if msg.location:
        await state.update_data(lat=msg.location.latitude, lon=msg.location.longitude, address="Xaritadan yuborilgan")
    else:
        await state.update_data(lat=0.0, lon=0.0, address=msg.text)
    await msg.answer("🏠 Uy/kvartira raqamini aniq yozing:", reply_markup=CANCEL_KB);
    await state.set_state(Checkout.apt)


@router.message(Checkout.apt)
async def process_apt(msg: Message, state: FSMContext):
    await state.update_data(apt=msg.text.strip())
    await msg.answer("💳 To'lov usuli:",
                     reply_markup=ik([("💵 Naqd pul", "pay_cash")], [("💳 Plastik karta", "pay_card")]));
    await state.set_state(Checkout.payment)


@router.callback_query(StateFilter(Checkout.payment))
async def process_payment_method(call: CallbackQuery, state: FSMContext):
    d = await state.get_data();
    uid = call.from_user.id
    items = await qall("SELECT c.*, p.price, p.name FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
                       (uid,))
    if not items: await state.clear(); return await call.message.answer("Savat bo'sh!", reply_markup=await main_kb(uid))

    tot = sum(i["price"] * i["quantity"] for i in items)
    s_lat = float((await q1("SELECT value FROM settings WHERE key='shop_lat'"))["value"])
    s_lon = float((await q1("SELECT value FROM settings WHERE key='shop_lon'"))["value"])
    fee_per_km = int((await q1("SELECT value FROM settings WHERE key='fee_per_km'"))["value"])

    km = calc_km(s_lat, s_lon, d.get('lat', 0), d.get('lon', 0)) if d.get('lat') else 0.0
    s_fee = int(max(1, math.ceil(km)) * fee_per_km) if km > 0 else 15000

    await state.update_data(tot=tot, fee=s_fee, km=km, items=items)

    if call.data == "pay_card":
        c = await q1("SELECT value FROM settings WHERE key='admin_card'")
        n = await q1("SELECT value FROM settings WHERE key='admin_card_name'")
        await safe_delete(call.message)
        await call.message.answer(
            f"💳 <b>Karta orqali to'lov</b>\n\n"
            f"🛍 Mahsulotlar: {fmt(tot)} so'm\n"
            f"🚚 Yo'lkira (tahminan): {fmt(s_fee)} so'm\n"
            f"💰 <b>Jami: {fmt(tot + s_fee)} so'm</b>\n\n"
            f"💳 Karta raqami: <code>{c['value']}</code>\n"
            f"👤 Karta egasi: {n['value']}\n\n"
            f"📸 <i>To'lovni amalga oshirib, chek rasmini shu yerga yuboring:</i>",
            reply_markup=CANCEL_KB
        )
        await state.set_state(Checkout.receipt)
    else:
        await save_order_and_send_to_admin(call.message, state, uid, "cash", tot, s_fee, km, items, "")
    await call.answer()


@router.message(Checkout.receipt, F.photo)
async def process_receipt(msg: Message, state: FSMContext):
    d = await state.get_data()
    await save_order_and_send_to_admin(msg, state, msg.from_user.id, "card", d['tot'], d['fee'], d['km'], d['items'],
                                       msg.photo[-1].file_id)


async def save_order_and_send_to_admin(msg, state, uid, pay_method, tot, fee, km, items, receipt_id):
    d = await state.get_data();
    user = await q1("SELECT * FROM users WHERE tg_id=?", (uid,))

    await exe(
        "INSERT INTO orders(user_id,total_amount,delivery_fee,payment_method,phone,lat,lon,address,apt,receipt_id,distance) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (uid, tot, fee, pay_method, user["phone"], d.get('lat', 0), d.get('lon', 0), d.get('address', ''),
         d.get('apt', ''), receipt_id, km)
    )
    oid = (await q1("SELECT id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)))["id"]

    items_txt = ""
    for i in items:
        await exe("INSERT INTO order_items(order_id,product_id,product_name,quantity,price) VALUES(?,?,?,?,?)",
                  (oid, i['product_id'], i['name'], i['quantity'], i['price']))
        await exe("UPDATE products SET stock=MAX(0,stock-?) WHERE id=?", (i["quantity"], i["product_id"]))
        items_txt += f"▫️ {i['name']} x {i['quantity']} ta = {fmt(i['price'] * i['quantity'])}\n"

    await exe("DELETE FROM cart WHERE user_id=?", (uid,));
    await state.clear()
    await msg.answer(f"🎉 Buyurtma #{oid} yuborildi! Admin tasdiqlashini kuting.", reply_markup=await main_kb(uid))

    pm_txt = "💳 Karta (Chek yuborildi)" if pay_method == "card" else "💵 Naqd pul"
    adm_txt = (
        f"🆕 <b>Yangi buyurtma #{oid}</b>\n"
        f"👤 {user['name']} | 📱 {user['phone']}\n"
        f"🏠 {d.get('address', '')} {d.get('apt', '')}\n"
        f"📏 Masofa: {km:.1f} km\n"
        f"💳 To'lov: {pm_txt}\n\n"
        f"🛍 <b>Mahsulotlar:</b>\n{items_txt}\n"
        f"💸 Mahsulot summasi: {fmt(tot)} so'm"
    )

    btns = [
        [("🚀 Avtomat (" + fmt(fee) + " so'm)", f"autofee_{oid}_{fee}")],
        [("✏️ Boshqa narx yozish", f"setfee_{oid}")],
        [("❌ Bekor qilish", f"acancel_{oid}")]
    ]

    adms = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in adms:
        try:
            if d.get('lat'): await bot.send_location(a["tg_id"], d['lat'], d['lon'])
            if receipt_id:
                await bot.send_photo(a["tg_id"], receipt_id, caption=adm_txt, reply_markup=ik(*btns))
            else:
                await bot.send_message(a["tg_id"], adm_txt, reply_markup=ik(*btns))
        except:
            pass


# ──────────────────────────────────────────
# 4. BUYURTMALARIM
# ──────────────────────────────────────────
@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(msg: Message):
    ords = await qall("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (msg.from_user.id,))
    if not ords: return await msg.answer("📦 Sizda hali buyurtmalar yo'q.")
    for o in ords:
        st = STATUSES.get(o["status"], o["status"])
        txt = f"📦 #{o['id']}\nHolati: {st}\n💵 Jami: {fmt(o['total_amount'] + o['delivery_fee'])} so'm"
        btns = []
        if o["status"] == "new":
            btns.append([("❌ Bekor qilish", f"ucancel_{o['id']}")])
        elif o["status"] == "on_way":
            btns.append([("✅ Qo'limga oldim", f"ureceive_{o['id']}")])
        btns.append([("♻️ Qayta buyurtma", f"reorder_{o['id']}")])
        await msg.answer(txt, reply_markup=ik(*btns))


@router.callback_query(F.data.startswith("reorder_"))
async def cb_reorder(call: CallbackQuery):
    uid = call.from_user.id;
    items = await qall("SELECT * FROM order_items WHERE order_id=?", (int(call.data[8:]),))
    await exe("DELETE FROM cart WHERE user_id=?", (uid,))
    for i in items: await exe("INSERT INTO cart(user_id,product_id,quantity) VALUES(?,?,?)",
                              (uid, i["product_id"], i["quantity"]))
    await call.answer("✅ Savatga solindi!", show_alert=True);
    txt, kb = await build_cart_msg(uid);
    await call.message.answer(txt, reply_markup=kb)


@router.callback_query(F.data.startswith("ucancel_"))
async def ucancel(call: CallbackQuery, state: FSMContext):
    await state.update_data(c_oid=int(call.data[8:]));
    await call.message.answer("Sababi:", reply_markup=ik([("Fikrimdan qaytdim", "ur_1")], [("Xato buyurtma", "ur_2")]));
    await call.answer()


@router.callback_query(F.data.startswith("ur_"))
async def ureason(call: CallbackQuery, state: FSMContext):
    oid = (await state.get_data()).get("c_oid");
    r = "Fikrimdan qaytdim" if call.data == "ur_1" else "Xato buyurtma"
    await exe("UPDATE orders SET status='cancelled', cancel_reason=? WHERE id=?", (f"Mijoz: {r}", oid))
    await return_stock(oid)
    await state.clear();
    await call.message.edit_text("✅ Bekor qilindi.")
    for a in await qall("SELECT tg_id FROM admins WHERE role='admin'"):
        try:
            await bot.send_message(a["tg_id"], f"⚠️ Mijoz #{oid} ni bekor qildi.")
        except:
            pass


@router.callback_query(F.data.startswith("ureceive_"))
async def ureceive(call: CallbackQuery):
    oid = int(call.data[9:]);
    await exe("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
    await call.message.edit_text(f"🎉 #{oid} yetkazildi!\nBaho bering:",
                                 reply_markup=ik([("⭐⭐⭐⭐⭐ A'lo", f"star_{oid}_5")]))


@router.callback_query(F.data.startswith("star_"))
async def ustar(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_");
    await state.update_data(soid=parts[1], sval=parts[2])
    await call.message.edit_text("Fikringiz (yoki 'yoq'):");
    await state.set_state(ReviewSt.comment)


@router.message(ReviewSt.comment)
async def rev_comm(msg: Message, state: FSMContext):
    d = await state.get_data();
    c = "" if msg.text.lower() == "yoq" else msg.text
    await exe("INSERT INTO reviews(user_id,order_id,rating,comment) VALUES(?,?,?,?)",
              (msg.from_user.id, int(d["soid"]), int(d["sval"]), c))
    await state.clear();
    await msg.answer("✅ Rahmat!", reply_markup=await main_kb(msg.from_user.id))


# ──────────────────────────────────────────
# 5. ADMIN PANEL
# ──────────────────────────────────────────
@router.message(F.text == "⚙️ Admin Panel")
async def cmd_admin(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    await msg.answer("⚙️ Admin Panel:",
                     reply_markup=rk(["📂 Bo'limlar", "📦 Mahsulotlar"], ["👨‍💼 Adminlar", "👥 Kuryerlar"],
                                     ["📍 Do'kon GPS", "💳 Karta sozlash"], ["🔙 Asosiy menyu"]))


@router.message(F.text == "💳 Karta sozlash")
async def set_card(msg: Message, state: FSMContext):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    c = await q1("SELECT value FROM settings WHERE key='admin_card'");
    n = await q1("SELECT value FROM settings WHERE key='admin_card_name'")
    await msg.answer(f"Karta: {c['value']}\nEga: {n['value']}\n\nYangi raqamni yozing:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.set_card_num)


@router.message(AdminSt.set_card_num)
async def save_card_num(msg: Message, state: FSMContext):
    await state.update_data(cnum=msg.text.strip());
    await msg.answer("Karta egasining ism-familiyasi:");
    await state.set_state(AdminSt.set_card_name)


@router.message(AdminSt.set_card_name)
async def save_card_name(msg: Message, state: FSMContext):
    d = await state.get_data();
    await exe("UPDATE settings SET value=? WHERE key='admin_card'", (d['cnum'],));
    await exe("UPDATE settings SET value=? WHERE key='admin_card_name'", (msg.text.strip(),))
    await state.clear();
    await msg.answer("✅ Saqlandi!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "📍 Do'kon GPS")
async def set_gps(msg: Message, state: FSMContext):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    await msg.answer("Do'kon lokatsiyasini yuboring:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.set_coord)


@router.message(AdminSt.set_coord, F.location)
async def save_gps_geo(msg: Message, state: FSMContext):
    await exe("UPDATE settings SET value=? WHERE key='shop_lat'", (str(msg.location.latitude),));
    await exe("UPDATE settings SET value=? WHERE key='shop_lon'", (str(msg.location.longitude),))
    await state.clear();
    await msg.answer("✅ Do'kon GPS saqlandi!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "👨‍💼 Adminlar")
async def adm_admins(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    cs = await qall("SELECT * FROM admins WHERE role='admin'")
    txt = "👨‍💼 <b>Adminlar:</b>\n" + "".join([f"• <code>{c['tg_id']}</code> - {c['name']}\n" for c in cs])
    await msg.answer(txt, reply_markup=ik([("➕ Admin qo'shish", "add_adm")]))


@router.callback_query(F.data == "add_adm")
async def add_adm(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi admin ID raqami:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.admin_add);
    await call.answer()


@router.message(AdminSt.admin_add)
async def save_adm(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    await exe("INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,'Admin','admin')", (int(msg.text.strip()),))
    await state.clear();
    await msg.answer("✅ Admin qo'shildi!", reply_markup=await main_kb(msg.from_user.id))


# --- KURYERLARNI BOSHQARISH VA O'CHIRISH ---

@router.message(F.text == "👥 Kuryerlar")
async def adm_couriers(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    cs = await qall("SELECT * FROM admins WHERE role='courier'")
    # Kuryerlarni tugma qilib chiqaramiz
    btns = [[(f"🚚 {c['name']} ({c['tg_id']})", f"ecour_{c['id']}")] for c in cs]
    btns.append([("➕ Kuryer qo'shish", "add_cour")])
    await msg.answer("👥 Kuryerlarni boshqarish (Tahrirlash/O'chirish uchun ustiga bosing):", reply_markup=ik(*btns))

@router.callback_query(F.data.startswith("ecour_"))
async def edit_cour_menu(call: CallbackQuery):
    cid = int(call.data[6:])
    await call.message.edit_text("Kuryer ustida amalni tanlang:", reply_markup=ik(
        [("🗑 O'chirish (Ishdan bo'shatish)", f"delcour_{cid}")],
        [("🔙 Orqaga", "back_cour")]
    ))

@router.callback_query(F.data.startswith("delcour_"))
async def del_cour_cb(call: CallbackQuery):
    cid = int(call.data[8:])
    await exe("DELETE FROM admins WHERE id=?", (cid,))
    await call.message.edit_text("✅ Kuryer tizimdan o'chirildi!")
    await call.answer()

@router.callback_query(F.data == "back_cour")
async def back_cour_cb(call: CallbackQuery):
    cs = await qall("SELECT * FROM admins WHERE role='courier'")
    btns = [[(f"🚚 {c['name']} ({c['tg_id']})", f"ecour_{c['id']}")] for c in cs]
    btns.append([("➕ Kuryer qo'shish", "add_cour")])
    await call.message.edit_text("👥 Kuryerlarni boshqarish:", reply_markup=ik(*btns))
    await call.answer()

@router.callback_query(F.data == "add_cour")
async def add_cour(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi kuryer ID raqami:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.courier_add);
    await call.answer()


@router.message(AdminSt.courier_add)
async def save_cour(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    await exe("INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,'Kuryer','courier')", (int(msg.text.strip()),))
    await state.clear();
    await msg.answer("✅ Kuryer qo'shildi!", reply_markup=await main_kb(msg.from_user.id))


# --- BO'LIM VA MAHSULOT CRUD ---
@router.message(F.text == "📂 Bo'limlar")
async def adm_cats(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    cats = await qall("SELECT * FROM categories")
    btns = [[(f"📦 {c['name']}", f"ecat_{c['id']}")] for c in cats]
    btns.append([("➕ Yangi qo'shish", "add_cat")])
    await msg.answer("📂 Bo'limlarni boshqarish:", reply_markup=ik(*btns))


@router.callback_query(F.data.startswith("ecat_"))
async def edit_cat(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[5:]);
    await state.update_data(ecid=cid);
    await call.message.edit_text("Amalni tanlang:", reply_markup=ik([("✏️ Nomini o'zgartirish", f"rncat_{cid}")],
                                                                    [("🗑 O'chirish", f"delcat_{cid}")]))


@router.callback_query(F.data.startswith("delcat_"))
async def del_cat(call: CallbackQuery):
    cid = int(call.data[7:]);
    await exe("DELETE FROM categories WHERE id=?", (cid,));
    await call.message.edit_text("✅ O'chirildi!");
    await call.answer()


@router.callback_query(F.data == "add_cat")
async def add_cat(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Nomini yozing:", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.cat_name);
    await call.answer()


@router.message(AdminSt.cat_name)
async def save_cat(msg: Message, state: FSMContext):
    await exe("INSERT INTO categories(name) VALUES(?)", (msg.text.strip(),));
    await state.clear();
    await msg.answer("✅ Qo'shildi!", reply_markup=await main_kb(msg.from_user.id))


@router.message(F.text == "📦 Mahsulotlar")
async def adm_prods(msg: Message):
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='admin'", (msg.from_user.id,)): return
    cats = await qall("SELECT * FROM categories")
    btns = [[(c['name'], f"epcat_{c['id']}")] for c in cats]
    btns.append([("➕ Yangi mahsulot", "add_prod")])
    await msg.answer("Mahsulotlarni boshqarish:", reply_markup=ik(*btns))


@router.callback_query(F.data == "add_prod")
async def add_prod_cb(call: CallbackQuery, state: FSMContext):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    if not cats: return await call.answer("Bo'lim yo'q!", show_alert=True)
    await call.message.answer("📂 Bo'limni tanlang:",
                              reply_markup=ik(*[[(c["name"], f"selc_{c['id']}")] for c in cats]));
    await state.set_state(AdminSt.prod_cat);
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
    await msg.answer("📦 Ombor miqdori:");
    await state.set_state(AdminSt.prod_stock)


@router.message(AdminSt.prod_stock)
async def p_stock(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam!")
    await state.update_data(pstock=int(msg.text.strip()));
    await msg.answer("🖼 Rasm (yoki 'yoq'):");
    await state.set_state(AdminSt.prod_photo)


@router.message(AdminSt.prod_photo)
async def p_photo(msg: Message, state: FSMContext):
    d = await state.get_data();
    file_id = msg.photo[-1].file_id if msg.photo else ""
    await exe("INSERT INTO products(category_id,name,description,price,stock,photo_id) VALUES(?,?,?,?,?,?)",
              (d["cid"], d["pname"], d["pdesc"], d["pprice"], d["pstock"], file_id))
    await state.clear();
    await msg.answer("✅ Mahsulot qo'shildi!", reply_markup=await main_kb(msg.from_user.id))


@router.callback_query(F.data.startswith("epcat_"))
async def edit_prod_list(call: CallbackQuery):
    prods = await qall("SELECT * FROM products WHERE category_id=?", (int(call.data[6:]),))
    await call.message.edit_text("Mahsulotni tanlang:",
                                 reply_markup=ik(*[[(p['name'], f"eprod_{p['id']}")] for p in prods]))


@router.callback_query(F.data.startswith("eprod_"))
async def edit_prod_menu(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[6:]);
    p = await q1("SELECT * FROM products WHERE id=?", (pid,))
    txt = f"📦 {p['name']}\n💰 {fmt(p['price'])} so'm"
    btns = [[("📝 Nom", f"epv_name_{pid}"), ("📄 Tavsif", f"epv_desc_{pid}")],
            [("💰 Narx", f"epv_price_{pid}"), ("📦 Ombor", f"epv_stock_{pid}")],
            [("🖼 Rasm", f"epv_photo_{pid}"), ("🗑 O'chirish", f"epv_del_{pid}")]]
    await safe_delete(call.message);
    if p['photo_id']:
        await bot.send_photo(call.from_user.id, p['photo_id'], caption=txt, reply_markup=ik(*btns))
    else:
        await bot.send_message(call.from_user.id, txt, reply_markup=ik(*btns))


@router.callback_query(F.data.startswith("epv_"))
async def edit_val(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_");
    field, pid = parts[1], int(parts[2])
    if field == 'del': await exe("DELETE FROM products WHERE id=?", (pid,)); return await call.message.answer(
        "✅ O'chirildi!")
    await state.update_data(epid=pid, efield=field);
    await call.message.answer(f"Yangi {field} qiymatini yuboring:");
    await state.set_state(AdminSt.edit_prod_val);
    await call.answer()


@router.message(AdminSt.edit_prod_val)
async def save_val(msg: Message, state: FSMContext):
    d = await state.get_data();
    col = {"name": "name", "desc": "description", "price": "price", "stock": "stock"}.get(d['efield'])
    val = msg.photo[-1].file_id if msg.photo else msg.text
    if col:
        await exe(f"UPDATE products SET {col}=? WHERE id=?", (val, d['epid']))
    elif d['efield'] == 'photo':
        await exe("UPDATE products SET photo_id=? WHERE id=?", (val, d['epid']))
    await state.clear();
    await msg.answer("✅ Yangilandi!", reply_markup=await main_kb(msg.from_user.id))


# ──────────────────────────────────────────
# 6. ADMIN TASDIQLASH (AVTOMAT VA QO'LDA)
# ──────────────────────────────────────────
async def approve_order_logic(oid: int, fee: int, admin_id: int):
    await exe("UPDATE orders SET delivery_fee=?, status='pending_courier' WHERE id=?", (fee, oid))
    o = await q1("SELECT * FROM orders WHERE id=?", (oid,))

    try:
        await bot.send_message(o['user_id'],
                               f"✅ Buyurtmangiz tasdiqlandi!\n\n🚚 Yo'lkira: {fmt(fee)} so'm\n💰 Jami: {fmt(o['total_amount'] + fee)} so'm\n\nTez orada kuryer aloqaga chiqadi.")
    except:
        pass

    cs = await qall("SELECT tg_id FROM admins WHERE role='courier' AND is_active=1")
    for cr in cs:
        try:
            if o['lat'] != 0.0: await bot.send_location(cr['tg_id'], o['lat'], o['lon'])
            await bot.send_message(cr['tg_id'],
                                   f"📦 <b>Buyurtma #{oid}</b>\n📍 Manzil: {o['address']} {o['apt']}\n📏 Masofa: {o['distance']:.1f} km\n💰 Kuryer haqqi: {fmt(fee)} so'm",
                                   reply_markup=ik([("🙋 Men yetkazaman", f"ctake_{oid}")]))
        except:
            pass


@router.callback_query(F.data.startswith("autofee_"))
async def auto_fee_cb(call: CallbackQuery):
    parts = call.data.split("_");
    oid = int(parts[1]);
    fee = int(parts[2])
    await approve_order_logic(oid, fee, call.from_user.id)
    await safe_delete(call.message)
    await call.message.answer(f"✅ #{oid} avtomat ({fmt(fee)} so'm) narx bilan tasdiqlandi!")
    await call.answer()


@router.callback_query(F.data.startswith("setfee_"))
async def set_fee_cb(call: CallbackQuery, state: FSMContext):
    await state.update_data(foid=int(call.data[7:]));
    await call.message.answer("💰 Boshqa yetkazish narxini yozing (faqat raqam):", reply_markup=CANCEL_KB);
    await state.set_state(AdminSt.set_fee);
    await call.answer()


@router.message(AdminSt.set_fee)
async def save_fee(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Faqat raqam kiriting!")
    fee = int(msg.text);
    oid = (await state.get_data())["foid"]
    await approve_order_logic(oid, fee, msg.from_user.id)
    await state.clear();
    await msg.answer("✅ Tasdiqlandi.", reply_markup=await main_kb(msg.from_user.id))


@router.callback_query(F.data.startswith("acancel_"))
async def acancel_cb(call: CallbackQuery, state: FSMContext):
    await state.update_data(c_oid=int(call.data[8:]));
    await call.message.answer("❌ Sababni tanlang:",
                              reply_markup=ik([("Mahsulot qolmagan", "ar_1")], [("Bog'lanib bo'lmadi", "ar_2")],
                                              [("✏️ Qo'lda yozish", "ar_3")]));
    await call.answer()


@router.callback_query(F.data.startswith("ar_"))
async def areason_cb(call: CallbackQuery, state: FSMContext):
    oid = (await state.get_data()).get("c_oid")
    if call.data == "ar_3":
        await call.message.answer("✏️ Sababni yozing:", reply_markup=CANCEL_KB);
        await state.set_state(AdminSt.cancel_reason);
        return await call.answer()
    r = "Mahsulot qolmagan" if call.data == "ar_1" else "Bog'lanib bo'lmadi"
    await exe("UPDATE orders SET status='cancelled', cancel_reason=? WHERE id=?", (f"Admin: {r}", oid))
    await return_stock(oid)
    await state.clear();
    await call.message.edit_text("✅ Bekor qilindi.")
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))
    if o:
        try:
            await bot.send_message(o["user_id"], f"❌ #{oid} bekor qilindi.\nSabab: {r}")
        except:
            pass
    await call.answer()


@router.message(AdminSt.cancel_reason)
async def areason_txt(msg: Message, state: FSMContext):
    oid = (await state.get_data())["c_oid"];
    await exe("UPDATE orders SET status='cancelled', cancel_reason=? WHERE id=?", (f"Admin: {msg.text}", oid))
    await return_stock(oid)
    await state.clear();
    await msg.answer("✅ Bekor qilindi.", reply_markup=await main_kb(msg.from_user.id))
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,))
    if o:
        try:
            await bot.send_message(o["user_id"], f"❌ #{oid} bekor qilindi.\nSabab: {msg.text}")
        except:
            pass


# ──────────────────────────────────────────
# 7. KURYER PANELI VA STATISTIKA
# ──────────────────────────────────────────
@router.message(F.text == "🚚 Kuryer Panel")
async def cpanel(msg: Message):
    uid = msg.from_user.id
    if not await q1("SELECT 1 FROM admins WHERE tg_id=? AND role='courier'", (uid,)): return

    stats = await q1(
        "SELECT COUNT(*) as cnt, AVG(distance) as avg_dist FROM orders WHERE courier_id=? AND status='delivered' AND date(created_at) = date('now','localtime')",
        (uid,))
    cnt = stats['cnt'] if stats and stats['cnt'] else 0
    avg_dist = stats['avg_dist'] if stats and stats['avg_dist'] else 0.0

    stat_txt = (
        f"📊 <b>Sizning bugungi statistikangiz:</b>\n"
        f"📦 Yetkazilgan: <b>{cnt} ta</b>\n"
        f"📏 O'rtacha masofa: <b>{avg_dist:.1f} km</b>\n"
        f"──────────────────\n"
    )

    ords = await qall("SELECT * FROM orders WHERE courier_id=? AND status='on_way'", (uid,))
    if not ords: return await msg.answer(stat_txt + "Hozirda faol buyurtmalaringiz yo'q.")

    await msg.answer(stat_txt + "🚚 <b>Sizdagi faol buyurtmalar:</b>")
    for o in ords:
        await msg.answer(f"📦 #{o['id']}\n📍 {o['address']} {o['apt']}",
                         reply_markup=ik([("✅ Yetkazdim", f"cdeliv_{o['id']}")]))


@router.callback_query(F.data.startswith("ctake_"))
async def ctake(call: CallbackQuery):
    oid = int(call.data[6:]);
    o = await q1("SELECT status FROM orders WHERE id=?", (oid,))
    if o['status'] != 'pending_courier':
        return await call.answer("Bu buyurtma boshqa kuryerda yoki bekor qilingan!", show_alert=True)

    await exe("UPDATE orders SET status='on_way', courier_id=? WHERE id=?", (call.from_user.id, oid))
    o = await q1("SELECT * FROM orders WHERE id=?", (oid,));
    await call.message.edit_text(f"✅ #{oid} sizniki!");
    await bot.send_message(o['user_id'], "🚚 Kuryerimiz buyurtmangizni oldi va siz tomonga yo'lga chiqdi!")


@router.callback_query(F.data.startswith("cdeliv_"))
async def cdelivered(call: CallbackQuery):
    oid = int(call.data[7:]);
    await exe("UPDATE orders SET status='delivered' WHERE id=?", (oid,));
    await call.message.edit_text(f"✅ #{oid} yetkazildi!")
    o = await q1("SELECT user_id FROM orders WHERE id=?", (oid,));
    await bot.send_message(o['user_id'], f"🎉 Yetkazildi! Osh bo'lsin.\nBaho bering:",
                           reply_markup=ik([("⭐⭐⭐⭐⭐", f"star_{oid}_5")]))


# ──────────────────────────────────────────
# YORDAMCHI
# ──────────────────────────────────────────
@router.message(F.text == "🔙 Asosiy menyu")
async def go_home(msg: Message, state: FSMContext):
    await state.clear();
    await msg.answer("🏠 Asosiy menyu", reply_markup=await main_kb(msg.from_user.id))


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery): await call.answer()


@router.message()
async def catch_all(msg: Message):
    await msg.answer("❓ Tushunmadim. Menyudan foydalaning:", reply_markup=await main_kb(msg.from_user.id))


async def main():
    await init_db()
    dp.include_router(router)
    await bot.set_my_commands([BotCommand(command="start", description="Boshlash")])
    print("🚀 Bot ishga tushdi...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())