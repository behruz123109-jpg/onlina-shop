import asyncio
import logging
import aiosqlite
import math
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton

# ═══════════════════════════════════════════════════════════════════════
#  SOZLAMALAR
# ═══════════════════════════════════════════════════════════════════════
API_TOKEN   = "8747604242:AAFj9oSG5txNx1Pw7UfCAc9WH_Em8tB73p0"
SUPER_ADMIN = 8488028783
DB_NAME     = "shop.db"

router = Router()
pending_orders: dict[int, str] = {}

STATUS_ICON = {
    "Kutilmoqda":  "⏳",
    "Tasdiqlandi": "✅",
    "Yo'lda":      "🚚",
    "Yetkazildi":  "📦",
    "Rad etildi":  "❌",
    "Bekor qilindi": "🛑",
}

# ═══════════════════════════════════════════════════════════════════════
#  FSM HOLATLARI
# ═══════════════════════════════════════════════════════════════════════
class AdminCategoryForm(StatesGroup):
    name        = State()
    description = State()

class AdminProductForm(StatesGroup):
    action      = State()
    category_id = State()
    product_id  = State()
    name        = State()
    description = State()
    price       = State()
    stock       = State()
    photo       = State()

class AdminEditForm(StatesGroup):
    field       = State()
    product_id  = State()
    new_value   = State()

class AdminPromoForm(StatesGroup):
    code        = State()
    discount    = State()
    dtype       = State()
    expiry      = State()

class AdminBroadcast(StatesGroup):
    msg = State()

class UserProfileForm(StatesGroup):
    action    = State()
    address_name = State()
    address   = State()

class OrderForm(StatesGroup):
    saved_addr = State()
    promo      = State()
    phone      = State()
    address    = State()
    confirm    = State()

class ReviewForm(StatesGroup):
    order_id   = State()
    product_id = State()
    rating     = State()
    comment    = State()

class SuperAdminForm(StatesGroup):
    new_id = State()

# ═══════════════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════════════
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                full_name TEXT,
                phone     TEXT,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS addresses (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                name     TEXT NOT NULL,
                address  TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                description TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name        TEXT NOT NULL,
                description TEXT,
                price       INTEGER NOT NULL,
                stock       INTEGER NOT NULL DEFAULT 0,
                photo_id    TEXT,
                views       INTEGER DEFAULT 0,
                sold        INTEGER DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity   INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                phone      TEXT,
                address    TEXT,
                total      INTEGER NOT NULL DEFAULT 0,
                discount   INTEGER NOT NULL DEFAULT 0,
                promo_code TEXT,
                status     TEXT NOT NULL DEFAULT 'Kutilmoqda',
                cancel_until DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id   INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity   INTEGER NOT NULL,
                price      INTEGER NOT NULL,
                FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                order_id   INTEGER NOT NULL,
                rating     INTEGER NOT NULL,
                comment    TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, product_id, order_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT UNIQUE NOT NULL,
                discount    INTEGER NOT NULL,
                dtype       TEXT NOT NULL DEFAULT 'percent',
                usage_limit INTEGER NOT NULL DEFAULT -1,
                used_count  INTEGER NOT NULL DEFAULT 0,
                expiry_date DATETIME,
                is_active   INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)) as cur:
            return bool(await cur.fetchone())

# ═══════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════
async def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text="🛍 Katalog")
    b.button(text="🔍 Qidiruv")
    b.button(text="⭐ Top Mahsulot")
    b.button(text="🛒 Savatcha")
    b.button(text="📦 Buyurtmalarim")
    b.button(text="👤 Profil")
    if await is_admin(user_id):
        b.button(text="⚙️ Admin")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def admin_menu_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text="📁 Bo'limlar")
    b.button(text="📦 Mahsulotlar")
    b.button(text="📋 Buyurtmalar")
    b.button(text="🎟 Promo Kodlar")
    b.button(text="📊 Dashboard")
    b.button(text="📢 Xabar tarqatish")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )

def location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton(text="✍️ Qo'lda yozish")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )

def order_kb(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"ord_app_{order_id}")
    b.button(text="❌ Rad etish", callback_data=f"ord_rej_{order_id}")
    b.button(text="🚚 Yo'lda", callback_data=f"ord_del_{order_id}")
    b.button(text="📦 Yetkazildi", callback_data=f"ord_done_{order_id}")
    b.adjust(2)
    return b.as_markup()

def stars_kb(order_id: int, product_id: int):
    b = InlineKeyboardBuilder()
    for i in range(1, 6):
        b.button(text="⭐" * i, callback_data=f"rate_{order_id}_{product_id}_{i}")
    b.adjust(5)
    return b.as_markup()

# ═══════════════════════════════════════════════════════════════════════
#  UNIVERSAL
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "❌ Bekor qilish", StateFilter("*"))
async def cancel_all(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🛑 Bekor qilindi.", reply_markup=await main_menu_kb(message.from_user.id))

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, phone) VALUES (?,?,?)",
            (message.from_user.id, message.from_user.full_name, "")
        )
        await db.commit()
    await message.answer(f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 🌟",
                        reply_markup=await main_menu_kb(message.from_user.id))

@router.message(F.text == "🏠 Asosiy menyu")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=await main_menu_kb(message.from_user.id))

# ═══════════════════════════════════════════════════════════════════════
#  USER PROFILE (MANZILLAR SAQLASH + QAYTA BUYURTMA)
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "👤 Profil")
async def user_profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (message.from_user.id,)) as cur:
            user = await cur.fetchone()
        async with db.execute("SELECT * FROM addresses WHERE user_id=?", (message.from_user.id,)) as cur:
            addrs = await cur.fetchall()

    txt = f"👤 <b>Profil</b>\n\nIsm: {user['full_name']}\nID: {user['user_id']}\n\n"
    if addrs:
        txt += "📍 <b>Saqlangan Manzillar:</b>\n"
        for a in addrs:
            default = " (asosiy)" if a["is_default"] else ""
            txt += f"  • {a['name']}{default}\n"
    b = InlineKeyboardBuilder()
    b.button(text="➕ Manzil qo'shish", callback_data="add_addr")
    b.button(text="🗑 Manzil o'chirish", callback_data="del_addr")
    await message.answer(txt, reply_markup=b.as_markup())

@router.callback_query(F.data == "add_addr")
async def add_address_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Manzilning nomini kiriting (masalan: 'Uy', 'Ofis'):", reply_markup=cancel_kb())
    await state.set_state(UserProfileForm.address_name)

@router.message(UserProfileForm.address_name)
async def add_address_name(message: types.Message, state: FSMContext):
    await state.update_data(address_name=message.text)
    await message.answer("Manzilni kiriting:", reply_markup=location_kb())
    await state.set_state(UserProfileForm.address)

@router.message(UserProfileForm.address)
async def add_address_save(message: types.Message, state: FSMContext):
    if message.location:
        addr = f"https://maps.google.com/?q={message.location.latitude},{message.location.longitude}"
    elif message.text == "✍️ Qo'lda yozish":
        await message.answer("Manzilni kiriting:", reply_markup=cancel_kb())
        return
    else:
        addr = message.text
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM addresses WHERE user_id=?", (message.from_user.id,)) as cur:
            count = (await cur.fetchone())[0]
        await db.execute(
            "INSERT INTO addresses (user_id, name, address, is_default) VALUES (?,?,?,?)",
            (message.from_user.id, data["address_name"], addr, 1 if count == 0 else 0)
        )
        await db.commit()
    await message.answer("✅ Manzil saqlandi!", reply_markup=await main_menu_kb(message.from_user.id))
    await state.clear()

@router.callback_query(F.data == "del_addr")
async def del_address(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM addresses WHERE user_id=?", (call.from_user.id,)) as cur:
            addrs = await cur.fetchall()
    if not addrs:
        return await call.message.answer("Saqlangan manzil yo'q.")
    b = InlineKeyboardBuilder()
    for a in addrs:
        b.button(text=f"🗑 {a['name']}", callback_data=f"deladdr_{a['id']}")
    b.adjust(2)
    await call.message.answer("O'chirish uchun tanlang:", reply_markup=b.as_markup())
    await state.set_state(UserProfileForm.action)

@router.callback_query(F.data.startswith("deladdr_"))
async def del_address_do(call: types.CallbackQuery, state: FSMContext):
    addr_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM addresses WHERE id=? AND user_id=?", (addr_id, call.from_user.id))
        await db.commit()
    await call.message.edit_text("✅ Manzil o'chirildi.")
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════
#  KATALOG + TOP MAHSULOT + QIDIRUV
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "🛍 Katalog")
async def show_catalog(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    if not cats:
        return await message.answer("Bo'limlar mavjud emas.")
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c["name"], callback_data=f"cat_{c['id']}_0")
    b.adjust(2)
    await message.answer("📂 <b>Bo'limni tanlang:</b>", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    parts = call.data.split("_")
    c_id, page = int(parts[1]), int(parts[2])

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE category_id=? AND stock>0 ORDER BY sold DESC", (c_id,)) as cur:
            all_prods = await cur.fetchall()

    if not all_prods:
        return await call.answer("Mahsulot yo'q.", show_alert=True)

    total = len(all_prods)
    p = all_prods[page]
    
    # Reyting
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE product_id=?", (p["id"],)) as cur:
            rev = await cur.fetchone()
    
    stars_txt = ""
    if rev and rev[1] > 0:
        avg = round(rev[0], 1)
        stars_txt = f"\n⭐ {avg}/5.0 ({rev[1]} ta baho)"

    caption = (
        f"🔹 <b>{p['name']}</b>\n\n"
        f"📝 {p['description'] or 'Tavsif yo\'q'}\n"
        f"💰 <b>{p['price']:,} so'm</b>\n"
        f"📦 Zaxira: {p['stock']} dona{stars_txt}\n"
        f"📊 Sotilgan: {p['sold']} dona\n\n"
        f"<i>{page+1}/{total}</i>"
    )

    b = InlineKeyboardBuilder()
    b.button(text="🛒 Savatga", callback_data=f"add_{p['id']}")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cat_{c_id}_{page-1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cat_{c_id}_{page+1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙", callback_data="back_cat"))

    try:
        if p["photo_id"]:
            await call.message.delete()
            await call.message.answer_photo(photo=p["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await call.message.edit_text(caption, reply_markup=b.as_markup())
    except:
        await call.message.answer(caption, reply_markup=b.as_markup())

@router.callback_query(F.data == "back_cat")
async def back_catalog(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c["name"], callback_data=f"cat_{c['id']}_0")
    b.adjust(2)
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("📂 Bo'limni tanlang:", reply_markup=b.as_markup())

@router.message(F.text == "⭐ Top Mahsulot")
async def top_products(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE stock>0 ORDER BY sold DESC LIMIT 10") as cur:
            prods = await cur.fetchall()
    if not prods:
        return await message.answer("Mahsulot yo'q.")
    txt = "⭐ <b>Top 10 Mahsulot:</b>\n\n"
    b = InlineKeyboardBuilder()
    for i, p in enumerate(prods, 1):
        txt += f"{i}. <b>{p['name']}</b> — {p['price']:,} so'm (sotilgan: {p['sold']})\n"
        b.button(text=f"🛒 {i}", callback_data=f"add_{p['id']}")
    b.adjust(5)
    await message.answer(txt, reply_markup=b.as_markup())

@router.message(F.text == "🔍 Qidiruv")
async def search(message: types.Message, state: FSMContext):
    await message.answer("Qidiruv so'zini kiriting:", reply_markup=cancel_kb())
    await state.set_state(AdminEditForm.field)

@router.message(AdminEditForm.field)
async def search_do(message: types.Message, state: FSMContext):
    q = f"%{message.text}%"
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE name LIKE ? OR description LIKE ?", (q, q)) as cur:
            prods = await cur.fetchall()
    await state.clear()
    if not prods:
        return await message.answer("Hech narsa topilmadi.")
    txt = f"🔍 <b>Natija ({len(prods)} ta):</b>\n\n"
    b = InlineKeyboardBuilder()
    for p in prods:
        txt += f"🔹 {p['name']} — {p['price']:,} so'm\n"
        if p["stock"] > 0:
            b.button(text=f"🛒 {p['name'][:15]}", callback_data=f"add_{p['id']}")
    b.adjust(2)
    await message.answer(txt, reply_markup=b.as_markup() if b.buttons else None)

@router.callback_query(F.data.startswith("add_"))
async def add_to_cart(call: types.CallbackQuery):
    p_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, p_id)) as cur:
            if await cur.fetchone():
                await db.execute("UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?",
                               (call.from_user.id, p_id))
            else:
                await db.execute("INSERT INTO cart (user_id, product_id) VALUES (?,?)", (call.from_user.id, p_id))
        await db.commit()
    await call.answer("✅ Savatga qo'shildi!")

# ═══════════════════════════════════════════════════════════════════════
#  SAVATCHA (MIQDOR BOSHQARUVI)
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "🛒 Savatcha")
async def view_cart(message: types.Message):
    await _show_cart(message, message.from_user.id)

async def _show_cart(message, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.id, c.quantity, p.name, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
            (user_id,)
        ) as cur:
            items = await cur.fetchall()

    if not items:
        return await message.answer("🛒 Savatingiz bo'sh.")

    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    b = InlineKeyboardBuilder()
    for i in items:
        line = i["price"] * i["quantity"]
        tot += line
        txt += f"▪️ {i['name']} x{i['quantity']} = {line:,} so'm\n"
        b.button(text="➖", callback_data=f"qty_{i['id']}_-")
        b.button(text=f"{i['quantity']}", callback_data="noop")
        b.button(text="➕", callback_data=f"qty_{i['id']}_+")
        b.button(text="🗑", callback_data=f"del_{i['id']}")

    txt += f"\n💰 <b>Jami: {tot:,} so'm</b>"
    b.adjust(4)
    b.row(
        InlineKeyboardButton(text="✅ Buyurtma", callback_data="checkout"),
        InlineKeyboardButton(text="🗑 Tozalash", callback_data="clr_cart")
    )
    await message.answer(txt, reply_markup=b.as_markup())

@router.callback_query(F.data == "noop")
async def noop(call: types.CallbackQuery):
    await call.answer()

@router.callback_query(F.data.startswith("qty_"))
async def change_qty(call: types.CallbackQuery):
    cart_id, op = int(call.data.split("_")[1]), call.data.split("_")[2]
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT quantity FROM cart WHERE id=?", (cart_id,)) as cur:
            qty = (await cur.fetchone())[0]
        if op == "+":
            await db.execute("UPDATE cart SET quantity=quantity+1 WHERE id=?", (cart_id,))
        elif op == "-" and qty <= 1:
            await db.execute("DELETE FROM cart WHERE id=?", (cart_id,))
        elif op == "-":
            await db.execute("UPDATE cart SET quantity=quantity-1 WHERE id=?", (cart_id,))
        await db.commit()
    await _show_cart(call.message, call.from_user.id)

@router.callback_query(F.data.startswith("del_") & ~F.data.startswith("del_addr"))
async def delete_from_cart(call: types.CallbackQuery):
    cart_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE id=?", (cart_id,))
        await db.commit()
    await _show_cart(call.message, call.from_user.id)

@router.callback_query(F.data == "clr_cart")
async def clear_cart(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE user_id=?", (call.from_user.id,))
        await db.commit()
    await call.message.edit_text("🛒 Savatcha tozalandi.")

# ═══════════════════════════════════════════════════════════════════════
#  CHECKOUT (PROMO + SAQLANGAN MANZILLAR + CANCEL BUYURTMA)
# ═══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "checkout")
async def checkout_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM addresses WHERE user_id=?", (call.from_user.id,)) as cur:
            addrs = await cur.fetchall()
    
    if addrs:
        b = InlineKeyboardBuilder()
        for a in addrs:
            b.button(text=a["name"], callback_data=f"addr_{a['id']}")
        b.button(text="✍️ Yangi", callback_data="addr_new")
        b.adjust(2)
        await call.message.answer("📍 Manzilni tanlang:", reply_markup=b.as_markup())
        await state.set_state(OrderForm.saved_addr)
    else:
        await call.message.answer("📍 Manzilni kiriting:", reply_markup=location_kb())
        await state.set_state(OrderForm.address)

@router.callback_query(OrderForm.saved_addr, F.data.startswith("addr_"))
async def checkout_addr_select(call: types.CallbackQuery, state: FSMContext):
    if call.data.startswith("addr_new"):
        await call.message.answer("📍 Yangi manzil:", reply_markup=location_kb())
        await state.set_state(OrderForm.address)
    else:
        addr_id = int(call.data.split("_")[1])
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT address FROM addresses WHERE id=?", (addr_id,)) as cur:
                addr = (await cur.fetchone())[0]
        await state.update_data(address=addr)
        await call.message.answer("🎟 Promo kod bo'lsa kiriting (yoki '-' deb yozing):", reply_markup=cancel_kb())
        await state.set_state(OrderForm.promo)

@router.message(OrderForm.address)
async def checkout_address(message: types.Message, state: FSMContext):
    if message.location:
        addr = f"https://maps.google.com/?q={message.location.latitude},{message.location.longitude}"
    elif message.text == "✍️ Qo'lda yozish":
        await message.answer("Manzil:", reply_markup=cancel_kb())
        return
    else:
        addr = message.text
    await state.update_data(address=addr)
    await message.answer("🎟 Promo kod bo'lsa kiriting (yoki '-' deb yozing):", reply_markup=cancel_kb())
    await state.set_state(OrderForm.promo)

@router.message(OrderForm.promo)
async def checkout_promo(message: types.Message, state: FSMContext):
    if message.text.strip() == "-":
        await state.update_data(promo_code=None, discount=0)
    else:
        code = message.text.strip().upper()
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promo_codes WHERE code=? AND is_active=1 AND (expiry_date IS NULL OR expiry_date > CURRENT_TIMESTAMP) AND (usage_limit=-1 OR used_count<usage_limit)",
                (code,)
            ) as cur:
                promo = await cur.fetchone()
        if not promo:
            await message.answer("❌ Promo kod noto'g'ri yoki tugagan. Davom etish?", reply_markup=cancel_kb())
            return
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT c.quantity, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
                (message.from_user.id,)
            ) as cur:
                items = await cur.fetchall()
        tot = sum(i["price"] * i["quantity"] for i in items)
        disc = int(tot * promo["discount"] / 100) if promo["dtype"] == "percent" else promo["discount"]
        await state.update_data(promo_code=code, discount=disc)
        await message.answer(f"✅ Promo qabul! Chegirma: -{disc:,} so'm")
    
    await message.answer("📞 Telefon:", reply_markup=phone_kb())
    await state.set_state(OrderForm.phone)

@router.message(OrderForm.phone)
async def checkout_phone(message: types.Message, state: FSMContext):
    ph = message.contact.phone_number if message.contact else message.text.strip()
    await state.update_data(phone=ph)
    await _show_confirm(message, state)

async def _show_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.quantity, p.name, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
            (message.from_user.id,)
        ) as cur:
            items = await cur.fetchall()

    if not items:
        await state.clear()
        return await message.answer("Savat bo'sh!")

    tot = sum(i["price"] * i["quantity"] for i in items)
    disc = data.get("discount", 0)
    final = max(0, tot - disc)
    lines = "\n".join(f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,}" for i in items)
    addr = data["address"]
    addr_s = f'<a href="{addr}">📍 Lokatsiya</a>' if addr.startswith("http") else f"📍 {addr}"
    txt = f"📋 <b>Tasdiqlang:</b>\n\n{lines}\n\n💰 {tot:,}"
    if disc:
        txt += f" → <b>{final:,} so'm</b> (-{disc:,})"
    else:
        txt += f" = <b>{final:,} so'm</b>"
    txt += f"\n📞 {data['phone']}\n{addr_s}"

    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha", callback_data="confirm_order")
    b.button(text="❌ Yo'q", callback_data="cancel_order")
    await message.answer(txt, reply_markup=b.adjust(1).as_markup(), disable_web_page_preview=True)
    await state.set_state(OrderForm.confirm)

@router.callback_query(F.data == "cancel_order")
async def cancel_order(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer("Bekor qilindi.", reply_markup=await main_menu_kb(call.from_user.id))

@router.callback_query(OrderForm.confirm, F.data == "confirm_order")
async def order_confirm(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    u_id = call.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.quantity, p.id, p.price, p.name, p.stock FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?",
            (u_id,)
        ) as cur:
            items = await cur.fetchall()

        if not items:
            await call.answer("Savat bo'sh!", show_alert=True)
            await state.clear()
            return

        for i in items:
            if i["quantity"] > i["stock"]:
                return await call.answer(f"'{i['name']}' zaxira yetarli emas!", show_alert=True)

        tot = sum(i["price"] * i["quantity"] for i in items)
        disc = data.get("discount", 0)
        final = max(0, tot - disc)
        cancel_until = (datetime.now() + timedelta(hours=4)).isoformat()
        c = await db.execute(
            "INSERT INTO orders (user_id, phone, address, total, discount, promo_code, cancel_until) VALUES (?,?,?,?,?,?,?)",
            (u_id, data["phone"], data["address"], final, disc, data.get("promo_code"), cancel_until)
        )
        o_id = c.lastrowid
        for i in items:
            await db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?,?,?,?)",
                (o_id, i["id"], i["quantity"], i["price"])
            )
            await db.execute("UPDATE products SET sold=sold+1 WHERE id=?", (i["id"],))
        
        if data.get("promo_code"):
            await db.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE code=?", (data["promo_code"],))
        
        await db.execute("DELETE FROM cart WHERE user_id=?", (u_id,))
        await db.commit()

    pending_orders[o_id] = "Kutilmoqda"
    await state.clear()
    try:
        await call.message.delete()
    except:
        pass

    await call.message.answer(
        f"⏳ <b>Buyurtma №{o_id}</b> yuborildi!\n"
        f"Admin tasdiqlashini kuting.\n\n"
        f"⏲ <i>2 soat ichida bekor qilish imkoni bor.</i>",
        reply_markup=await main_menu_kb(u_id)
    )

    lines = "\n".join(f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,}" for i in items)
    addr = data["address"]
    addr_s = f'<a href="{addr}">📍</a>' if addr.startswith("http") else f"📍 {addr}"
    promo_txt = f"\n🎟 Promo: {data['promo_code']} (-{disc:,})" if data.get("promo_code") else ""
    await bot.send_message(
        SUPER_ADMIN,
        f"🆕 BUYURTMA #{o_id}\n\n{lines}\n\n💰 {final:,} so'm{promo_txt}\n📞 {data['phone']}\n{addr_s}",
        reply_markup=order_kb(o_id)
    )

# ═══════════════════════════════════════════════════════════════════════
#  BUYURTMALARIM + CANCEL + REVIEW
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 15",
            (message.from_user.id,)
        ) as cur:
            orders = await cur.fetchall()

    if not orders:
        return await message.answer("Buyurtma yo'q.")

    txt = "📦 <b>Buyurtmalaringiz:</b>\n\n"
    b = InlineKeyboardBuilder()
    for o in orders:
        icon = STATUS_ICON.get(o["status"], "❓")
        txt += f"{icon} <b>№{o['id']}</b> — {o['total']:,} so'm\n"
        txt += f"   {o['status']} | {str(o['created_at'])[:16]}\n"
        
        # Cancel qilish imkoni
        if o["status"] == "Kutilmoqda" and o["cancel_until"]:
            cancel_time = datetime.fromisoformat(o["cancel_until"])
            if datetime.now() < cancel_time:
                b.button(text=f"🛑 #{o['id']} bekor", callback_data=f"cancel_ord_{o['id']}")

        # Review qilish imkoni
        if o["status"] == "Yetkazildi":
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT COUNT(*) FROM reviews WHERE order_id=?", (o["id"],)) as cur:
                    rev_count = (await cur.fetchone())[0]
            if rev_count == 0:
                async with db.execute("SELECT COUNT(*) FROM order_items WHERE order_id=?", (o["id"],)) as cur:
                    item_count = (await cur.fetchone())[0]
                if item_count > 0:
                    b.button(text=f"⭐ #{o['id']} baho", callback_data=f"review_ord_{o['id']}")

        txt += "\n"

    kb = b.adjust(2).as_markup() if b.buttons else None
    await message.answer(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("cancel_ord_"))
async def cancel_order_do(call: types.CallbackQuery):
    o_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE orders SET status='Bekor qilindi' WHERE id=?", (o_id,))
        await db.commit()
    await call.answer("✅ Buyurtma bekor qilindi!")

@router.callback_query(F.data.startswith("review_ord_"))
async def review_order(call: types.CallbackQuery, state: FSMContext):
    o_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM order_items WHERE order_id=?", (o_id,)) as cur:
            items = await cur.fetchall()
    if not items:
        return await call.answer("Mahsulot yo'q")
    p = items[0]
    await state.update_data(order_id=o_id, product_id=p["product_id"])
    await call.message.answer(f"'{p['name']}' uchun baho (⭐⭐⭐):", reply_markup=stars_kb(o_id, p["product_id"]))
    await state.set_state(ReviewForm.rating)

@router.callback_query(ReviewForm.rating, F.data.startswith("rate_"))
async def review_rating(call: types.CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    rating = int(parts[3])
    await state.update_data(rating=rating)
    await call.message.answer("Izoh (yoki '-' deb yozing):", reply_markup=cancel_kb())
    await state.set_state(ReviewForm.comment)

@router.message(ReviewForm.comment)
async def review_comment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    comment = None if message.text.strip() == "-" else message.text
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO reviews (user_id, product_id, order_id, rating, comment) VALUES (?,?,?,?,?)",
                (message.from_user.id, data["product_id"], data["order_id"], data["rating"], comment)
            )
            await db.commit()
            await message.answer("✅ Rahmat!", reply_markup=await main_menu_kb(message.from_user.id))
        except:
            await message.answer("Siz allaqachon baho qo'ygan.", reply_markup=await main_menu_kb(message.from_user.id))
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════
@router.message(F.text == "⚙️ Admin")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("⚙️ Admin Panel:", reply_markup=admin_menu_kb())

# ── BO'LIMLAR ────────────────────────────────────────────────────────
@router.message(F.text == "📁 Bo'limlar")
async def cat_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Qo'shish", callback_data="cat_add")
    b.button(text="✏️ Tahrirlash", callback_data="cat_edit")
    b.button(text="🗑 O'chirish", callback_data="cat_del")
    b.adjust(2)
    await message.answer("📁 <b>Bo'limlar:</b>", reply_markup=b.as_markup())

@router.callback_query(F.data == "cat_add")
async def cat_add_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Bo'lim nomi:", reply_markup=cancel_kb())
    await state.set_state(AdminCategoryForm.name)

@router.message(AdminCategoryForm.name)
async def cat_add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Tavsif:")
    await state.set_state(AdminCategoryForm.description)

@router.message(AdminCategoryForm.description)
async def cat_add_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO categories (name, description) VALUES (?,?)",
                           (data["name"], message.text))
            await db.commit()
            await message.answer("✅ Bo'lim qo'shildi.", reply_markup=admin_menu_kb())
        except:
            await message.answer("❌ Xato!", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "cat_edit")
async def cat_edit_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    if not cats:
        return await call.message.answer("Bo'limlar yo'q.")
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c["name"], callback_data=f"cate_{c['id']}")
    b.adjust(2)
    await call.message.answer("Bo'lim tanlang:", reply_markup=b.as_markup())
    await state.set_state(AdminCategoryForm.name)

@router.callback_query(AdminCategoryForm.name, F.data.startswith("cate_"))
async def cat_edit_field(call: types.CallbackQuery, state: FSMContext):
    c_id = int(call.data.split("_")[1])
    await state.update_data(product_id=c_id)
    b = InlineKeyboardBuilder()
    b.button(text="📝 Nomi", callback_data="catf_name")
    b.button(text="📄 Tavsifi", callback_data="catf_desc")
    await call.message.answer("Maydon:", reply_markup=b.as_markup())
    await state.set_state(AdminEditForm.field)

@router.callback_query(AdminEditForm.field, F.data.startswith("catf_"))
async def cat_edit_get(call: types.CallbackQuery, state: FSMContext):
    field = call.data.split("_")[1]
    await state.update_data(field=field)
    await call.message.answer("Yangi qiymat:", reply_markup=cancel_kb())
    await state.set_state(AdminEditForm.new_value)

@router.message(AdminEditForm.new_value)
async def cat_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE categories SET {data['field']}=? WHERE id=?",
                       (message.text, data["product_id"]))
        await db.commit()
    await message.answer("✅ Yangilandi.", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "cat_del")
async def cat_del_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=f"🗑 {c['name']}", callback_data=f"catd_{c['id']}")
    b.adjust(2)
    await call.message.answer("⚠️ O'chirish:", reply_markup=b.as_markup())
    await state.set_state(AdminCategoryForm.description)

@router.callback_query(AdminCategoryForm.description, F.data.startswith("catd_"))
async def cat_del_do(call: types.CallbackQuery, state: FSMContext):
    c_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM categories WHERE id=?", (c_id,))
        await db.commit()
    await call.message.edit_text("✅ O'chirildi.")
    await state.clear()

# ── MAHSULOTLAR ──────────────────────────────────────────────────────
@router.message(F.text == "📦 Mahsulotlar")
async def prod_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Qo'shish", callback_data="prod_add")
    b.button(text="✏️ Tahrirlash", callback_data="prod_edit")
    b.button(text="🗑 O'chirish", callback_data="prod_del")
    b.adjust(2)
    await message.answer("📦 <b>Mahsulotlar:</b>", reply_markup=b.as_markup())

@router.callback_query(F.data == "prod_add")
async def prod_add_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    if not cats:
        return await call.message.answer("Bo'lim yarating!")
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c["name"], callback_data=f"pc_{c['id']}")
    b.adjust(2)
    await call.message.answer("Bo'lim:", reply_markup=b.as_markup())
    await state.set_state(AdminProductForm.category_id)

@router.callback_query(AdminProductForm.category_id, F.data.startswith("pc_"))
async def prod_add_cat(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_id=int(call.data.split("_")[1]))
    await call.message.answer("Nomi:", reply_markup=cancel_kb())
    await state.set_state(AdminProductForm.name)

@router.message(AdminProductForm.name)
async def prod_add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Tavsif:")
    await state.set_state(AdminProductForm.description)

@router.message(AdminProductForm.description)
async def prod_add_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Narx:")
    await state.set_state(AdminProductForm.price)

@router.message(AdminProductForm.price)
async def prod_add_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Raqam:")
    await state.update_data(price=int(message.text))
    await message.answer("Zaxira:")
    await state.set_state(AdminProductForm.stock)

@router.message(AdminProductForm.stock)
async def prod_add_stock(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Raqam:")
    await state.update_data(stock=int(message.text))
    b = InlineKeyboardBuilder()
    b.button(text="⏭ Skip", callback_data="skip_ph")
    await call.message.answer("Rasm:", reply_markup=b.as_markup())
    await state.set_state(AdminProductForm.photo)

@router.callback_query(AdminProductForm.photo, F.data == "skip_ph")
async def prod_add_save(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO products (category_id, name, description, price, stock) VALUES (?,?,?,?,?)",
            (data["category_id"], data["name"], data["description"], data["price"], data["stock"])
        )
        await db.commit()
    await call.message.answer("✅ Mahsulot qo'shildi.", reply_markup=admin_menu_kb())
    await state.clear()

@router.message(AdminProductForm.photo)
async def prod_add_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Rasm yuboring:")
    data = await state.get_data()
    ph = message.photo[-1].file_id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO products (category_id, name, description, price, stock, photo_id) VALUES (?,?,?,?,?,?)",
            (data["category_id"], data["name"], data["description"], data["price"], data["stock"], ph)
        )
        await db.commit()
    await message.answer("✅ Mahsulot qo'shildi.", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "prod_edit")
async def prod_edit_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products") as cur:
            prods = await cur.fetchall()
    if not prods:
        return await call.message.answer("Mahsulot yo'q.")
    b = InlineKeyboardBuilder()
    for p in prods:
        b.button(text=p["name"][:20], callback_data=f"pe_{p['id']}")
    b.adjust(2)
    await call.message.answer("Mahsulot:", reply_markup=b.as_markup())
    await state.set_state(AdminProductForm.product_id)

@router.callback_query(AdminProductForm.product_id, F.data.startswith("pe_"))
async def prod_edit_field(call: types.CallbackQuery, state: FSMContext):
    p_id = int(call.data.split("_")[1])
    await state.update_data(product_id=p_id)
    b = InlineKeyboardBuilder()
    b.button(text="📝 Nomi", callback_data="pef_name")
    b.button(text="📄 Tavsifi", callback_data="pef_desc")
    b.button(text="💰 Narxi", callback_data="pef_price")
    b.button(text="📦 Zaxira", callback_data="pef_stock")
    b.adjust(2)
    await call.message.answer("Maydon:", reply_markup=b.as_markup())
    await state.set_state(AdminEditForm.field)

@router.callback_query(AdminEditForm.field, F.data.startswith("pef_"))
async def prod_edit_get(call: types.CallbackQuery, state: FSMContext):
    field = call.data.split("_")[1]
    await state.update_data(field=field)
    await call.message.answer("Yangi qiymat:", reply_markup=cancel_kb())
    await state.set_state(AdminEditForm.new_value)

@router.message(AdminEditForm.new_value)
async def prod_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["field"]
    value = int(message.text) if field in ("price", "stock") and message.text.isdigit() else message.text
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, data["product_id"]))
        await db.commit()
    await message.answer("✅ Yangilandi.", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "prod_del")
async def prod_del_start(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products") as cur:
            prods = await cur.fetchall()
    b = InlineKeyboardBuilder()
    for p in prods:
        b.button(text=f"🗑 {p['name'][:15]}", callback_data=f"pd_{p['id']}")
    b.adjust(2)
    await call.message.answer("Mahsulot:", reply_markup=b.as_markup())
    await state.set_state(AdminProductForm.product_id)

@router.callback_query(AdminProductForm.product_id, F.data.startswith("pd_"))
async def prod_del_do(call: types.CallbackQuery, state: FSMContext):
    p_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM products WHERE id=?", (p_id,))
        await db.commit()
    await call.message.edit_text("✅ O'chirildi.")
    await state.clear()

# ── BUYURTMALAR ──────────────────────────────────────────────────────
@router.message(F.text == "📋 Buyurtmalar")
async def admin_orders(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20") as cur:
            orders = await cur.fetchall()
    if not orders:
        return await message.answer("Buyurtma yo'q.")
    txt = "📋 <b>Oxirgi 20:</b>\n\n"
    b = InlineKeyboardBuilder()
    for o in orders:
        icon = STATUS_ICON.get(o["status"], "❓")
        txt += f"{icon} <b>#{o['id']}</b> — {o['total']:,}\n"
        if o["status"] == "Kutilmoqda":
            b.button(text=f"#{o['id']}", callback_data=f"ord_view_{o['id']}")
    kb = b.adjust(5).as_markup() if b.buttons else None
    await message.answer(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("ord_"))
async def order_action(call: types.CallbackQuery, bot: Bot):
    if call.data.startswith("ord_view_"):
        o_id = int(call.data.split("_")[2])
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE id=?", (o_id,)) as cur:
                order = await cur.fetchone()
            async with db.execute("SELECT oi.quantity, oi.price, p.name FROM order_items oi LEFT JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (o_id,)) as cur:
                items = await cur.fetchall()
        lines = "\n".join(f"▪️ {i['name'] or '?'} x{i['quantity']}" for i in items)
        addr_s = f"<a href='{order['address']}'>📍</a>" if order['address'].startswith("http") else f"📍 {order['address']}"
        txt = f"#{o_id}\n{lines}\n💰 {order['total']:,}\n📞 {order['phone']}\n{addr_s}"
        await call.message.answer(txt, reply_markup=order_kb(o_id), disable_web_page_preview=True)
    else:
        parts = call.data.split("_")
        action = parts[1]
        o_id = int(parts[2])
        status_map = {"app": "Tasdiqlandi", "rej": "Rad etildi", "del": "Yo'lda", "done": "Yetkazildi"}
        new_status = status_map.get(action, "")
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE id=?", (o_id,)) as cur:
                order = await cur.fetchone()
            await db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, o_id))
            if action == "app":
                async with db.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?", (o_id,)) as cur:
                    for row in await cur.fetchall():
                        await db.execute("UPDATE products SET stock=MAX(0,stock-?) WHERE id=?", (row["quantity"], row["product_id"]))
            await db.commit()
        pending_orders[o_id] = new_status
        icon = STATUS_ICON.get(new_status, "")
        await call.message.edit_text(f"{icon} #{o_id} → {new_status}", reply_markup=order_kb(o_id))
        try:
            await bot.send_message(order["user_id"], f"{icon} Buyurtma #{o_id}: {new_status}")
        except:
            pass

# ── PROMO KODLAR ──────────────────────────────────────────────────────
@router.message(F.text == "🎟 Promo Kodlar")
async def promo_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Qo'shish", callback_data="promo_add")
    b.button(text="📋 Ro'yxat", callback_data="promo_list")
    b.adjust(2)
    await message.answer("🎟 <b>Promo Kodlar:</b>", reply_markup=b.as_markup())

@router.callback_query(F.data == "promo_add")
async def promo_add_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kod (masalan: SALE30):", reply_markup=cancel_kb())
    await state.set_state(AdminPromoForm.code)

@router.message(AdminPromoForm.code)
async def promo_add_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.upper())
    b = InlineKeyboardBuilder()
    b.button(text="%", callback_data="pt_p")
    b.button(text="So'm", callback_data="pt_a")
    await message.answer("Turi:", reply_markup=b.as_markup())
    await state.set_state(AdminPromoForm.dtype)

@router.callback_query(AdminPromoForm.dtype, F.data.startswith("pt_"))
async def promo_add_type(call: types.CallbackQuery, state: FSMContext):
    dtype = "percent" if call.data == "pt_p" else "amount"
    await state.update_data(dtype=dtype)
    await call.message.answer("Miqdor:", reply_markup=cancel_kb())
    await state.set_state(AdminPromoForm.discount)

@router.message(AdminPromoForm.discount)
async def promo_add_discount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Raqam:")
    await state.update_data(discount=int(message.text))
    await message.answer("Muddati (soatda, yoki '-' = cheksiz):", reply_markup=cancel_kb())
    await state.set_state(AdminPromoForm.expiry)

@router.message(AdminPromoForm.expiry)
async def promo_add_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    expiry = None
    if message.text != "-":
        try:
            hours = int(message.text)
            expiry = (datetime.now() + timedelta(hours=hours)).isoformat()
        except:
            return await message.answer("❌ Raqam:")
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO promo_codes (code, discount, dtype, expiry_date) VALUES (?,?,?,?)",
                (data["code"], data["discount"], data["dtype"], expiry)
            )
            await db.commit()
            await message.answer("✅ Kod qo'shildi.", reply_markup=admin_menu_kb())
        except:
            await message.answer("❌ Kod mavjud!", reply_markup=admin_menu_kb())
    await state.clear()

@router.callback_query(F.data == "promo_list")
async def promo_list(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes") as cur:
            promos = await cur.fetchall()
    if not promos:
        return await call.message.answer("Kod yo'q.")
    txt = "🎟 <b>Kodlar:</b>\n\n"
    for p in promos:
        dtype = "%" if p["dtype"] == "percent" else "so'm"
        txt += f"<b>{p['code']}</b> — -{p['discount']}{dtype}\n"
    await call.message.answer(txt)

# ── DASHBOARD ────────────────────────────────────────────────────────
@router.message(F.text == "📊 Dashboard")
async def dashboard(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c: users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders") as c: orders = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(total) FROM orders WHERE status='Yetkazildi'") as c:
            rev = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status='Kutilmoqda'") as c: pend = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM products") as c: prods = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM reviews") as c: revs = (await c.fetchone())[0]
    await message.answer(
        f"📊 <b>Dashboard</b>\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"📦 Mahsulotlar: {prods}\n"
        f"🛒 Buyurtmalar: {orders} ({pend} kutilmoqda)\n"
        f"💰 Daromad: {rev:,} so'm\n"
        f"⭐ Baholangan: {revs} ta"
    )

# ── XABAR TARQATISH ──────────────────────────────────────────────────
@router.message(F.text == "📢 Xabar tarqatish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Xabar:", reply_markup=cancel_kb())
    await state.set_state(AdminBroadcast.msg)

@router.message(AdminBroadcast.msg)
async def broadcast_send(message: types.Message, state: FSMContext, bot: Bot):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = await cur.fetchall()
    sent = 0
    for (uid,) in users:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"📢 {sent} ta yuborildi.", reply_markup=admin_menu_kb())
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 PROFESSIONAL SHOP BOT ISHGA TUSHDI!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
