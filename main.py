#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           ENTERPRISE SHOP BOT  —  To'liq Professional Telegram Bot          ║
║                         Barcha funksiyalar bir faylda                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  O'rnatish:  pip install aiogram aiosqlite                                   ║
║  Ishga tushirish: python shop_enterprise.py                                  ║
║  Muhit o'zgaruvchilari:                                                      ║
║    BOT_TOKEN  — BotFather dan olingan token                                  ║
║    ADMIN_IDS  — Admin Telegram ID'lari, vergul bilan  (masalan: 111,222)     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio, logging, os, random, string, json
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    BotCommand, InputMediaPhoto
)
import aiosqlite

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ShopBot")

# ══════════════════════════════════════════════════════════════════════════════
#  KONFIGURATSIYA
# ══════════════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8747604242:AAFj9oSG5txNx1Pw7UfCAc9WH_Em8tB73p0")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "8488028783").split(",")
    if x.strip().isdigit()
]
DB_PATH = "shop.db"

# Ball tizimi
POINTS_PER_SUM      = 1000    # 1 000 so'm → 1 ball
POINT_VALUE_SUM     = 100     # 1 ball → 100 so'm
REFERRAL_POINTS     = 500
FIRST_ORDER_POINTS  = 200

ORDER_STATUSES = {
    "new":       "🆕 Yangi",
    "confirmed": "✅ Tasdiqlangan",
    "cooking":   "👨‍🍳 Tayyorlanmoqda",
    "on_way":    "🚚 Yo'lda",
    "delivered": "✅ Yetkazildi",
    "cancelled": "❌ Bekor qilindi",
}
PAYMENT_LABELS = {
    "cash":  "💵 Naqd pul",
    "card":  "💳 Plastik karta",
    "click": "📱 Click",
    "payme": "📱 Payme",
}

# ══════════════════════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════════════════════
class Reg(StatesGroup):
    name  = State()
    phone = State()

class Shop(StatesGroup):
    catalog = State()
    search  = State()
    product = State()

class Checkout(StatesGroup):
    promo   = State()
    points  = State()
    phone   = State()
    address = State()
    zone    = State()
    payment = State()
    confirm = State()

class ReviewSt(StatesGroup):
    rating  = State()
    comment = State()

class SupportSt(StatesGroup):
    subject = State()
    chat    = State()

class AdminSt(StatesGroup):
    # Categories
    cat_name       = State()
    cat_emoji      = State()
    cat_edit_name  = State()
    # Products
    prod_cat       = State()
    prod_name      = State()
    prod_desc      = State()
    prod_price     = State()
    prod_stock     = State()
    prod_photo     = State()
    prod_edit_fld  = State()
    prod_edit_val  = State()
    # Flash Sale
    flash_pid      = State()
    flash_price    = State()
    flash_hours    = State()
    # Orders
    ord_msg        = State()
    # Courier assign
    assign_ord_id  = State()
    # Promo
    promo_code     = State()
    promo_type     = State()
    promo_val      = State()
    promo_cat      = State()
    promo_min      = State()
    promo_uses     = State()
    promo_exp      = State()
    # Zones
    zone_name      = State()
    zone_fee       = State()
    zone_time      = State()
    zone_min       = State()
    zone_edit_fld  = State()
    zone_edit_val  = State()
    # Settings
    setting_val    = State()
    setting_key    = State()
    # Broadcast
    bcast_msg      = State()
    # Courier mgmt
    courier_add    = State()
    # Support reply
    support_rep    = State()
    support_tid    = State()

class CourierSt(StatesGroup):
    menu = State()

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id        INTEGER UNIQUE NOT NULL,
            name         TEXT    NOT NULL DEFAULT 'Foydalanuvchi',
            phone        TEXT    DEFAULT '',
            points       INTEGER DEFAULT 0,
            ref_code     TEXT    UNIQUE,
            ref_by       INTEGER DEFAULT 0,
            is_blocked   INTEGER DEFAULT 0,
            orders_count INTEGER DEFAULT 0,
            total_spent  INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS admins (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id      INTEGER UNIQUE NOT NULL,
            name       TEXT    DEFAULT 'Admin',
            role       TEXT    DEFAULT 'admin',
            is_active  INTEGER DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS categories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            emoji      TEXT    DEFAULT '📦',
            is_active  INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id  INTEGER REFERENCES categories(id),
            name         TEXT    NOT NULL,
            description  TEXT    DEFAULT '',
            price        INTEGER NOT NULL DEFAULT 0,
            old_price    INTEGER DEFAULT 0,
            stock        INTEGER DEFAULT 0,
            photo_id     TEXT    DEFAULT '',
            is_active    INTEGER DEFAULT 1,
            is_flash     INTEGER DEFAULT 0,
            flash_price  INTEGER DEFAULT 0,
            flash_until  TEXT    DEFAULT '',
            is_top       INTEGER DEFAULT 0,
            sold_count   INTEGER DEFAULT 0,
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS cart (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity   INTEGER DEFAULT 1,
            UNIQUE(user_id, product_id)
        );

        CREATE TABLE IF NOT EXISTS delivery_zones (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            delivery_fee  INTEGER DEFAULT 0,
            min_order     INTEGER DEFAULT 0,
            delivery_time TEXT    DEFAULT '30-45 daqiqa',
            is_active     INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS orders (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            courier_id     INTEGER DEFAULT 0,
            zone_id        INTEGER DEFAULT 0,
            status         TEXT    DEFAULT 'new',
            total_amount   INTEGER DEFAULT 0,
            delivery_fee   INTEGER DEFAULT 0,
            discount       INTEGER DEFAULT 0,
            points_used    INTEGER DEFAULT 0,
            points_earned  INTEGER DEFAULT 0,
            promo_code     TEXT    DEFAULT '',
            payment_method TEXT    DEFAULT 'cash',
            phone          TEXT    DEFAULT '',
            address        TEXT    DEFAULT '',
            comment        TEXT    DEFAULT '',
            estimated_time TEXT    DEFAULT '',
            created_at     TEXT    DEFAULT (datetime('now','localtime')),
            updated_at     TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id     INTEGER NOT NULL REFERENCES orders(id),
            product_id   INTEGER NOT NULL,
            product_name TEXT    NOT NULL,
            quantity     INTEGER NOT NULL,
            price        INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            order_id   INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            rating     INTEGER NOT NULL,
            comment    TEXT    DEFAULT '',
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS promos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            code           TEXT    UNIQUE NOT NULL,
            discount_type  TEXT    DEFAULT 'percent',
            discount_value INTEGER NOT NULL DEFAULT 0,
            category_id    INTEGER DEFAULT 0,
            min_order      INTEGER DEFAULT 0,
            max_uses       INTEGER DEFAULT 0,
            used_count     INTEGER DEFAULT 0,
            is_active      INTEGER DEFAULT 1,
            expires_at     TEXT    DEFAULT '',
            created_at     TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS support_tickets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            subject    TEXT    DEFAULT 'Muammo',
            status     TEXT    DEFAULT 'open',
            admin_id   INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now','localtime')),
            updated_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS support_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id  INTEGER NOT NULL,
            sender_id  INTEGER NOT NULL,
            is_admin   INTEGER DEFAULT 0,
            message    TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS shop_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS point_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            amount     INTEGER NOT NULL,
            reason     TEXT    DEFAULT '',
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        );
        """)

        defaults = [
            ("shop_name",       "🛒 Enterprise Shop"),
            ("shop_open",       "1"),
            ("open_time",       "09:00"),
            ("close_time",      "23:00"),
            ("min_order",       "15000"),
            ("welcome_msg",     "Bizning do'konimizga xush kelibsiz! 🎉"),
            ("currency",        "so'm"),
            ("about_text",      "Biz – sifatli mahsulotlarni tez va arzon yetkazib beramiz."),
            ("instagram",       ""),
            ("phone_support",   "+998 90 000 00 00"),
        ]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO shop_settings(key,value) VALUES(?,?)", (k, v))

        for admin_id in ADMIN_IDS:
            await db.execute(
                "INSERT OR IGNORE INTO admins(tg_id,name,role) VALUES(?,'Super Admin','admin')",
                (admin_id,)
            )

        await db.commit()
    logger.info("✅ Database initialized")


# ══════════════════════════════════════════════════════════════════════════════
#  DB HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def q1(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as c:
            r = await c.fetchone()
            return dict(r) if r else None

async def qall(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as c:
            return [dict(r) for r in await c.fetchall()]

async def exe(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, params)
        await db.commit()

async def setting(key: str) -> str:
    r = await q1("SELECT value FROM shop_settings WHERE key=?", (key,))
    return r["value"] if r else ""

async def set_setting(key: str, value: str):
    await exe("INSERT OR REPLACE INTO shop_settings(key,value) VALUES(?,?)", (key, value))

async def is_open():
    if await setting("shop_open") != "1":
        return False, "Do'kon hozir yopiq 🔴"
    ot, ct = await setting("open_time"), await setting("close_time")
    now = datetime.now().strftime("%H:%M")
    if ot <= now <= ct:
        return True, ""
    return False, f"Ish vaqti: {ot}–{ct}"

async def get_user(tg_id):
    return await q1("SELECT * FROM users WHERE tg_id=?", (tg_id,))

async def upsert_user(tg_id, name):
    rc = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    await exe(
        "INSERT OR IGNORE INTO users(tg_id,name,ref_code) VALUES(?,?,?)",
        (tg_id, name, rc)
    )
    return await get_user(tg_id)

async def is_admin(tg_id):
    return bool(await q1("SELECT id FROM admins WHERE tg_id=? AND role='admin' AND is_active=1", (tg_id,)))

async def is_courier(tg_id):
    return bool(await q1("SELECT id FROM admins WHERE tg_id=? AND role='courier' AND is_active=1", (tg_id,)))

async def add_points(user_id, amount, reason=""):
    await exe("UPDATE users SET points=points+? WHERE tg_id=?", (amount, user_id))
    await exe("INSERT INTO point_log(user_id,amount,reason) VALUES(?,?,?)", (user_id, amount, reason))

async def get_cart(user_id):
    return await qall("""
        SELECT c.id, c.product_id, c.quantity,
               p.name, p.price, p.flash_price, p.is_flash, p.stock, p.photo_id
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
    """, (user_id,))

async def cart_total(user_id):
    items = await get_cart(user_id)
    t = 0
    for i in items:
        p = i["flash_price"] if i["is_flash"] and i["flash_price"] else i["price"]
        t += p * i["quantity"]
    return t

async def clear_cart(user_id):
    await exe("DELETE FROM cart WHERE user_id=?", (user_id,))


# ══════════════════════════════════════════════════════════════════════════════
#  FORMATTERS
# ══════════════════════════════════════════════════════════════════════════════
def fmt(n):        return f"{n:,}".replace(",", " ")
def stars(r):      return "⭐" * r + "☆" * (5 - r)
def oid(n):        return f"#{n:05d}"
def now_str():     return datetime.now().strftime("%Y-%m-%d %H:%M")


async def fmt_cart(user_id):
    items = await get_cart(user_id)
    if not items:
        return "🛒 Savatingiz bo'sh"
    txt = "🛒 <b>Sizning savatingiz:</b>\n\n"
    total = 0
    for i, it in enumerate(items, 1):
        pr = it["flash_price"] if it["is_flash"] and it["flash_price"] else it["price"]
        sub = pr * it["quantity"]
        total += sub
        fl = " ⚡" if it["is_flash"] and it["flash_price"] else ""
        txt += f"{i}. {it['name']}{fl}\n   {fmt(pr)} × {it['quantity']} = <b>{fmt(sub)} so'm</b>\n"
    txt += f"\n💰 <b>Jami: {fmt(total)} so'm</b>"
    return txt


async def fmt_order(order_id):
    o = await q1("SELECT * FROM orders WHERE id=?", (order_id,))
    if not o:
        return "Buyurtma topilmadi"
    items = await qall("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    user  = await get_user(o["user_id"])
    zone  = await q1("SELECT name FROM delivery_zones WHERE id=?", (o["zone_id"],))

    status  = ORDER_STATUSES.get(o["status"], o["status"])
    payment = PAYMENT_LABELS.get(o["payment_method"], o["payment_method"])

    txt  = f"📦 <b>Buyurtma {oid(order_id)}</b>\n"
    txt += f"📊 Holat: {status}\n"
    txt += f"📅 Vaqt: {o['created_at'][:16]}\n"
    if user:
        txt += f"👤 Mijoz: {user['name']}\n"
    txt += f"📱 Telefon: {o['phone']}\n"
    txt += f"📍 Manzil: {o['address']}\n"
    if zone:
        txt += f"🗺 Zona: {zone['name']}\n"
    if o["estimated_time"]:
        txt += f"⏱ Taxminiy vaqt: {o['estimated_time']}\n"
    txt += "\n🛒 <b>Mahsulotlar:</b>\n"
    for it in items:
        txt += f"  • {it['product_name']} ×{it['quantity']} = {fmt(it['price'] * it['quantity'])} so'm\n"

    sub_total = o["total_amount"]
    d_fee     = o["delivery_fee"]
    discount  = o["discount"]
    pts_disc  = o["points_used"] * POINT_VALUE_SUM
    final     = max(0, sub_total + d_fee - discount - pts_disc)

    txt += f"\n💰 Mahsulotlar: {fmt(sub_total)} so'm\n"
    txt += f"🚚 Yetkazish: {fmt(d_fee)} so'm\n"
    if discount:
        txt += f"🎟 Promo chegirma: -{fmt(discount)} so'm\n"
    if o["points_used"]:
        txt += f"💎 Ballar chegirma: -{fmt(pts_disc)} so'm\n"
    txt += f"\n💵 <b>To'lash kerak: {fmt(final)} so'm</b>\n"
    txt += f"💳 To'lov usuli: {payment}\n"
    if o["promo_code"]:
        txt += f"🎟 Promo kod: <code>{o['promo_code']}</code>\n"
    if o["comment"]:
        txt += f"💬 Izoh: {o['comment']}\n"
    return txt


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════════════
def ik(*rows):
    """Build InlineKeyboardMarkup from list of (text, callback_data) tuples per row."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])

def rk(*rows, resize=True, one_time=False):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=resize,
        one_time_keyboard=one_time,
    )

CANCEL_KB = rk(["❌ Bekor qilish"])

def main_kb(adm=False, cour=False):
    rows = [
        ["🛍 Katalog", "🔍 Qidiruv"],
        ["🛒 Savatcha", "📦 Buyurtmalarim"],
        ["⚡ Flash Sale", "⭐ TOP mahsulotlar"],
        ["💎 Ballarim", "👤 Profilim"],
        ["🆘 Yordam", "🤝 Referal"],
    ]
    if adm:  rows.append(["⚙️ Admin Panel"])
    if cour: rows.append(["🚚 Kuryer Panel"])
    return rk(*rows)

def admin_kb():
    return rk(
        ["📂 Bo'limlar", "📦 Mahsulotlar"],
        ["🛒 Buyurtmalar", "👥 Kuryerlar"],
        ["⚡ Flash Sale", "🎟 Promo kodlar"],
        ["🗺 Yetkazish zonalari", "🆘 Support"],
        ["📊 Statistika", "📨 Broadcast"],
        ["⚙️ Sozlamalar", "🔙 Asosiy menyu"],
    )

def courier_kb():
    return rk(["📋 Buyurtmalarim", "🔙 Asosiy menyu"])

def phone_request_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Raqamimni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
    )

def categories_ik(cats):
    rows = [[f"{c['emoji']} {c['name']}", f"cat_{c['id']}"] for c in cats]
    return ik(*[[r] for r in rows])

def products_ik(prods, page, total, per=8, cat_id=0):
    rows = []
    for p in prods:
        pr = p["flash_price"] if p["is_flash"] and p["flash_price"] else p["price"]
        tag = "⚡" if p["is_flash"] and p["flash_price"] else ("🔥" if p["is_top"] else "")
        st  = "✅" if p["stock"] > 0 else "❌"
        rows.append([f"{st}{tag} {p['name']} — {fmt(pr)} so'm", f"prod_{p['id']}"])
    nav = []
    if page > 0:
        nav.append(["◀️", f"pgcat_{cat_id}_{page-1}"])
    nav.append([f"{page+1}/{max(1,(total-1)//per+1)}", "noop"])
    if (page+1)*per < total:
        nav.append(["▶️", f"pgcat_{cat_id}_{page+1}"])
    if nav:
        rows.append(nav)
    rows.append(["🔙 Bo'limlarga qaytish", "back_cats"])
    return ik(*[[r] for r in rows])

def product_detail_ik(pid, qty=0):
    rows = []
    if qty > 0:
        rows.append([
            ("➖", f"cdec_{pid}"),
            (f"🛒 {qty} ta", "view_cart"),
            ("➕", f"cinc_{pid}"),
        ])
    else:
        rows.append([("🛒 Savatga qo'shish", f"cadd_{pid}")])
    rows.append([("🔙 Orqaga", "back_prods")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t,c in row]
        for row in rows
    ])

def cart_ik(items):
    rows = []
    for it in items:
        pr = it["flash_price"] if it["is_flash"] and it["flash_price"] else it["price"]
        rows.append([
            InlineKeyboardButton(text="➖", callback_data=f"cdec_{it['product_id']}"),
            InlineKeyboardButton(text=f"{it['name'][:22]}·{it['quantity']}шт", callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"cinc_{it['product_id']}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows + [
        [InlineKeyboardButton(text="🗑 Savatni tozalash",  callback_data="cart_clear")],
        [InlineKeyboardButton(text="✅ Buyurtma berish",   callback_data="checkout_start")],
    ])

def zones_ik(zones):
    rows = []
    for z in zones:
        label = f"📍 {z['name']}  |  🚚 {fmt(z['delivery_fee'])} so'm  |  ⏱ {z['delivery_time']}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"zone_{z['id']}")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def payments_ik():
    return ik(
        [("💵 Naqd pul",       "pay_cash")],
        [("💳 Plastik karta",  "pay_card")],
        [("📱 Click",          "pay_click")],
        [("📱 Payme",          "pay_payme")],
        [("🔙 Orqaga",         "back")],
    )

def orders_list_ik(orders, prefix="ord"):
    rows = []
    for o in orders:
        st = ORDER_STATUSES.get(o["status"], o["status"])
        rows.append([InlineKeyboardButton(
            text=f"{oid(o['id'])} {st} — {fmt(o['total_amount'])} so'm",
            callback_data=f"{prefix}_{o['id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

def admin_order_ik(order_id, status):
    flow = {
        "new":       [("✅ Tasdiqlash",          f"ostatus_{order_id}_confirmed"),
                      ("❌ Bekor qilish",         f"ostatus_{order_id}_cancelled")],
        "confirmed": [("👨‍🍳 Tayyorlanmoqda",    f"ostatus_{order_id}_cooking"),
                      ("❌ Bekor qilish",         f"ostatus_{order_id}_cancelled")],
        "cooking":   [("🚚 Yo'lga chiqarish",     f"ostatus_{order_id}_on_way")],
        "on_way":    [("✅ Yetkazildi",            f"ostatus_{order_id}_delivered")],
    }
    rows = []
    for text, cb in flow.get(status, []):
        rows.append([InlineKeyboardButton(text=text, callback_data=cb)])
    if status not in ("delivered", "cancelled"):
        rows.append([InlineKeyboardButton(text="📩 Mijozga xabar",     callback_data=f"omsg_{order_id}")])
        rows.append([InlineKeyboardButton(text="🚚 Kuryer biriktirish", callback_data=f"oassign_{order_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Buyurtmalar",            callback_data="admin_orders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def courier_order_ik(order_id, status):
    rows = []
    if status == "on_way":
        rows.append([InlineKeyboardButton(text="✅ Yetkazildi deb belgilash", callback_data=f"cdeliver_{order_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="courier_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def yes_no_ik(yes_cb, no_cb):
    return ik([(f"✅ Ha", yes_cb), (f"❌ Yo'q", no_cb)])

def skip_ik(cb="skip"):
    return ik([(f"⏭ O'tkazib yuborish", cb)])


# ══════════════════════════════════════════════════════════════════════════════
#  BOT & ROUTER
# ══════════════════════════════════════════════════════════════════════════════
bot    = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
router = Router()
dp     = Dispatcher(storage=MemoryStorage())
dp.include_router(router)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCS
# ══════════════════════════════════════════════════════════════════════════════
async def notify_admins(text: str):
    admins = await qall("SELECT tg_id FROM admins WHERE role='admin' AND is_active=1")
    for a in admins:
        try:
            await bot.send_message(a["tg_id"], text)
        except Exception:
            pass

async def get_main_kb(tg_id):
    return main_kb(await is_admin(tg_id), await is_courier(tg_id))

async def safe_delete(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

async def check_user(message: Message, state: FSMContext):
    """Make sure user is registered; redirect to reg if not."""
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Iltimos, avval /start buyrug'ini yuboring.")
        return None
    return user

async def apply_promo(code: str, category_ids: list, total: int):
    """Returns discount amount or (0, error_msg)."""
    p = await q1("SELECT * FROM promos WHERE code=? AND is_active=1", (code,))
    if not p:
        return 0, "❌ Promo kod topilmadi yoki faol emas"
    if p["expires_at"] and p["expires_at"] < now_str()[:10]:
        return 0, "❌ Promo kod muddati tugagan"
    if p["max_uses"] > 0 and p["used_count"] >= p["max_uses"]:
        return 0, "❌ Promo kod foydalanish chegarasiga yetdi"
    if p["min_order"] > total:
        return 0, f"❌ Minimal buyurtma summasi: {fmt(p['min_order'])} so'm"
    if p["category_id"] and p["category_id"] not in category_ids:
        return 0, "❌ Bu promo kod ushbu bo'lim mahsulotlari uchun emas"
    if p["discount_type"] == "percent":
        disc = total * p["discount_value"] // 100
    else:
        disc = p["discount_value"]
    return min(disc, total), None


# ══════════════════════════════════════════════════════════════════════════════
#  ═══════════════════  USER HANDLERS  ═══════════════════
# ══════════════════════════════════════════════════════════════════════════════

# ─── /start ───────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    uid  = msg.from_user.id
    user = await get_user(uid)
    args = msg.text.split()
    ref  = args[1] if len(args) > 1 else None

    if not user:
        await state.update_data(ref=ref)
        wm = await setting("welcome_msg")
        sn = await setting("shop_name")
        await msg.answer(
            f"<b>{sn}</b>\n\n{wm}\n\n👋 Ro'yxatdan o'tish uchun ismingizni kiriting:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(Reg.name)
    else:
        sn = await setting("shop_name")
        op, _ = await is_open()
        st = "🟢 Ochiq" if op else "🔴 Yopiq"
        await msg.answer(
            f"🏠 <b>{sn}</b>\nDo'kon holati: {st}\n\nNima kerak?",
            reply_markup=await get_main_kb(uid),
        )


@router.message(Reg.name)
async def reg_name(msg: Message, state: FSMContext):
    n = msg.text.strip()
    if len(n) < 2:
        await msg.answer("❌ Ism juda qisqa. Qaytadan kiriting:")
        return
    await state.update_data(name=n)
    await msg.answer(f"✅ Salom, <b>{n}</b>!\n\n📱 Telefon raqamingizni yuboring:", reply_markup=phone_request_kb())
    await state.set_state(Reg.phone)


@router.message(Reg.phone, F.contact)
async def reg_phone_contact(msg: Message, state: FSMContext):
    ph = msg.contact.phone_number
    if not ph.startswith("+"): ph = "+" + ph
    await _finish_reg(msg, state, ph)


@router.message(Reg.phone, F.text)
async def reg_phone_text(msg: Message, state: FSMContext):
    t = msg.text.strip()
    if t == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return
    ph = t if t.startswith("+") else "+998" + t.lstrip("0")
    await _finish_reg(msg, state, ph)


async def _finish_reg(msg: Message, state: FSMContext, phone: str):
    data   = await state.get_data()
    name   = data.get("name", msg.from_user.first_name or "Foydalanuvchi")
    ref    = data.get("ref")
    uid    = msg.from_user.id
    rc     = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    ref_by = 0

    if ref:
        ru = await q1("SELECT tg_id FROM users WHERE ref_code=?", (ref,))
        if ru:
            ref_by = ru["tg_id"]

    await exe(
        "INSERT OR IGNORE INTO users(tg_id,name,phone,ref_code,ref_by) VALUES(?,?,?,?,?)",
        (uid, name, phone, rc, ref_by),
    )
    if ref_by:
        await add_points(ref_by, REFERRAL_POINTS, "Referal bonus")
        try:
            await bot.send_message(
                ref_by,
                f"🎉 <b>Yangi referal!</b>\n<b>{name}</b> sizning havolangiz orqali ro'yxatdan o'tdi!\n💎 +{REFERRAL_POINTS} ball oldiniz!"
            )
        except Exception:
            pass

    await state.clear()
    sn = await setting("shop_name")
    await msg.answer(
        f"✅ <b>Ro'yxatdan muvaffaqiyatli o'tdingiz!</b>\n\n"
        f"👤 Ism: {name}\n📱 Telefon: {phone}\n"
        f"🔗 Referal kodingiz: <code>{rc}</code>\n\n"
        f"<b>{sn}</b> ga xush kelibsiz! 🎉",
        reply_markup=await get_main_kb(uid),
    )


# ─── KATALOG ──────────────────────────────────────────────────────────────────
@router.message(F.text == "🛍 Katalog")
async def cmd_catalog(msg: Message, state: FSMContext):
    user = await check_user(msg, state)
    if not user: return
    cats = await qall("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order,id")
    if not cats:
        await msg.answer("📂 Hozircha bo'limlar mavjud emas.")
        return
    await state.update_data(from_catalog=True)
    await msg.answer("📂 <b>Bo'limlarni tanlang:</b>", reply_markup=categories_ik(cats))


@router.callback_query(F.data.startswith("cat_"))
async def show_category(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data[4:])
    await _show_products(call, state, cat_id, 0)


@router.callback_query(F.data.startswith("pgcat_"))
async def page_products(call: CallbackQuery, state: FSMContext):
    _, cat_id, page = call.data.split("_")
    await _show_products(call, state, int(cat_id), int(page))


async def _show_products(call, state, cat_id, page):
    per   = 8
    cat   = await q1("SELECT * FROM categories WHERE id=?", (cat_id,))
    total = (await q1("SELECT COUNT(*) as n FROM products WHERE category_id=? AND is_active=1", (cat_id,)))["n"]
    prods = await qall(
        "SELECT * FROM products WHERE category_id=? AND is_active=1 ORDER BY is_top DESC,sold_count DESC LIMIT ? OFFSET ?",
        (cat_id, per, page * per)
    )
    await state.update_data(current_cat=cat_id, current_page=page)
    txt = f"{cat['emoji']} <b>{cat['name']}</b>\n({total} ta mahsulot)"
    kb  = products_ik(prods, page, total, per, cat_id)
    try:
        await call.message.edit_text(txt, reply_markup=kb)
    except Exception:
        await call.message.answer(txt, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "back_cats")
async def back_to_cats(call: CallbackQuery, state: FSMContext):
    cats = await qall("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order,id")
    try:
        await call.message.edit_text("📂 <b>Bo'limlarni tanlang:</b>", reply_markup=categories_ik(cats))
    except Exception:
        await call.message.answer("📂 <b>Bo'limlarni tanlang:</b>", reply_markup=categories_ik(cats))
    await call.answer()


@router.callback_query(F.data.startswith("prod_"))
async def show_product(call: CallbackQuery, state: FSMContext):
    pid  = int(call.data[5:])
    p    = await q1("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id=c.id WHERE p.id=?", (pid,))
    if not p:
        await call.answer("Mahsulot topilmadi"); return
    await state.update_data(current_prod=pid)

    uid = call.from_user.id
    ci  = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
    qty = ci["quantity"] if ci else 0

    pr   = p["flash_price"] if p["is_flash"] and p["flash_price"] else p["price"]
    tags = []
    if p["is_flash"] and p["flash_price"]: tags.append("⚡ Flash Sale")
    if p["is_top"]:                         tags.append("🔥 TOP")
    tag_line = "  ".join(tags) + "\n" if tags else ""

    # Stock check / flash expiry
    flash_end = ""
    if p["is_flash"] and p["flash_until"]:
        flash_end = f"\n⏳ Flash Sale tugaydi: <b>{p['flash_until'][:16]}</b>"

    txt  = f"{tag_line}<b>{p['name']}</b>\n"
    txt += f"📂 Bo'lim: {p['cat_name']}\n"
    if p["description"]: txt += f"\n{p['description']}\n"
    txt += f"\n💰 Narx: <b>{fmt(pr)} so'm</b>"
    if p["old_price"] and p["old_price"] > pr:
        txt += f"  <s>{fmt(p['old_price'])} so'm</s>"
    txt += f"\n📦 Ombor: {'✅ Mavjud' if p['stock'] > 0 else '❌ Tugagan'} ({p['stock']} ta){flash_end}"

    # Reviews
    avg = await q1("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE product_id=?", (pid,))
    if avg and avg["cnt"]:
        txt += f"\n⭐ Baho: {avg['avg']:.1f}/5  ({avg['cnt']} sharh)"

    kb = product_detail_ik(pid, qty)
    try:
        if p["photo_id"]:
            await call.message.delete()
            await bot.send_photo(call.from_user.id, p["photo_id"], caption=txt, reply_markup=kb)
        else:
            await call.message.edit_text(txt, reply_markup=kb)
    except Exception:
        try:
            if p["photo_id"]:
                await bot.send_photo(call.from_user.id, p["photo_id"], caption=txt, reply_markup=kb)
            else:
                await call.message.answer(txt, reply_markup=kb)
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data == "back_prods")
async def back_to_prods(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("current_cat", 0)
    page   = data.get("current_page", 0)
    if cat_id:
        await _show_products(call, state, cat_id, page)
    else:
        await back_to_cats(call, state)


# Cart add/inc/dec
async def _cart_update(call: CallbackQuery, pid: int, delta: int):
    uid = call.from_user.id
    if delta > 0:
        p = await q1("SELECT stock FROM products WHERE id=?", (pid,))
        ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
        cur_qty = ci["quantity"] if ci else 0
        if p and cur_qty + delta > p["stock"] and p["stock"] > 0:
            await call.answer(f"❌ Omborda faqat {p['stock']} ta bor!", show_alert=True)
            return
        await exe(
            "INSERT INTO cart(user_id,product_id,quantity) VALUES(?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=quantity+?",
            (uid, pid, delta, delta)
        )
    else:
        ci = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
        if ci:
            if ci["quantity"] + delta <= 0:
                await exe("DELETE FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
            else:
                await exe("UPDATE cart SET quantity=quantity+? WHERE user_id=? AND product_id=?", (delta, uid, pid))

    ci2 = await q1("SELECT quantity FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
    qty = ci2["quantity"] if ci2 else 0

    p = await q1("SELECT * FROM products WHERE id=?", (pid,))
    pr   = p["flash_price"] if p["is_flash"] and p["flash_price"] else p["price"]
    txt  = f"{'⚡ ' if p['is_flash'] and p['flash_price'] else ''}<b>{p['name']}</b>\n"
    txt += f"💰 <b>{fmt(pr)} so'm</b>\n"
    txt += f"📦 Ombor: {p['stock']} ta\n"
    if qty: txt += f"\n🛒 Savatchada: {qty} ta"

    try:
        await call.message.edit_caption(txt, reply_markup=product_detail_ik(pid, qty))
    except Exception:
        try:
            await call.message.edit_text(txt, reply_markup=product_detail_ik(pid, qty))
        except Exception:
            pass
    if delta > 0:
        await call.answer(f"✅ Savatga qo'shildi ({qty} ta)")
    else:
        await call.answer("♻️ Yangilandi")


@router.callback_query(F.data.startswith("cadd_"))
async def cart_add(call: CallbackQuery):
    await _cart_update(call, int(call.data[5:]), 1)

@router.callback_query(F.data.startswith("cinc_"))
async def cart_inc(call: CallbackQuery):
    await _cart_update(call, int(call.data[5:]), 1)

@router.callback_query(F.data.startswith("cdec_"))
async def cart_dec(call: CallbackQuery):
    await _cart_update(call, int(call.data[5:]), -1)

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ─── SAVATCHA ─────────────────────────────────────────────────────────────────
@router.message(F.text == "🛒 Savatcha")
@router.callback_query(F.data == "view_cart")
async def cmd_cart(event, state: FSMContext = None):
    if isinstance(event, CallbackQuery):
        uid = event.from_user.id
        send = event.message.answer
    else:
        uid = event.from_user.id
        send = event.answer

    items = await get_cart(uid)
    if not items:
        if isinstance(event, CallbackQuery):
            await event.answer("🛒 Savatcha bo'sh", show_alert=True)
        else:
            await send("🛒 Savatingiz bo'sh. Avval mahsulot tanlang!")
        return

    txt = await fmt_cart(uid)
    kb  = cart_ik(items)
    await send(txt, reply_markup=kb)
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data == "cart_clear")
async def cart_clear(call: CallbackQuery):
    await clear_cart(call.from_user.id)
    await call.message.edit_text("🗑 Savatcha tozalandi.")
    await call.answer("✅ Savatcha tozalandi")


# ─── QIDIRUV ──────────────────────────────────────────────────────────────────
@router.message(F.text == "🔍 Qidiruv")
async def cmd_search(msg: Message, state: FSMContext):
    await msg.answer("🔍 Qidirish uchun mahsulot nomini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(Shop.search)

@router.message(Shop.search)
async def do_search(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bosh menyu:", reply_markup=await get_main_kb(msg.from_user.id))
        return
    q  = f"%{msg.text.strip()}%"
    ps = await qall(
        "SELECT * FROM products WHERE is_active=1 AND (name LIKE ? OR description LIKE ?) LIMIT 20",
        (q, q)
    )
    if not ps:
        await msg.answer("❌ Hech narsa topilmadi. Qaytadan kiriting yoki ❌ Bekor qilish.")
        return
    await state.clear()
    txt = f"🔍 <b>Qidiruv natijalari ({len(ps)} ta):</b>\n\n"
    rows = []
    for p in ps:
        pr  = p["flash_price"] if p["is_flash"] and p["flash_price"] else p["price"]
        st  = "✅" if p["stock"] > 0 else "❌"
        rows.append([InlineKeyboardButton(text=f"{st} {p['name']} — {fmt(pr)} so'm", callback_data=f"prod_{p['id']}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await msg.answer(txt, reply_markup=await get_main_kb(msg.from_user.id))
    await msg.answer("Quyidagi mahsulotlardan birini tanlang:", reply_markup=kb)


# ─── FLASH SALE ───────────────────────────────────────────────────────────────
@router.message(F.text == "⚡ Flash Sale")
async def cmd_flash(msg: Message, state: FSMContext):
    now = now_str()
    ps  = await qall(
        "SELECT * FROM products WHERE is_active=1 AND is_flash=1 AND flash_price>0 AND (flash_until='' OR flash_until>?) ORDER BY sold_count DESC",
        (now,)
    )
    if not ps:
        await msg.answer("⚡ Hozirda Flash Sale yo'q.")
        return
    rows = []
    for p in ps:
        disc = p["price"] - p["flash_price"]
        rows.append([InlineKeyboardButton(
            text=f"⚡ {p['name']} — {fmt(p['flash_price'])} so'm  (-{fmt(disc)} so'm)",
            callback_data=f"prod_{p['id']}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await msg.answer("⚡ <b>Flash Sale mahsulotlar:</b>", reply_markup=kb)


# ─── TOP ──────────────────────────────────────────────────────────────────────
@router.message(F.text == "⭐ TOP mahsulotlar")
async def cmd_top(msg: Message, state: FSMContext):
    ps = await qall(
        "SELECT * FROM products WHERE is_active=1 AND is_top=1 ORDER BY sold_count DESC LIMIT 20"
    )
    if not ps:
        ps = await qall(
            "SELECT * FROM products WHERE is_active=1 ORDER BY sold_count DESC LIMIT 10"
        )
    if not ps:
        await msg.answer("📦 Mahsulotlar hozircha yo'q.")
        return
    rows = []
    for i, p in enumerate(ps, 1):
        pr = p["flash_price"] if p["is_flash"] and p["flash_price"] else p["price"]
        rows.append([InlineKeyboardButton(
            text=f"{i}. {'⚡' if p['is_flash'] and p['flash_price'] else '⭐'} {p['name']} — {fmt(pr)} so'm",
            callback_data=f"prod_{p['id']}"
        )])
    await msg.answer("⭐ <b>TOP mahsulotlar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ─── CHECKOUT ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "checkout_start")
async def checkout_start(call: CallbackQuery, state: FSMContext):
    uid   = call.from_user.id
    items = await get_cart(uid)
    if not items:
        await call.answer("🛒 Savatcha bo'sh", show_alert=True); return

    open_ok, msg_oc = await is_open()
    if not open_ok:
        await call.answer(msg_oc, show_alert=True); return

    total = await cart_total(uid)
    min_o = int(await setting("min_order") or 0)
    if total < min_o:
        await call.answer(f"❌ Minimal buyurtma: {fmt(min_o)} so'm", show_alert=True); return

    await state.update_data(
        checkout_items=items,
        checkout_total=total,
        promo_code="",
        promo_discount=0,
        points_used=0,
        zone_id=0,
        delivery_fee=0,
        payment_method="cash",
        estimated_time="",
    )

    await call.message.answer(
        f"🛒 <b>Buyurtma berish</b>\n\nJami summa: <b>{fmt(total)} so'm</b>\n\n"
        f"1️⃣ Promo kodingiz bormi?\n(Yo'q bo'lsa ⏭ bosing)",
        reply_markup=ik([("⏭ Promo kodsiz", "skip_promo"), ("❌ Bekor", "cancel_checkout")])
    )
    await state.set_state(Checkout.promo)
    await call.answer()


@router.message(Checkout.promo)
async def checkout_promo_text(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await _cancel_checkout(msg, state); return
    code = msg.text.strip().upper()
    data = await state.get_data()
    items = data.get("checkout_items", [])
    total = data.get("checkout_total", 0)
    cat_ids = list({i["product_id"] for i in items})  # just using product_id; ideally category_ids

    # get category ids from items
    prod_ids = [str(i["product_id"]) for i in items]
    if prod_ids:
        ph = ",".join(["?"]*len(prod_ids))
        cats_r = await qall(f"SELECT DISTINCT category_id FROM products WHERE id IN ({ph})", prod_ids)
        cat_ids = [c["category_id"] for c in cats_r]

    disc, err = await apply_promo(code, cat_ids, total)
    if err:
        await msg.answer(err + "\n\nQaytadan kiring yoki ⏭ o'tkazib yuboring:",
                         reply_markup=ik([("⏭ O'tkazib yuborish", "skip_promo")]))
        return

    await state.update_data(promo_code=code, promo_discount=disc)
    await exe("UPDATE promos SET used_count=used_count+1 WHERE code=?", (code,))
    await _next_points(msg, state, f"✅ Promo kod qabul qilindi! Chegirma: <b>{fmt(disc)} so'm</b>")


@router.callback_query(F.data == "skip_promo")
async def skip_promo(call: CallbackQuery, state: FSMContext):
    await call.message.answer("⏭ Promo kod o'tkazib yuborildi.")
    await _next_points(call.message, state)
    await call.answer()


async def _next_points(msg, state, prefix=""):
    data = await state.get_data()
    user = await get_user(msg.chat.id)
    if not user:
        return
    pts  = user["points"]
    if pts >= 100:
        max_disc = pts * POINT_VALUE_SUM
        await msg.answer(
            f"{prefix}\n\n2️⃣ 💎 Sizda <b>{pts} ball</b> bor ({fmt(max_disc)} so'm chegirma)\n"
            f"Ballarni ishlatishni xohlaysizmi?",
            reply_markup=ik(
                [(f"💎 {pts} ball ishlatish", "use_points")],
                [("⏭ Ballarsiz davom", "skip_points")],
            )
        )
    else:
        await msg.answer(f"{prefix}\n\n(Balansingizda {pts} ball — 100 ta bo'lganda ishlatish mumkin)")
        await _next_phone(msg, state)
    await state.set_state(Checkout.points)


@router.callback_query(F.data == "use_points")
async def use_points(call: CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    pts  = user["points"] if user else 0
    await state.update_data(points_used=pts)
    await call.message.answer(f"💎 <b>{pts} ball</b> ishlatiladi ({fmt(pts * POINT_VALUE_SUM)} so'm chegirma).")
    await _next_phone(call.message, state)
    await call.answer("✅")

@router.callback_query(F.data == "skip_points")
async def skip_points(call: CallbackQuery, state: FSMContext):
    await _next_phone(call.message, state)
    await call.answer()


async def _next_phone(msg, state):
    user = await get_user(msg.chat.id)
    if user and user.get("phone"):
        await msg.answer(
            f"3️⃣ Telefon raqam:\n\nSaqlangan raqam: <b>{user['phone']}</b>",
            reply_markup=ik(
                [(f"✅ {user['phone']} ishlatish", "use_saved_phone")],
                [("📱 Boshqa raqam", "enter_phone")],
            )
        )
    else:
        await msg.answer("3️⃣ Telefon raqamingizni yuboring:", reply_markup=phone_request_kb())
    await state.set_state(Checkout.phone)


@router.callback_query(F.data == "use_saved_phone")
async def use_saved_phone(call: CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    await state.update_data(checkout_phone=user["phone"])
    await call.message.answer(f"✅ Telefon: <b>{user['phone']}</b>")
    await _next_address(call.message, state)
    await call.answer()

@router.callback_query(F.data == "enter_phone")
async def enter_phone(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📱 Telefon raqamingizni yuboring:", reply_markup=phone_request_kb())
    await call.answer()

@router.message(Checkout.phone, F.contact)
async def checkout_phone_contact(msg: Message, state: FSMContext):
    ph = msg.contact.phone_number
    if not ph.startswith("+"): ph = "+" + ph
    await state.update_data(checkout_phone=ph)
    await msg.answer(f"✅ Telefon: <b>{ph}</b>")
    await _next_address(msg, state)

@router.message(Checkout.phone, F.text)
async def checkout_phone_text(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await _cancel_checkout(msg, state); return
    ph = msg.text.strip()
    if not ph.startswith("+"): ph = "+998" + ph.lstrip("0")
    await state.update_data(checkout_phone=ph)
    await msg.answer(f"✅ Telefon: <b>{ph}</b>")
    await _next_address(msg, state)


async def _next_address(msg, state):
    await msg.answer(
        "4️⃣ Yetkazib berish manzilingizni kiriting:\n(Ko'cha, uy raqami, mo'ljal)",
        reply_markup=CANCEL_KB,
    )
    await state.set_state(Checkout.address)

@router.message(Checkout.address)
async def checkout_address(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await _cancel_checkout(msg, state); return
    addr = msg.text.strip()
    if len(addr) < 5:
        await msg.answer("❌ Manzil juda qisqa. To'liqroq kiriting:"); return
    await state.update_data(checkout_address=addr)

    zones = await qall("SELECT * FROM delivery_zones WHERE is_active=1 ORDER BY delivery_fee")
    if zones:
        await msg.answer(
            f"5️⃣ Yetkazish zonasini tanlang:\n📍 Manzil: {addr}",
            reply_markup=zones_ik(zones)
        )
        await state.set_state(Checkout.zone)
    else:
        await state.update_data(zone_id=0, delivery_fee=0, estimated_time=await setting("default_delivery_time") or "30-60 daqiqa")
        await _next_payment(msg, state)


@router.callback_query(F.data.startswith("zone_"))
async def checkout_zone(call: CallbackQuery, state: FSMContext):
    zone_id = int(call.data[5:])
    zone    = await q1("SELECT * FROM delivery_zones WHERE id=?", (zone_id,))
    if not zone:
        await call.answer("Zona topilmadi", show_alert=True); return

    data  = await state.get_data()
    total = data.get("checkout_total", 0)
    if total < zone["min_order"]:
        await call.answer(
            f"❌ Bu zona uchun minimal buyurtma: {fmt(zone['min_order'])} so'm",
            show_alert=True
        )
        return

    await state.update_data(zone_id=zone_id, delivery_fee=zone["delivery_fee"], estimated_time=zone["delivery_time"])
    await call.message.answer(
        f"✅ Zona: <b>{zone['name']}</b>\n🚚 Yetkazish narxi: <b>{fmt(zone['delivery_fee'])} so'm</b>\n⏱ Taxminiy vaqt: <b>{zone['delivery_time']}</b>"
    )
    await _next_payment(call.message, state)
    await call.answer()


async def _next_payment(msg, state):
    await msg.answer("6️⃣ To'lov usulini tanlang:", reply_markup=payments_ik())
    await state.set_state(Checkout.payment)


@router.callback_query(F.data.startswith("pay_"))
async def checkout_payment(call: CallbackQuery, state: FSMContext):
    method  = call.data[4:]
    label   = PAYMENT_LABELS.get(method, method)
    await state.update_data(payment_method=method)

    data    = await state.get_data()
    total   = data.get("checkout_total", 0)
    d_fee   = data.get("delivery_fee", 0)
    disc    = data.get("promo_discount", 0)
    pts     = data.get("points_used", 0)
    pts_d   = pts * POINT_VALUE_SUM
    final   = max(0, total + d_fee - disc - pts_d)
    addr    = data.get("checkout_address", "—")
    phone   = data.get("checkout_phone", "—")
    zone_id = data.get("zone_id", 0)
    etime   = data.get("estimated_time", "")
    promo   = data.get("promo_code", "")

    zone_nm = ""
    if zone_id:
        z = await q1("SELECT name FROM delivery_zones WHERE id=?", (zone_id,))
        if z: zone_nm = z["name"]

    txt  = "✅ <b>Buyurtmani tasdiqlang:</b>\n\n"
    txt += f"📍 Manzil: {addr}\n"
    txt += f"📱 Telefon: {phone}\n"
    if zone_nm: txt += f"🗺 Zona: {zone_nm}\n"
    if etime:   txt += f"⏱ Taxminiy yetkazish: <b>{etime}</b>\n"
    txt += f"\n💰 Mahsulotlar: {fmt(total)} so'm\n"
    txt += f"🚚 Yetkazish: {fmt(d_fee)} so'm\n"
    if disc:   txt += f"🎟 Promo: -{fmt(disc)} so'm\n"
    if pts_d:  txt += f"💎 Ballar: -{fmt(pts_d)} so'm\n"
    txt += f"\n💵 <b>Jami: {fmt(final)} so'm</b>\n"
    txt += f"💳 To'lov: {label}\n"
    if promo: txt += f"🎟 Promo kod: {promo}\n"

    await call.message.answer(txt, reply_markup=ik([("✅ Tasdiqlash", "confirm_order"), ("❌ Bekor", "cancel_checkout")]))
    await state.set_state(Checkout.confirm)
    await call.answer()


@router.callback_query(F.data == "confirm_order")
async def confirm_order(call: CallbackQuery, state: FSMContext):
    uid  = call.from_user.id
    data = await state.get_data()

    total   = data.get("checkout_total", 0)
    d_fee   = data.get("delivery_fee", 0)
    disc    = data.get("promo_discount", 0)
    pts_u   = data.get("points_used", 0)
    zone_id = data.get("zone_id", 0)
    method  = data.get("payment_method", "cash")
    phone   = data.get("checkout_phone", "")
    addr    = data.get("checkout_address", "")
    etime   = data.get("estimated_time", "")
    promo   = data.get("promo_code", "")
    items   = await get_cart(uid)

    if not items:
        await call.answer("Savatcha bo'sh", show_alert=True)
        await state.clear()
        return

    pts_earned = total // POINTS_PER_SUM

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO orders(user_id,zone_id,status,total_amount,delivery_fee,discount,
               points_used,points_earned,promo_code,payment_method,phone,address,estimated_time)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uid, zone_id, "new", total, d_fee, disc, pts_u, pts_earned,
             promo, method, phone, addr, etime)
        )
        order_id = cur.lastrowid
        for it in items:
            pr = it["flash_price"] if it["is_flash"] and it["flash_price"] else it["price"]
            await db.execute(
                "INSERT INTO order_items(order_id,product_id,product_name,quantity,price) VALUES(?,?,?,?,?)",
                (order_id, it["product_id"], it["name"], it["quantity"], pr)
            )
            # reduce stock
            await db.execute("UPDATE products SET stock=stock-?, sold_count=sold_count+? WHERE id=?",
                             (it["quantity"], it["quantity"], it["product_id"]))
        # deduct points
        if pts_u > 0:
            await db.execute("UPDATE users SET points=points-? WHERE tg_id=?", (pts_u, uid))
        # credit earned points
        await db.execute("UPDATE users SET points=points+?, orders_count=orders_count+1, total_spent=total_spent+? WHERE tg_id=?",
                         (pts_earned, total, uid))

        # first order bonus
        u = await get_user(uid)
        if u and u["orders_count"] == 1:
            await db.execute("UPDATE users SET points=points+? WHERE tg_id=?", (FIRST_ORDER_POINTS, uid))

        await db.commit()

    await clear_cart(uid)
    await state.clear()

    # Notify user
    await call.message.answer(
        f"✅ <b>Buyurtma {oid(order_id)} qabul qilindi!</b>\n\n"
        f"⏱ Taxminiy yetkazish: <b>{etime or 'aniqlanadi'}</b>\n"
        f"💎 +{pts_earned} ball oldiniz!\n\n"
        f"Buyurtma holati uchun: 📦 Buyurtmalarim",
        reply_markup=await get_main_kb(uid),
    )

    # Notify admins
    order_txt = await fmt_order(order_id)
    await notify_admins(f"🔔 <b>Yangi buyurtma {oid(order_id)}!</b>\n\n{order_txt}")
    await call.answer("✅")


@router.callback_query(F.data == "cancel_checkout")
async def cancel_checkout_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Buyurtma bekor qilindi.", reply_markup=await get_main_kb(call.from_user.id))
    await call.answer()

async def _cancel_checkout(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Buyurtma bekor qilindi.", reply_markup=await get_main_kb(msg.from_user.id))


# ─── BUYURTMALARIM ────────────────────────────────────────────────────────────
@router.message(F.text == "📦 Buyurtmalarim")
async def cmd_my_orders(msg: Message, state: FSMContext):
    uid    = msg.from_user.id
    orders = await qall("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))
    if not orders:
        await msg.answer("📦 Hali buyurtmalaringiz yo'q.")
        return
    kb = orders_list_ik(orders, "userord")
    if kb:
        await msg.answer("📦 <b>Buyurtmalaringiz:</b>", reply_markup=kb)

@router.callback_query(F.data.startswith("userord_"))
async def view_user_order(call: CallbackQuery, state: FSMContext):
    oid_int = int(call.data.split("_")[1])
    o = await q1("SELECT * FROM orders WHERE id=?", (oid_int,))
    if not o or o["user_id"] != call.from_user.id:
        await call.answer("Topilmadi", show_alert=True); return

    txt = await fmt_order(oid_int)
    # Review button if delivered
    rows = []
    if o["status"] == "delivered":
        rows.append([InlineKeyboardButton(text="⭐ Sharh qoldirish", callback_data=f"review_order_{oid_int}")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="my_orders_back")])
    await call.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data == "my_orders_back")
async def my_orders_back(call: CallbackQuery, state: FSMContext):
    uid    = call.from_user.id
    orders = await qall("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))
    kb     = orders_list_ik(orders, "userord")
    if kb:
        await call.message.edit_text("📦 <b>Buyurtmalaringiz:</b>", reply_markup=kb)
    await call.answer()


# ─── PROFIL ───────────────────────────────────────────────────────────────────
@router.message(F.text == "👤 Profilim")
async def cmd_profile(msg: Message, state: FSMContext):
    uid  = msg.from_user.id
    user = await get_user(uid)
    if not user:
        await msg.answer("Iltimos /start bilan boshlang."); return

    pts   = user["points"]
    pts_v = pts * POINT_VALUE_SUM
    txt   = (
        f"👤 <b>Profilingiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Ism: {user['name']}\n"
        f"📱 Telefon: {user.get('phone') or '—'}\n"
        f"📅 Ro'yxatdan: {user['created_at'][:10]}\n\n"
        f"📦 Buyurtmalar: {user['orders_count']} ta\n"
        f"💰 Umumiy xarid: {fmt(user['total_spent'])} so'm\n\n"
        f"💎 Ballar: <b>{pts}</b>  ({fmt(pts_v)} so'm qiymatida)\n"
        f"🔗 Referal kod: <code>{user['ref_code']}</code>"
    )
    await msg.answer(txt, reply_markup=ik(
        [("✏️ Ismni o'zgartirish", "edit_name")],
        [("📱 Telefon o'zgartirish", "edit_phone")],
        [("📊 Ball tarixi", "point_history")],
    ))


@router.callback_query(F.data == "point_history")
async def point_history(call: CallbackQuery, state: FSMContext):
    logs = await qall(
        "SELECT * FROM point_log WHERE user_id=? ORDER BY id DESC LIMIT 15",
        (call.from_user.id,)
    )
    if not logs:
        await call.answer("Ball tarixi bo'sh", show_alert=True); return
    txt = "💎 <b>Ball tarixi:</b>\n\n"
    for l in logs:
        sign = "+" if l["amount"] > 0 else ""
        txt += f"{sign}{l['amount']} ball — {l['reason']} — {l['created_at'][:16]}\n"
    await call.message.edit_text(txt, reply_markup=ik([("🔙", "back_profile")]))
    await call.answer()

@router.callback_query(F.data == "back_profile")
async def back_profile(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await cmd_profile(call.message, state)
    await call.answer()


# ─── BALLARIM ─────────────────────────────────────────────────────────────────
@router.message(F.text == "💎 Ballarim")
async def cmd_points(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    if not user:
        await msg.answer("Iltimos /start bilan boshlang."); return
    pts = user["points"]
    txt = (
        f"💎 <b>Ball tizimi</b>\n\n"
        f"Sizda: <b>{pts} ball</b>\n"
        f"Qiymati: <b>{fmt(pts * POINT_VALUE_SUM)} so'm</b>\n\n"
        f"📊 <b>Qoidalar:</b>\n"
        f"• Har {fmt(POINTS_PER_SUM)} so'mlik xariddan → 1 ball\n"
        f"• 100 ball = {fmt(100 * POINT_VALUE_SUM)} so'm chegirma\n"
        f"• Referal uchun → {REFERRAL_POINTS} ball\n"
        f"• Birinchi buyurtma → {FIRST_ORDER_POINTS} ball\n\n"
        f"Ballar keyingi buyurtmada avtomatik ishlatiladi (100 dan oshganda)."
    )
    await msg.answer(txt)


# ─── REFERAL ──────────────────────────────────────────────────────────────────
@router.message(F.text == "🤝 Referal")
async def cmd_referral(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    if not user: return
    rc   = user["ref_code"]
    link = f"https://t.me/{(await bot.get_me()).username}?start={rc}"
    referrals = await qall("SELECT name FROM users WHERE ref_by=?", (msg.from_user.id,))
    txt = (
        f"🤝 <b>Referal dasturi</b>\n\n"
        f"Do'stlaringizni taklif qiling va <b>{REFERRAL_POINTS} ball</b> oling!\n\n"
        f"🔗 Sizning havolangiz:\n<code>{link}</code>\n\n"
        f"📊 Jami referallar: <b>{len(referrals)}</b> ta\n"
        f"💎 Jami topilgan: <b>{len(referrals) * REFERRAL_POINTS}</b> ball\n\n"
        f"<i>Havola orqali ro'yxatdan o'tgan har bir do'st uchun {REFERRAL_POINTS} ball!</i>"
    )
    await msg.answer(txt)


# ─── SHARH (REVIEW) ───────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("review_order_"))
async def start_review(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[2])
    o = await q1("SELECT * FROM orders WHERE id=? AND status='delivered'", (order_id,))
    if not o or o["user_id"] != call.from_user.id:
        await call.answer("Faqat yetkazilgan buyurtmalar uchun sharh qoldiriladi", show_alert=True)
        return
    items = await qall("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    if not items:
        await call.answer("Mahsulot topilmadi", show_alert=True); return

    await state.update_data(review_order_id=order_id, review_items=items, review_idx=0)
    await _ask_review(call.message, state, 0, items)
    await call.answer()

async def _ask_review(msg, state, idx, items):
    it = items[idx]
    await msg.answer(
        f"⭐ <b>{it['product_name']}</b> ga baho bering (1-5):",
        reply_markup=ik(
            [("⭐1","rv_1"),("⭐2","rv_2"),("⭐3","rv_3")],
            [("⭐4","rv_4"),("⭐5","rv_5")],
            [("⏭ O'tkazib yuborish","rv_skip")],
        )
    )
    await state.set_state(ReviewSt.rating)

@router.callback_query(F.data.startswith("rv_"))
async def review_rating(call: CallbackQuery, state: FSMContext):
    action = call.data[3:]
    if action == "skip":
        await _next_review(call.message, state)
        await call.answer(); return
    rating = int(action)
    await state.update_data(current_rating=rating)
    await call.message.answer(
        f"{stars(rating)} Izoh qoldiring (ixtiyoriy):",
        reply_markup=ik([("⏭ Izoхsiz", "rv_nocomment")])
    )
    await state.set_state(ReviewSt.comment)
    await call.answer()

@router.message(ReviewSt.comment)
async def review_comment(msg: Message, state: FSMContext):
    await _save_review(msg, state, msg.text)

@router.callback_query(F.data == "rv_nocomment")
async def review_no_comment(call: CallbackQuery, state: FSMContext):
    await _save_review(call.message, state, "")
    await call.answer()

async def _save_review(msg, state, comment):
    data   = await state.get_data()
    items  = data.get("review_items", [])
    idx    = data.get("review_idx", 0)
    oid_i  = data.get("review_order_id", 0)
    rating = data.get("current_rating", 5)
    uid    = msg.chat.id

    if idx < len(items):
        it = items[idx]
        existing = await q1("SELECT id FROM reviews WHERE user_id=? AND order_id=? AND product_id=?",
                           (uid, oid_i, it["product_id"]))
        if not existing:
            await exe(
                "INSERT INTO reviews(user_id,order_id,product_id,rating,comment) VALUES(?,?,?,?,?)",
                (uid, oid_i, it["product_id"], rating, comment or "")
            )
    await _next_review(msg, state)

async def _next_review(msg, state):
    data  = await state.get_data()
    items = data.get("review_items", [])
    idx   = data.get("review_idx", 0) + 1
    await state.update_data(review_idx=idx)
    if idx < len(items):
        await _ask_review(msg, state, idx, items)
    else:
        await state.clear()
        await msg.answer("✅ Sharhlaringiz uchun rahmat! 🙏")


# ─── SUPPORT ──────────────────────────────────────────────────────────────────
@router.message(F.text == "🆘 Yordam")
async def cmd_support(msg: Message, state: FSMContext):
    txt = (
        "🆘 <b>Yordam markazi</b>\n\n"
        "📞 Telefon: " + (await setting("phone_support") or "+998 90 000 00 00") + "\n\n"
        "Muammoni yozing va biz tez orada javob beramiz:"
    )
    await msg.answer(txt, reply_markup=ik(
        [("✉️ Xabar yuborish", "support_new")],
        [("📋 Mening ticketlarim", "support_my")],
    ))

@router.callback_query(F.data == "support_new")
async def support_new(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✉️ Muammoni yozing:", reply_markup=CANCEL_KB)
    await state.set_state(SupportSt.subject)
    await call.answer()

@router.message(SupportSt.subject)
async def support_subject(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=await get_main_kb(msg.from_user.id)); return

    uid = msg.from_user.id
    user = await get_user(uid)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO support_tickets(user_id,subject) VALUES(?,?)",
            (uid, msg.text[:200])
        )
        tid = cur.lastrowid
        await db.execute(
            "INSERT INTO support_messages(ticket_id,sender_id,is_admin,message) VALUES(?,?,0,?)",
            (tid, uid, msg.text)
        )
        await db.commit()

    await state.clear()
    await msg.answer(
        f"✅ Ticket #{tid} yaratildi!\nAdmin tez orada javob beradi. Rahmat!",
        reply_markup=await get_main_kb(uid)
    )
    name = user["name"] if user else "Noma'lum"
    await notify_admins(
        f"🆘 <b>Yangi support ticket #{tid}</b>\n👤 {name} (ID: {uid})\n📝 {msg.text[:300]}"
    )

@router.callback_query(F.data == "support_my")
async def support_my(call: CallbackQuery, state: FSMContext):
    uid     = call.from_user.id
    tickets = await qall("SELECT * FROM support_tickets WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    if not tickets:
        await call.answer("Sizda hali ticket yo'q", show_alert=True); return
    rows = []
    for t in tickets:
        st = "🟢" if t["status"] == "open" else ("🔵" if t["status"] == "in_progress" else "⚫")
        rows.append([InlineKeyboardButton(
            text=f"{st} #{t['id']} — {t['subject'][:30]}",
            callback_data=f"sticket_{t['id']}"
        )])
    await call.message.edit_text("📋 <b>Ticketlaringiz:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("sticket_"))
async def view_ticket(call: CallbackQuery, state: FSMContext):
    tid  = int(call.data[8:])
    msgs = await qall("SELECT * FROM support_messages WHERE ticket_id=? ORDER BY id", (tid,))
    txt  = f"📋 <b>Ticket #{tid}</b>\n\n"
    for m in msgs:
        who = "👤 Siz" if not m["is_admin"] else "👨‍💼 Admin"
        txt += f"{who} ({m['created_at'][:16]}):\n{m['message']}\n\n"
    await call.message.edit_text(txt, reply_markup=ik([("🔙", "support_my")]))
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  ═══════════════════  ADMIN HANDLERS  ═══════════════════
# ══════════════════════════════════════════════════════════════════════════════

async def check_admin(msg_or_call):
    uid = msg_or_call.from_user.id if isinstance(msg_or_call, Message) else msg_or_call.from_user.id
    return await is_admin(uid)


@router.message(F.text == "⚙️ Admin Panel")
async def cmd_admin(msg: Message, state: FSMContext):
    if not await check_admin(msg):
        await msg.answer("❌ Ruxsat yo'q."); return
    await state.clear()
    op, _ = await is_open()
    cnt   = (await q1("SELECT COUNT(*) as n FROM orders WHERE status='new'"))["n"]
    await msg.answer(
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"🟢 Do'kon: {'Ochiq' if op else '🔴 Yopiq'}\n"
        f"🆕 Yangi buyurtmalar: {cnt} ta",
        reply_markup=admin_kb()
    )


# ─── KATEGORIYALAR ────────────────────────────────────────────────────────────
@router.message(F.text == "📂 Bo'limlar")
async def admin_cats(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    cats = await qall("SELECT * FROM categories ORDER BY sort_order,id")
    rows = []
    for c in cats:
        st = "✅" if c["is_active"] else "❌"
        rows.append([
            InlineKeyboardButton(text=f"{st} {c['emoji']} {c['name']}", callback_data=f"acat_{c['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Yangi bo'lim", callback_data="acat_new")])
    await msg.answer("📂 <b>Bo'limlar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "acat_new")
async def admin_cat_new(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📂 Yangi bo'lim nomini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.cat_name)
    await call.answer()

@router.message(AdminSt.cat_name)
async def admin_cat_name(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.update_data(cat_name=msg.text.strip())
    await msg.answer("Emoji kiriting (masalan: 🍕) yoki ⏭ bosing:", reply_markup=ik([("⏭ O'tkazib yuborish","skip_emoji")]))
    await state.set_state(AdminSt.cat_emoji)

@router.callback_query(F.data == "skip_emoji")
async def skip_emoji(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await exe("INSERT INTO categories(name,emoji) VALUES(?,?)", (data["cat_name"], "📦"))
    await state.clear()
    await call.message.answer("✅ Bo'lim qo'shildi!", reply_markup=admin_kb())
    await call.answer()

@router.message(AdminSt.cat_emoji)
async def admin_cat_emoji(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    data  = await state.get_data()
    emoji = msg.text.strip()[:4] or "📦"
    await exe("INSERT INTO categories(name,emoji) VALUES(?,?)", (data["cat_name"], emoji))
    await state.clear()
    await msg.answer("✅ Bo'lim qo'shildi!", reply_markup=admin_kb())

@router.callback_query(F.data.startswith("acat_"))
async def admin_cat_detail(call: CallbackQuery, state: FSMContext):
    cid = call.data[5:]
    if cid == "new": return
    c   = await q1("SELECT * FROM categories WHERE id=?", (int(cid),))
    if not c: await call.answer(); return
    st  = "✅ Faol" if c["is_active"] else "❌ Nofaol"
    await call.message.edit_text(
        f"{c['emoji']} <b>{c['name']}</b>\nHolat: {st}",
        reply_markup=ik(
            [(f"{'❌ O\'chirish' if c['is_active'] else '✅ Yoqish'}", f"acattoggle_{c['id']}")],
            [("✏️ Nomni o'zgartirish", f"acatedit_{c['id']}")],
            [("🗑 O'chirish", f"acatdel_{c['id']}")],
            [("🔙 Orqaga", "admin_cats_back")],
        )
    )
    await call.answer()

@router.callback_query(F.data.startswith("acattoggle_"))
async def admin_cat_toggle(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[11:])
    c   = await q1("SELECT is_active FROM categories WHERE id=?", (cid,))
    if c:
        await exe("UPDATE categories SET is_active=? WHERE id=?", (0 if c["is_active"] else 1, cid))
    await call.answer("✅ Holat o'zgartirildi")
    await admin_cat_detail(call, state)

@router.callback_query(F.data.startswith("acatdel_"))
async def admin_cat_del(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[8:])
    await exe("DELETE FROM categories WHERE id=?", (cid,))
    await call.message.edit_text("🗑 Bo'lim o'chirildi.")
    await call.answer()

@router.callback_query(F.data == "admin_cats_back")
async def admin_cats_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_cats(call.message, state)
    await call.answer()


# ─── MAHSULOTLAR ──────────────────────────────────────────────────────────────
@router.message(F.text == "📦 Mahsulotlar")
async def admin_prods(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    prods = await qall("""
        SELECT p.*, c.name as cat_name FROM products p
        LEFT JOIN categories c ON p.category_id=c.id
        ORDER BY p.id DESC LIMIT 50
    """)
    rows = []
    for p in prods:
        st = "✅" if p["is_active"] else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{st} {p['name']} — {fmt(p['price'])} so'm ({p['cat_name'] or '-'})",
            callback_data=f"aprod_{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Yangi mahsulot", callback_data="aprod_new")])
    await msg.answer(f"📦 <b>Mahsulotlar ({len(prods)} ta):</b>",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "aprod_new")
async def admin_prod_new(call: CallbackQuery, state: FSMContext):
    cats = await qall("SELECT * FROM categories WHERE is_active=1")
    if not cats:
        await call.answer("Avval bo'lim yarating!", show_alert=True); return
    rows = [[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"newpcat_{c['id']}")] for c in cats]
    await call.message.answer("📂 Bo'limni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await state.set_state(AdminSt.prod_cat)
    await call.answer()

@router.callback_query(F.data.startswith("newpcat_"), AdminSt.prod_cat)
async def admin_prod_cat(call: CallbackQuery, state: FSMContext):
    await state.update_data(new_cat_id=int(call.data[8:]))
    await call.message.answer("📝 Mahsulot nomini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.prod_name)
    await call.answer()

@router.message(AdminSt.prod_name)
async def admin_prod_name(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.update_data(new_name=msg.text.strip())
    await msg.answer("📄 Tavsif kiriting yoki ⏭:", reply_markup=ik([("⏭ O'tkazib yuborish","skip_desc")]))
    await state.set_state(AdminSt.prod_desc)

@router.callback_query(F.data == "skip_desc", AdminSt.prod_desc)
async def skip_desc(call: CallbackQuery, state: FSMContext):
    await state.update_data(new_desc="")
    await call.message.answer("💰 Narxini kiriting (so'mda):", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.prod_price)
    await call.answer()

@router.message(AdminSt.prod_desc)
async def admin_prod_desc(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.update_data(new_desc=msg.text.strip())
    await msg.answer("💰 Narxini kiriting (so'mda):")
    await state.set_state(AdminSt.prod_price)

@router.message(AdminSt.prod_price)
async def admin_prod_price(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Faqat raqam kiriting:"); return
    await state.update_data(new_price=int(msg.text.strip()))
    await msg.answer("📦 Ombor miqdorini kiriting:")
    await state.set_state(AdminSt.prod_stock)

@router.message(AdminSt.prod_stock)
async def admin_prod_stock(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Faqat raqam:"); return
    await state.update_data(new_stock=int(msg.text.strip()))
    await msg.answer("🖼 Rasmini yuboring yoki ⏭:", reply_markup=ik([("⏭ Rasmsiz","skip_photo")]))
    await state.set_state(AdminSt.prod_photo)

@router.callback_query(F.data == "skip_photo", AdminSt.prod_photo)
async def skip_photo(call: CallbackQuery, state: FSMContext):
    await _save_product(call.message, state, "")
    await call.answer()

@router.message(AdminSt.prod_photo, F.photo)
async def admin_prod_photo(msg: Message, state: FSMContext):
    photo_id = msg.photo[-1].file_id
    await _save_product(msg, state, photo_id)

@router.message(AdminSt.prod_photo, F.text)
async def admin_prod_photo_text(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return

async def _save_product(msg, state, photo_id):
    data = await state.get_data()
    await exe(
        "INSERT INTO products(category_id,name,description,price,stock,photo_id) VALUES(?,?,?,?,?,?)",
        (data["new_cat_id"], data["new_name"], data.get("new_desc",""),
         data["new_price"], data["new_stock"], photo_id)
    )
    await state.clear()
    await msg.answer(f"✅ Mahsulot <b>{data['new_name']}</b> qo'shildi!", reply_markup=admin_kb())


@router.callback_query(F.data.startswith("aprod_"))
async def admin_prod_detail(call: CallbackQuery, state: FSMContext):
    pid = call.data[6:]
    if pid == "new": return
    p = await q1("SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=?", (int(pid),))
    if not p:
        await call.answer(); return
    st   = "✅ Faol" if p["is_active"] else "❌ Nofaol"
    fl   = "⚡ Flash Sale" if p["is_flash"] and p["flash_price"] else ""
    top  = "🔥 TOP" if p["is_top"] else ""
    rev  = await q1("SELECT AVG(rating) as avg, COUNT(*) as n FROM reviews WHERE product_id=?", (int(pid),))
    txt  = (
        f"📦 <b>{p['name']}</b>\n"
        f"📂 {p['cat_name']} | {st} {fl} {top}\n"
        f"💰 Narx: {fmt(p['price'])} so'm\n"
        f"📦 Ombor: {p['stock']} ta | Sotilgan: {p['sold_count']} ta\n"
    )
    if rev and rev["n"]:
        txt += f"⭐ Baho: {rev['avg']:.1f} ({rev['n']} ta)\n"
    await call.message.edit_text(txt, reply_markup=ik(
        [("✅/❌ Faollik", f"aprodtog_{pid}"), ("🔥 TOP on/off", f"aprodtop_{pid}")],
        [("⚡ Flash Sale", f"aflash_{pid}"),   ("✏️ Tahrirlash", f"aprodit_{pid}")],
        [("🗑 O'chirish",  f"aproddel_{pid}"), ("🔙 Orqaga",     "admin_prods_back")],
    ))
    await call.answer()

@router.callback_query(F.data.startswith("aprodtog_"))
async def admin_prod_toggle(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    p   = await q1("SELECT is_active FROM products WHERE id=?", (pid,))
    if p:
        await exe("UPDATE products SET is_active=? WHERE id=?", (0 if p["is_active"] else 1, pid))
    await admin_prod_detail(call, state)
    await call.answer("✅")

@router.callback_query(F.data.startswith("aprodtop_"))
async def admin_prod_top(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    p   = await q1("SELECT is_top FROM products WHERE id=?", (pid,))
    if p:
        await exe("UPDATE products SET is_top=? WHERE id=?", (0 if p["is_top"] else 1, pid))
    await admin_prod_detail(call, state)
    await call.answer("✅")

@router.callback_query(F.data.startswith("aproddel_"))
async def admin_prod_del(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    await exe("DELETE FROM products WHERE id=?", (pid,))
    await call.message.edit_text("🗑 Mahsulot o'chirildi.")
    await call.answer()

@router.callback_query(F.data == "admin_prods_back")
async def admin_prods_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_prods(call.message, state)
    await call.answer()

@router.callback_query(F.data.startswith("aprodit_"))
async def admin_prod_edit(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[8:])
    await state.update_data(edit_prod_id=pid)
    await call.message.answer(
        "✏️ Qaysi maydonni tahrirlamoqchisiz?",
        reply_markup=ik(
            [("📝 Nom", f"pedit_name_{pid}"),   ("📄 Tavsif", f"pedit_desc_{pid}")],
            [("💰 Narx", f"pedit_price_{pid}"),  ("📦 Ombor",  f"pedit_stock_{pid}")],
            [("🖼 Rasm",  f"pedit_photo_{pid}")],
            [("🔙",       "admin_prods_back")],
        )
    )
    await call.answer()

@router.callback_query(F.data.startswith("pedit_"))
async def admin_prod_edit_field(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    field = parts[1]
    pid   = int(parts[2])
    field_labels = {
        "name": "yangi nom", "desc": "yangi tavsif",
        "price": "yangi narx (raqam)", "stock": "yangi ombor miqdori (raqam)",
        "photo": "rasm",
    }
    await state.update_data(edit_prod_id=pid, edit_prod_field=field)
    if field == "photo":
        await call.message.answer("🖼 Yangi rasmni yuboring:")
    else:
        await call.message.answer(f"✏️ {field_labels.get(field, field)} kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.prod_edit_val)
    await call.answer()

@router.message(AdminSt.prod_edit_val)
async def admin_prod_edit_val(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    data  = await state.get_data()
    pid   = data.get("edit_prod_id")
    field = data.get("edit_prod_field")
    col_map = {"name": "name", "desc": "description", "price": "price", "stock": "stock"}

    if field == "photo":
        if not msg.photo:
            await msg.answer("❌ Rasm yuboring:"); return
        val = msg.photo[-1].file_id
        await exe("UPDATE products SET photo_id=? WHERE id=?", (val, pid))
    elif field in ("price", "stock"):
        val_str = msg.text.strip()
        if not val_str.isdigit():
            await msg.answer("❌ Faqat raqam:"); return
        await exe(f"UPDATE products SET {col_map[field]}=? WHERE id=?", (int(val_str), pid))
    else:
        await exe(f"UPDATE products SET {col_map[field]}=? WHERE id=?", (msg.text.strip(), pid))

    await state.clear()
    await msg.answer("✅ Mahsulot yangilandi!", reply_markup=admin_kb())


# ─── FLASH SALE ───────────────────────────────────────────────────────────────
@router.message(F.text == "⚡ Flash Sale")
async def admin_flash_menu(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    prods = await qall("SELECT * FROM products WHERE is_flash=1 AND is_active=1")
    rows  = []
    for p in prods:
        rows.append([InlineKeyboardButton(
            text=f"⚡ {p['name']} — {fmt(p['flash_price'])} so'm (tugaydi: {p['flash_until'][:16]})",
            callback_data=f"flashend_{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Yangi Flash Sale", callback_data="flash_add")])
    await msg.answer(
        f"⚡ <b>Flash Sale ({len(prods)} ta mahsulot):</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@router.callback_query(F.data.startswith("flashend_"))
async def flash_end_sale(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    await exe("UPDATE products SET is_flash=0, flash_price=0, flash_until='' WHERE id=?", (pid,))
    await call.answer("✅ Flash Sale tugatildi")
    await call.message.delete()

@router.callback_query(F.data == "flash_add")
async def flash_add(call: CallbackQuery, state: FSMContext):
    await call.message.answer("⚡ Flash Sale mahsulot ID sini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.flash_pid)
    await call.answer()

@router.message(AdminSt.flash_pid)
async def flash_pid(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam kiriting:"); return
    pid = int(msg.text.strip())
    p   = await q1("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        await msg.answer("❌ Mahsulot topilmadi:"); return
    await state.update_data(flash_pid=pid)
    await msg.answer(f"💰 Flash narxini kiriting (hozirgi narx: {fmt(p['price'])} so'm):")
    await state.set_state(AdminSt.flash_price)

@router.message(AdminSt.flash_price)
async def flash_price_h(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam:"); return
    await state.update_data(flash_price_v=int(msg.text.strip()))
    await msg.answer("⏱ Necha soat davom etsin? (masalan: 24):")
    await state.set_state(AdminSt.flash_hours)

@router.message(AdminSt.flash_hours)
async def flash_hours_h(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam:"); return
    hours  = int(msg.text.strip())
    data   = await state.get_data()
    until  = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    await exe(
        "UPDATE products SET is_flash=1, flash_price=?, flash_until=? WHERE id=?",
        (data["flash_price_v"], until, data["flash_pid"])
    )
    await state.clear()
    p = await q1("SELECT name FROM products WHERE id=?", (data["flash_pid"],))
    await msg.answer(
        f"✅ Flash Sale aktiv!\n<b>{p['name']}</b> → {fmt(data['flash_price_v'])} so'm\nTugaydi: {until}",
        reply_markup=admin_kb()
    )


# ─── BUYURTMALAR (ADMIN) ──────────────────────────────────────────────────────
@router.message(F.text == "🛒 Buyurtmalar")
@router.callback_query(F.data == "admin_orders")
async def admin_orders(event, state: FSMContext = None):
    if isinstance(event, Message):
        if not await check_admin(event): return
        send = event.answer
    else:
        send = event.message.answer
        await event.answer()

    rows = await qall("SELECT * FROM orders ORDER BY id DESC LIMIT 30")
    if not rows:
        await send("📋 Hali buyurtmalar yo'q."); return

    kb = orders_list_ik(rows, "aord")
    if kb:
        await send("🛒 <b>Buyurtmalar (oxirgi 30):</b>", reply_markup=kb)
    else:
        await send("Buyurtmalar yo'q.")

@router.callback_query(F.data.startswith("aord_"))
async def admin_order_detail(call: CallbackQuery, state: FSMContext):
    oid_i = int(call.data[5:])
    o     = await q1("SELECT * FROM orders WHERE id=?", (oid_i,))
    if not o:
        await call.answer("Topilmadi", show_alert=True); return
    txt = await fmt_order(oid_i)
    await call.message.edit_text(txt, reply_markup=admin_order_ik(oid_i, o["status"]))
    await call.answer()

@router.callback_query(F.data.startswith("ostatus_"))
async def admin_order_status(call: CallbackQuery, state: FSMContext):
    _, oid_str, new_status = call.data.split("_", 2)
    oid_i = int(oid_str)
    o     = await q1("SELECT * FROM orders WHERE id=?", (oid_i,))
    if not o:
        await call.answer("Topilmadi", show_alert=True); return

    await exe(
        "UPDATE orders SET status=?, updated_at=? WHERE id=?",
        (new_status, now_str(), oid_i)
    )

    # Add points on delivery
    if new_status == "delivered":
        pts = o["points_earned"]
        if pts > 0:
            await add_points(o["user_id"], pts, f"Buyurtma #{oid_i}")

    label = ORDER_STATUSES.get(new_status, new_status)
    # Notify user
    try:
        msg_to_user = f"📦 <b>Buyurtma {oid(oid_i)}</b>\n\nHolat yangilandi: <b>{label}</b>"
        if new_status == "on_way" and o["estimated_time"]:
            msg_to_user += f"\n⏱ Taxminiy yetkazish: <b>{o['estimated_time']}</b>"
        if new_status == "delivered":
            msg_to_user += f"\n\n✅ Buyurtmangiz yetkazildi! Xarid uchun rahmat 🙏\n💎 +{o['points_earned']} ball oldiniz!"
        await bot.send_message(o["user_id"], msg_to_user)
    except Exception:
        pass

    await admin_order_detail(call, state)
    await call.answer(f"✅ Holat o'zgartirildi: {label}")

@router.callback_query(F.data.startswith("omsg_"))
async def admin_order_msg(call: CallbackQuery, state: FSMContext):
    oid_i = int(call.data[5:])
    await state.update_data(msg_order_id=oid_i)
    await call.message.answer("📩 Mijozga yuboriladigan xabarni kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.ord_msg)
    await call.answer()

@router.message(AdminSt.ord_msg)
async def admin_ord_msg_send(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    data  = await state.get_data()
    oid_i = data.get("msg_order_id")
    o     = await q1("SELECT user_id FROM orders WHERE id=?", (oid_i,))
    if o:
        try:
            await bot.send_message(o["user_id"], f"📦 <b>Buyurtma {oid(oid_i)}</b>\n\n{msg.text}")
            await msg.answer("✅ Xabar yuborildi!", reply_markup=admin_kb())
        except Exception:
            await msg.answer("❌ Xabar yuborib bo'lmadi.", reply_markup=admin_kb())
    await state.clear()

@router.callback_query(F.data.startswith("oassign_"))
async def admin_assign_courier(call: CallbackQuery, state: FSMContext):
    oid_i = int(call.data[8:])
    couriers = await qall("SELECT * FROM admins WHERE role='courier' AND is_active=1")
    if not couriers:
        await call.answer("❌ Hali kuryer yo'q. Avval kuryer qo'shing.", show_alert=True); return

    rows = [[InlineKeyboardButton(
        text=f"🚚 {c['name']} (ID: {c['tg_id']})",
        callback_data=f"docassign_{oid_i}_{c['tg_id']}"
    )] for c in couriers]
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"aord_{oid_i}")])
    await call.message.edit_text("🚚 Kuryer tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("docassign_"))
async def do_assign(call: CallbackQuery, state: FSMContext):
    _, oid_str, courier_id_str = call.data.split("_", 2)
    oid_i      = int(oid_str)
    courier_id = int(courier_id_str)

    await exe("UPDATE orders SET courier_id=?, status='on_way', updated_at=? WHERE id=?",
              (courier_id, now_str(), oid_i))
    o = await q1("SELECT * FROM orders WHERE id=?", (oid_i,))

    try:
        txt  = f"🚚 <b>Yangi buyurtma biriktirildi!</b>\n\n"
        txt += await fmt_order(oid_i)
        user = await get_user(o["user_id"]) if o else None
        map_link = ""
        if o and o["address"]:
            addr_enc = o["address"].replace(" ", "+")
            map_link = f"\n🗺 <a href='https://maps.google.com/?q={addr_enc}'>Xaritada ko'rish</a>"
        await bot.send_message(courier_id, txt + map_link)
    except Exception:
        pass

    try:
        await bot.send_message(o["user_id"] if o else 0,
            f"🚚 <b>Buyurtma {oid(oid_i)}</b>\n\nKuryer yo'lga chiqdi! Tez orada yetkaziladi.\n⏱ {o['estimated_time'] if o else ''}")
    except Exception:
        pass

    await call.answer("✅ Kuryer biriktirildi va yo'lga chiqdi!")
    await admin_order_detail(call, state)


# ─── KURYERLAR ────────────────────────────────────────────────────────────────
@router.message(F.text == "👥 Kuryerlar")
async def admin_couriers(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    cs   = await qall("SELECT * FROM admins WHERE role='courier'")
    rows = []
    for c in cs:
        st = "✅" if c["is_active"] else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{st} {c['name']} (ID: {c['tg_id']})",
            callback_data=f"acour_{c['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Kuryer qo'shish", callback_data="courier_add")])
    await msg.answer(f"👥 <b>Kuryerlar ({len(cs)} ta):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "courier_add")
async def courier_add(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🆔 Kuryer Telegram ID sini kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.courier_add)
    await call.answer()

@router.message(AdminSt.courier_add)
async def courier_add_id(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().lstrip("-").isdigit():
        await msg.answer("❌ Faqat raqam kiriting:"); return
    cid  = int(msg.text.strip())
    name = f"Kuryer {cid}"
    try:
        cu = await bot.get_chat(cid)
        name = cu.full_name or name
    except Exception:
        pass
    await exe("INSERT OR REPLACE INTO admins(tg_id,name,role,is_active) VALUES(?,?,'courier',1)", (cid, name))
    await state.clear()
    await msg.answer(f"✅ Kuryer <b>{name}</b> ({cid}) qo'shildi!", reply_markup=admin_kb())
    try:
        await bot.send_message(cid, "🚚 Siz kuryer sifatida qo'shildingiz! /start ni bosing.")
    except Exception:
        pass

@router.callback_query(F.data.startswith("acour_"))
async def admin_courier_detail(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[6:])
    c   = await q1("SELECT * FROM admins WHERE id=?", (cid,))
    if not c:
        await call.answer(); return
    st = "✅ Faol" if c["is_active"] else "❌ Nofaol"
    await call.message.edit_text(
        f"🚚 <b>{c['name']}</b>\nID: {c['tg_id']}\nHolat: {st}",
        reply_markup=ik(
            [(f"{'❌ Bloklash' if c['is_active'] else '✅ Faollashtirish'}", f"actogtog_{c['id']}")],
            [("🗑 O'chirish", f"acoursdel_{c['id']}")],
            [("🔙", "admin_couriers_back")],
        )
    )
    await call.answer()

@router.callback_query(F.data.startswith("actogtog_"))
async def admin_courier_toggle(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[9:])
    c   = await q1("SELECT is_active FROM admins WHERE id=?", (cid,))
    if c:
        await exe("UPDATE admins SET is_active=? WHERE id=?", (0 if c["is_active"] else 1, cid))
    await admin_courier_detail(call, state)
    await call.answer("✅")

@router.callback_query(F.data.startswith("acoursdel_"))
async def admin_courier_del(call: CallbackQuery, state: FSMContext):
    cid = int(call.data[10:])
    await exe("DELETE FROM admins WHERE id=? AND role='courier'", (cid,))
    await call.message.edit_text("🗑 Kuryer o'chirildi.")
    await call.answer()

@router.callback_query(F.data == "admin_couriers_back")
async def admin_couriers_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_couriers(call.message, state)
    await call.answer()


# ─── PROMO KODLAR ─────────────────────────────────────────────────────────────
@router.message(F.text == "🎟 Promo kodlar")
async def admin_promos(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    promos = await qall("SELECT * FROM promos ORDER BY id DESC LIMIT 20")
    rows   = []
    for p in promos:
        st    = "✅" if p["is_active"] else "❌"
        dtype = "%" if p["discount_type"] == "percent" else "so'm"
        rows.append([InlineKeyboardButton(
            text=f"{st} {p['code']} — {p['discount_value']}{dtype}  ({p['used_count']} marta)",
            callback_data=f"apromo_{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Yangi promo kod", callback_data="promo_new")])
    await msg.answer("🎟 <b>Promo kodlar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "promo_new")
async def promo_new(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🎟 Promo kod matnini kiriting (masalan: SUMMER20):", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.promo_code)
    await call.answer()

@router.message(AdminSt.promo_code)
async def promo_code_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    code = msg.text.strip().upper()
    existing = await q1("SELECT id FROM promos WHERE code=?", (code,))
    if existing:
        await msg.answer("❌ Bu kod allaqachon mavjud. Boshqa kod kiriting:"); return
    await state.update_data(promo_code=code)
    await msg.answer(
        "📊 Chegirma turini tanlang:",
        reply_markup=ik([("% Foiz", "pt_percent"), ("💰 Summasi", "pt_fixed")])
    )
    await state.set_state(AdminSt.promo_type)

@router.callback_query(F.data.startswith("pt_"), AdminSt.promo_type)
async def promo_type_sel(call: CallbackQuery, state: FSMContext):
    dtype = "percent" if call.data == "pt_percent" else "fixed"
    await state.update_data(promo_type=dtype)
    hint = "(%)" if dtype == "percent" else "(so'mda)"
    await call.message.answer(f"💰 Chegirma qiymatini kiriting {hint}:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.promo_val)
    await call.answer()

@router.message(AdminSt.promo_val)
async def promo_val_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam kiriting:"); return
    await state.update_data(promo_val=int(msg.text.strip()))
    await msg.answer("📦 Minimal buyurtma summasi (0 = cheklovsiz):")
    await state.set_state(AdminSt.promo_min)

@router.message(AdminSt.promo_min)
async def promo_min_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam:"); return
    await state.update_data(promo_min=int(msg.text.strip()))
    await msg.answer("🔢 Maksimal foydalanish soni (0 = cheksiz):")
    await state.set_state(AdminSt.promo_uses)

@router.message(AdminSt.promo_uses)
async def promo_uses_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam:"); return
    await state.update_data(promo_uses=int(msg.text.strip()))
    await msg.answer("📅 Muddati (YYYY-MM-DD format) yoki ⏭:", reply_markup=ik([("⏭ Muddatsiz","skip_exp")]))
    await state.set_state(AdminSt.promo_exp)

@router.callback_query(F.data == "skip_exp", AdminSt.promo_exp)
async def skip_exp(call: CallbackQuery, state: FSMContext):
    await _save_promo(call.message, state, "")
    await call.answer()

@router.message(AdminSt.promo_exp)
async def promo_exp_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await _save_promo(msg, state, msg.text.strip())

async def _save_promo(msg, state, expires):
    data = await state.get_data()
    await exe(
        "INSERT INTO promos(code,discount_type,discount_value,min_order,max_uses,expires_at) VALUES(?,?,?,?,?,?)",
        (data["promo_code"], data["promo_type"], data["promo_val"],
         data.get("promo_min", 0), data.get("promo_uses", 0), expires)
    )
    await state.clear()
    dtype = "%" if data["promo_type"] == "percent" else " so'm"
    await msg.answer(
        f"✅ Promo kod yaratildi!\n\nKod: <code>{data['promo_code']}</code>\n"
        f"Chegirma: {data['promo_val']}{dtype}\nMinimal: {fmt(data.get('promo_min',0))} so'm",
        reply_markup=admin_kb()
    )

@router.callback_query(F.data.startswith("apromo_"))
async def admin_promo_detail(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[7:])
    p   = await q1("SELECT * FROM promos WHERE id=?", (pid,))
    if not p:
        await call.answer(); return
    st    = "✅ Faol" if p["is_active"] else "❌ Nofaol"
    dtype = "%" if p["discount_type"] == "percent" else " so'm"
    await call.message.edit_text(
        f"🎟 <b>{p['code']}</b>\n{st}\n"
        f"Chegirma: {p['discount_value']}{dtype}\n"
        f"Minimal: {fmt(p['min_order'])} so'm\n"
        f"Ishlatildi: {p['used_count']} marta\n"
        f"Muddati: {p['expires_at'] or 'Cheksiz'}",
        reply_markup=ik(
            [("✅/❌ Holat", f"apromtog_{pid}"), ("🗑 O'chirish", f"apromdel_{pid}")],
            [("🔙", "admin_promos_back")],
        )
    )
    await call.answer()

@router.callback_query(F.data.startswith("apromtog_"))
async def promo_toggle(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    p   = await q1("SELECT is_active FROM promos WHERE id=?", (pid,))
    if p:
        await exe("UPDATE promos SET is_active=? WHERE id=?", (0 if p["is_active"] else 1, pid))
    await admin_promo_detail(call, state)
    await call.answer("✅")

@router.callback_query(F.data.startswith("apromdel_"))
async def promo_del(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[9:])
    await exe("DELETE FROM promos WHERE id=?", (pid,))
    await call.message.edit_text("🗑 Promo kod o'chirildi.")
    await call.answer()

@router.callback_query(F.data == "admin_promos_back")
async def admin_promos_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_promos(call.message, state)
    await call.answer()


# ─── YETKAZISH ZONALARI ───────────────────────────────────────────────────────
@router.message(F.text == "🗺 Yetkazish zonalari")
async def admin_zones(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    zones = await qall("SELECT * FROM delivery_zones ORDER BY delivery_fee")
    rows  = []
    for z in zones:
        st = "✅" if z["is_active"] else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{st} {z['name']} — {fmt(z['delivery_fee'])} so'm  ⏱{z['delivery_time']}",
            callback_data=f"azone_{z['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Yangi zona", callback_data="zone_new")])
    await msg.answer(f"🗺 <b>Yetkazish zonalari ({len(zones)} ta):</b>",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "zone_new")
async def zone_new(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📍 Zona nomini kiriting (masalan: Yunusabad):", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.zone_name)
    await call.answer()

@router.message(AdminSt.zone_name)
async def zone_name_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.update_data(zone_name=msg.text.strip())
    await msg.answer("💰 Yetkazish narxini kiriting (so'mda, masalan: 10000):")
    await state.set_state(AdminSt.zone_fee)

@router.message(AdminSt.zone_fee)
async def zone_fee_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam kiriting:"); return
    await state.update_data(zone_fee=int(msg.text.strip()))
    await msg.answer("⏱ Yetkazish vaqtini kiriting (masalan: 30-45 daqiqa):")
    await state.set_state(AdminSt.zone_time)

@router.message(AdminSt.zone_time)
async def zone_time_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.update_data(zone_time=msg.text.strip())
    await msg.answer("📦 Minimal buyurtma summasi (0 = yo'q):")
    await state.set_state(AdminSt.zone_min)

@router.message(AdminSt.zone_min)
async def zone_min_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    if not msg.text.strip().isdigit():
        await msg.answer("❌ Raqam:"); return
    data = await state.get_data()
    await exe(
        "INSERT INTO delivery_zones(name,delivery_fee,delivery_time,min_order) VALUES(?,?,?,?)",
        (data["zone_name"], data["zone_fee"], data["zone_time"], int(msg.text.strip()))
    )
    await state.clear()
    await msg.answer(
        f"✅ Zona <b>{data['zone_name']}</b> qo'shildi!\n"
        f"Narxi: {fmt(data['zone_fee'])} so'm | Vaqt: {data['zone_time']}",
        reply_markup=admin_kb()
    )

@router.callback_query(F.data.startswith("azone_"))
async def admin_zone_detail(call: CallbackQuery, state: FSMContext):
    zid = int(call.data[6:])
    z   = await q1("SELECT * FROM delivery_zones WHERE id=?", (zid,))
    if not z: await call.answer(); return
    st = "✅ Faol" if z["is_active"] else "❌ Nofaol"
    await call.message.edit_text(
        f"📍 <b>{z['name']}</b>\n{st}\n"
        f"💰 Narx: {fmt(z['delivery_fee'])} so'm\n"
        f"⏱ Vaqt: {z['delivery_time']}\n"
        f"📦 Minimal: {fmt(z['min_order'])} so'm",
        reply_markup=ik(
            [("✅/❌ Holat", f"aztog_{zid}"), ("🗑 O'chirish", f"azdel_{zid}")],
            [("🔙", "admin_zones_back")],
        )
    )
    await call.answer()

@router.callback_query(F.data.startswith("aztog_"))
async def zone_toggle(call: CallbackQuery, state: FSMContext):
    zid = int(call.data[6:])
    z   = await q1("SELECT is_active FROM delivery_zones WHERE id=?", (zid,))
    if z:
        await exe("UPDATE delivery_zones SET is_active=? WHERE id=?", (0 if z["is_active"] else 1, zid))
    await admin_zone_detail(call, state)
    await call.answer("✅")

@router.callback_query(F.data.startswith("azdel_"))
async def zone_del(call: CallbackQuery, state: FSMContext):
    zid = int(call.data[6:])
    await exe("DELETE FROM delivery_zones WHERE id=?", (zid,))
    await call.message.edit_text("🗑 Zona o'chirildi.")
    await call.answer()

@router.callback_query(F.data == "admin_zones_back")
async def admin_zones_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_zones(call.message, state)
    await call.answer()


# ─── SOZLAMALAR ───────────────────────────────────────────────────────────────
@router.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    sn  = await setting("shop_name")
    op  = await setting("shop_open")
    ot  = await setting("open_time")
    ct  = await setting("close_time")
    mo  = await setting("min_order")
    ph  = await setting("phone_support")

    await msg.answer(
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"🏪 Do'kon nomi: {sn}\n"
        f"🔘 Holat: {'🟢 Ochiq' if op=='1' else '🔴 Yopiq'}\n"
        f"⏰ Ish vaqti: {ot} – {ct}\n"
        f"📦 Minimal buyurtma: {fmt(int(mo or 0))} so'm\n"
        f"📞 Telefon: {ph}",
        reply_markup=ik(
            [("🟢 Ochiq/Yopiq",    "stog_open")],
            [("⏰ Ish vaqti",       "sedit_times")],
            [("📦 Minimal buyurtma","sedit_min")],
            [("🏪 Do'kon nomi",     "sedit_name")],
            [("📞 Telefon",         "sedit_phone")],
            [("📢 Xush kelibsiz xabari","sedit_welcome")],
        )
    )

@router.callback_query(F.data == "stog_open")
async def settings_toggle_open(call: CallbackQuery, state: FSMContext):
    cur = await setting("shop_open")
    await set_setting("shop_open", "0" if cur == "1" else "1")
    st = "🟢 Ochiq" if cur != "1" else "🔴 Yopiq"
    await call.answer(f"Do'kon holati: {st}", show_alert=True)
    await admin_settings(call.message, state)

@router.callback_query(F.data == "sedit_times")
async def sedit_times(call: CallbackQuery, state: FSMContext):
    await state.update_data(setting_key="times")
    await call.message.answer("⏰ Ish vaqtini kiriting (HH:MM-HH:MM formatida, masalan: 09:00-22:00):", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.setting_val)
    await call.answer()

@router.callback_query(F.data.startswith("sedit_"))
async def sedit_field(call: CallbackQuery, state: FSMContext):
    field = call.data[6:]
    field_map = {
        "min": ("min_order", "📦 Minimal buyurtma (so'mda):"),
        "name": ("shop_name", "🏪 Yangi do'kon nomini kiriting:"),
        "phone": ("phone_support", "📞 Telefon raqamini kiriting:"),
        "welcome": ("welcome_msg", "📢 Xush kelibsiz xabarini kiriting:"),
    }
    if field not in field_map:
        await call.answer(); return
    key, prompt = field_map[field]
    await state.update_data(setting_key=key)
    await call.message.answer(prompt, reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.setting_val)
    await call.answer()

@router.message(AdminSt.setting_val)
async def setting_val_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    data = await state.get_data()
    key  = data.get("setting_key", "")
    val  = msg.text.strip()

    if key == "times":
        parts = val.replace(" ", "").split("-")
        if len(parts) == 2:
            await set_setting("open_time",  parts[0])
            await set_setting("close_time", parts[1])
            await state.clear()
            await msg.answer(f"✅ Ish vaqti: {parts[0]} – {parts[1]}", reply_markup=admin_kb())
        else:
            await msg.answer("❌ Format xato. HH:MM-HH:MM kiriting:")
        return

    if key == "min_order" and not val.isdigit():
        await msg.answer("❌ Raqam kiriting:"); return

    await set_setting(key, val)
    await state.clear()
    await msg.answer("✅ Saqlandi!", reply_markup=admin_kb())


# ─── STATISTIKA ───────────────────────────────────────────────────────────────
@router.message(F.text == "📊 Statistika")
async def admin_stats(msg: Message, state: FSMContext):
    if not await check_admin(msg): return

    today     = datetime.now().strftime("%Y-%m-%d")
    week_ago  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    total_users   = (await q1("SELECT COUNT(*) as n FROM users"))["n"]
    today_users   = (await q1("SELECT COUNT(*) as n FROM users WHERE created_at LIKE ?", (f"{today}%",)))["n"]

    total_orders  = (await q1("SELECT COUNT(*) as n FROM orders"))["n"]
    today_orders  = (await q1("SELECT COUNT(*) as n FROM orders WHERE created_at LIKE ?", (f"{today}%",)))["n"]
    week_orders   = (await q1("SELECT COUNT(*) as n FROM orders WHERE created_at >= ?", (week_ago,)))["n"]

    delivered     = (await q1("SELECT COUNT(*) as n FROM orders WHERE status='delivered'"))["n"]
    cancelled     = (await q1("SELECT COUNT(*) as n FROM orders WHERE status='cancelled'"))["n"]
    new_orders    = (await q1("SELECT COUNT(*) as n FROM orders WHERE status='new'"))["n"]

    today_rev  = await q1("SELECT COALESCE(SUM(total_amount),0) as s FROM orders WHERE status='delivered' AND updated_at LIKE ?", (f"{today}%",))
    week_rev   = await q1("SELECT COALESCE(SUM(total_amount),0) as s FROM orders WHERE status='delivered' AND updated_at >= ?", (week_ago,))
    month_rev  = await q1("SELECT COALESCE(SUM(total_amount),0) as s FROM orders WHERE status='delivered' AND updated_at >= ?", (month_ago,))
    total_rev  = await q1("SELECT COALESCE(SUM(total_amount),0) as s FROM orders WHERE status='delivered'")

    top_prods = await qall("""
        SELECT p.name, SUM(oi.quantity) as cnt
        FROM order_items oi JOIN products p ON oi.product_id=p.id
        GROUP BY oi.product_id ORDER BY cnt DESC LIMIT 5
    """)

    txt  = "📊 <b>Statistika</b>\n\n"
    txt += f"👥 <b>Foydalanuvchilar:</b>\n"
    txt += f"  Jami: {total_users} ta | Bugun: {today_users} ta\n\n"
    txt += f"🛒 <b>Buyurtmalar:</b>\n"
    txt += f"  Jami: {total_orders} ta\n"
    txt += f"  Bugun: {today_orders} ta | Hafta: {week_orders} ta\n"
    txt += f"  ✅ Yetkazildi: {delivered} | ❌ Bekor: {cancelled}\n"
    txt += f"  🆕 Kutilmoqda: {new_orders}\n\n"
    txt += f"💰 <b>Daromad:</b>\n"
    txt += f"  Bugun: {fmt(today_rev['s'])} so'm\n"
    txt += f"  Hafta: {fmt(week_rev['s'])} so'm\n"
    txt += f"  Oy: {fmt(month_rev['s'])} so'm\n"
    txt += f"  Jami: {fmt(total_rev['s'])} so'm\n\n"
    if top_prods:
        txt += "🏆 <b>TOP mahsulotlar:</b>\n"
        for i, p in enumerate(top_prods, 1):
            txt += f"  {i}. {p['name']} — {p['cnt']} ta\n"

    await msg.answer(txt)


# ─── BROADCAST ────────────────────────────────────────────────────────────────
@router.message(F.text == "📨 Broadcast")
async def admin_broadcast(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    cnt = (await q1("SELECT COUNT(*) as n FROM users WHERE is_blocked=0"))["n"]
    await msg.answer(
        f"📨 <b>Xabar tarqatish</b>\n\n{cnt} ta foydalanuvchiga xabar yuborilyapti.\n\nXabarni kiriting:",
        reply_markup=CANCEL_KB
    )
    await state.set_state(AdminSt.bcast_msg)

@router.message(AdminSt.bcast_msg)
async def broadcast_send(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    await state.clear()

    users = await qall("SELECT tg_id FROM users WHERE is_blocked=0")
    ok = fail = 0
    await msg.answer(f"⏳ Yuborilmoqda... ({len(users)} ta foydalanuvchi)")

    for i, u in enumerate(users):
        try:
            await bot.send_message(u["tg_id"], f"📢 <b>Do'kondan xabar:</b>\n\n{msg.text}")
            ok += 1
        except Exception:
            fail += 1
        if i % 30 == 0:
            await asyncio.sleep(1)

    await msg.answer(f"✅ Yuborildi: {ok} ta\n❌ Muvaffaqiyatsiz: {fail} ta", reply_markup=admin_kb())


# ─── SUPPORT (ADMIN) ──────────────────────────────────────────────────────────
@router.message(F.text == "🆘 Support")
async def admin_support(msg: Message, state: FSMContext):
    if not await check_admin(msg): return
    tickets = await qall("SELECT st.*, u.name as uname FROM support_tickets st LEFT JOIN users u ON st.user_id=u.tg_id ORDER BY st.id DESC LIMIT 20")
    rows = []
    for t in tickets:
        st_ic = "🟢" if t["status"] == "open" else ("🔵" if t["status"] == "in_progress" else "⚫")
        rows.append([InlineKeyboardButton(
            text=f"{st_ic} #{t['id']} {t['uname'] or 'Noma\'lum'}: {t['subject'][:30]}",
            callback_data=f"asup_{t['id']}"
        )])
    if not rows:
        await msg.answer("🆘 Hali ticketlar yo'q.")
        return
    await msg.answer("🆘 <b>Support ticketlar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith("asup_"))
async def admin_ticket_detail(call: CallbackQuery, state: FSMContext):
    tid   = int(call.data[5:])
    t     = await q1("SELECT st.*, u.name as uname FROM support_tickets st LEFT JOIN users u ON st.user_id=u.tg_id WHERE st.id=?", (tid,))
    if not t:
        await call.answer(); return
    msgs  = await qall("SELECT * FROM support_messages WHERE ticket_id=? ORDER BY id", (tid,))
    txt   = f"📋 <b>Ticket #{tid}</b>\n👤 {t['uname'] or 'Noma\'lum'}\n📝 {t['subject']}\n\n"
    for m in msgs[-10:]:
        who = "👤 Mijoz" if not m["is_admin"] else "👨‍💼 Admin"
        txt += f"{who}: {m['message']}\n"
    await call.message.edit_text(txt, reply_markup=ik(
        [("✉️ Javob berish", f"asrep_{tid}"), ("✅ Yopish", f"asclose_{tid}")],
        [("🔙", "admin_support_back")],
    ))
    await exe("UPDATE support_tickets SET status='in_progress', admin_id=? WHERE id=?",
              (call.from_user.id, tid))
    await call.answer()

@router.callback_query(F.data.startswith("asrep_"))
async def admin_support_reply(call: CallbackQuery, state: FSMContext):
    tid = int(call.data[6:])
    await state.update_data(sup_ticket_id=tid)
    await call.message.answer("✉️ Javobingizni kiriting:", reply_markup=CANCEL_KB)
    await state.set_state(AdminSt.support_rep)
    await call.answer()

@router.message(AdminSt.support_rep)
async def admin_support_reply_send(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("Bekor.", reply_markup=admin_kb()); return
    data  = await state.get_data()
    tid   = data.get("sup_ticket_id")
    t     = await q1("SELECT * FROM support_tickets WHERE id=?", (tid,))
    await exe(
        "INSERT INTO support_messages(ticket_id,sender_id,is_admin,message) VALUES(?,?,1,?)",
        (tid, msg.from_user.id, msg.text)
    )
    await exe("UPDATE support_tickets SET status='in_progress', updated_at=? WHERE id=?", (now_str(), tid))
    if t:
        try:
            await bot.send_message(
                t["user_id"],
                f"📋 <b>Ticket #{tid} — Admin javobi:</b>\n\n{msg.text}"
            )
        except Exception:
            pass
    await state.clear()
    await msg.answer("✅ Javob yuborildi!", reply_markup=admin_kb())

@router.callback_query(F.data.startswith("asclose_"))
async def admin_ticket_close(call: CallbackQuery, state: FSMContext):
    tid = int(call.data[8:])
    t   = await q1("SELECT user_id FROM support_tickets WHERE id=?", (tid,))
    await exe("UPDATE support_tickets SET status='closed', updated_at=? WHERE id=?", (now_str(), tid))
    if t:
        try:
            await bot.send_message(t["user_id"], f"📋 Ticket #{tid} yopildi. Murojaat uchun rahmat!")
        except Exception:
            pass
    await call.message.edit_text(f"✅ Ticket #{tid} yopildi.")
    await call.answer()

@router.callback_query(F.data == "admin_support_back")
async def admin_support_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await admin_support(call.message, state)
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  ═══════════════════  COURIER HANDLERS  ═══════════════════
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🚚 Kuryer Panel")
async def cmd_courier(msg: Message, state: FSMContext):
    if not await is_courier(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q."); return
    new_cnt = (await q1(
        "SELECT COUNT(*) as n FROM orders WHERE courier_id=? AND status='on_way'",
        (msg.from_user.id,)
    ))["n"]
    await msg.answer(
        f"🚚 <b>Kuryer Panel</b>\n\nYo'ldagi buyurtmalar: {new_cnt} ta",
        reply_markup=courier_kb()
    )

@router.message(F.text == "📋 Buyurtmalarim")
async def courier_orders(msg: Message, state: FSMContext):
    if not await is_courier(msg.from_user.id): return
    uid    = msg.from_user.id
    orders = await qall(
        "SELECT * FROM orders WHERE courier_id=? AND status IN ('on_way','confirmed') ORDER BY id DESC LIMIT 20",
        (uid,)
    )
    if not orders:
        await msg.answer("📋 Hozirda biriktirilgan buyurtma yo'q."); return
    kb = orders_list_ik(orders, "cord")
    if kb:
        await msg.answer(f"📋 <b>Sizning buyurtmalaringiz ({len(orders)} ta):</b>", reply_markup=kb)

@router.callback_query(F.data.startswith("cord_"))
async def courier_order_detail(call: CallbackQuery, state: FSMContext):
    oid_i = int(call.data[5:])
    o     = await q1("SELECT * FROM orders WHERE id=? AND courier_id=?", (oid_i, call.from_user.id))
    if not o:
        await call.answer("Topilmadi yoki ruxsat yo'q", show_alert=True); return
    txt = await fmt_order(oid_i)
    # Add map link
    if o["address"]:
        addr_enc = o["address"].replace(" ", "+")
        txt += f"\n🗺 <a href='https://maps.google.com/?q={addr_enc}'>Xaritada ko'rish</a>"
    await call.message.edit_text(txt, reply_markup=courier_order_ik(oid_i, o["status"]))
    await call.answer()

@router.callback_query(F.data.startswith("cdeliver_"))
async def courier_deliver(call: CallbackQuery, state: FSMContext):
    oid_i = int(call.data[9:])
    o     = await q1("SELECT * FROM orders WHERE id=? AND courier_id=?", (oid_i, call.from_user.id))
    if not o:
        await call.answer("Ruxsat yo'q", show_alert=True); return

    await exe("UPDATE orders SET status='delivered', updated_at=? WHERE id=?", (now_str(), oid_i))

    # Add earned points to user
    pts = o["points_earned"]
    if pts > 0:
        await add_points(o["user_id"], pts, f"Buyurtma #{oid_i}")

    try:
        await bot.send_message(
            o["user_id"],
            f"✅ <b>Buyurtma {oid(oid_i)} yetkazildi!</b>\n\n"
            f"Xarid uchun rahmat! 🙏\n💎 +{pts} ball oldiniz!"
        )
    except Exception:
        pass

    await notify_admins(f"✅ Buyurtma {oid(oid_i)} kuryer tomonidan yetkazildi!")
    await call.message.edit_text(f"✅ Buyurtma {oid(oid_i)} yetkazildi deb belgilandi!")
    await call.answer("✅ Yetkazildi!")

@router.callback_query(F.data == "courier_menu")
async def courier_menu_cb(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  NAVIGATION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.answer()

@router.message(F.text == "🔙 Asosiy menyu")
async def cmd_main_menu(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🏠 Bosh menyu:", reply_markup=await get_main_kb(msg.from_user.id))

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📋 <b>Yordam</b>\n\n"
        "/start — Boshlash\n"
        "🛍 Katalog — Mahsulotlarni ko'rish\n"
        "🔍 Qidiruv — Mahsulot qidirish\n"
        "🛒 Savatcha — Savat\n"
        "📦 Buyurtmalarim — Buyurtmalar tarixi\n"
        "⚡ Flash Sale — Chegirmali mahsulotlar\n"
        "⭐ TOP — Eng ko'p sotilgan\n"
        "💎 Ballarim — Bonus ballar\n"
        "👤 Profilim — Shaxsiy ma'lumotlar\n"
        "🤝 Referal — Do'stlarni taklif etish\n"
        "🆘 Yordam — Qo'llab-quvvatlash\n"
    )

# Handle unknown messages gracefully
@router.message()
async def unknown_msg(msg: Message, state: FSMContext):
    cur_state = await state.get_state()
    if cur_state:
        return  # Let state handlers deal with it
    await msg.answer(
        "❓ Tushunmadim. Menyu tugmalaridan foydalaning:",
        reply_markup=await get_main_kb(msg.from_user.id)
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
async def set_bot_commands():
    commands = [
        BotCommand(command="start",  description="Botni ishga tushirish"),
        BotCommand(command="help",   description="Yordam"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await init_db()
    await set_bot_commands()

    logger.info("🚀 Enterprise Shop Bot ishga tushdi!")
    logger.info(f"👑 Admin IDs: {ADMIN_IDS}")

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("⚠️  BOT TOKEN sozlanmagan!")
        print("   .env faylida yoki muhit o'zgaruvchisida:")
        print("   BOT_TOKEN=your_token_here")
        print("   ADMIN_IDS=your_telegram_id")
        print("=" * 60)
    else:
        asyncio.run(main())
