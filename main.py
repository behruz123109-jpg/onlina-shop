import asyncio
import logging
import aiosqlite
import math
from os import getenv
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton


load_dotenv()
# ==================== 1. SOZLAMALAR (CONFIG) ====================
API_TOKEN = getenv("8041760588:AAFLJi1Lg7Oo_1JE5bHsRrUO6k-vp-EWa9w")
SUPER_ADMIN = 8488028783
DB_NAME = "shop.db"

router = Router()
pending_orders = {}

# ==================== 2. HOLATLAR (FSM) ====================
class AdminCategory(StatesGroup):
    name = State()

class AdminProduct(StatesGroup):
    category_id = State()
    name = State()
    description = State()
    price = State()
    stock = State()
    photo = State()

class AdminEdit(StatesGroup):
    product_id = State()
    choose_field = State()
    new_value = State()

class AdminDelete(StatesGroup):
    product_id = State()

class AdminBroadcast(StatesGroup):
    msg = State()

class OrderFSM(StatesGroup):
    phone = State()
    location = State()
    address = State()
    confirm = State()

class SuperAdminState(StatesGroup):
    new_admin_id = State()

# ==================== 3. MA'LUMOTLAR BAZASI (DATABASE) ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                photo_id TEXT,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone TEXT,
                address TEXT,
                total INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Kutilmoqda',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price INTEGER NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )
        """)
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)) as cur:
            return bool(await cur.fetchone())

# ==================== 4. TUGMALAR (KEYBOARDS) ====================
async def main_menu_kb(user_id):
    b = ReplyKeyboardBuilder()
    b.button(text="🛍 Katalog")
    b.button(text="🛒 Savatcha")
    b.button(text="📦 Buyurtmalarim")
    if await is_admin(user_id):
        b.button(text="⚙️ Admin Panel")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def admin_menu_kb(user_id):
    b = ReplyKeyboardBuilder()
    b.button(text="📁 Bo'lim qo'shish")
    b.button(text="➕ Mahsulot qo'shish")
    b.button(text="✏️ Mahsulot tahrirlash")
    b.button(text="🗑 Mahsulot o'chirish")
    b.button(text="📋 Barcha buyurtmalar")
    b.button(text="📢 Xabar tarqatish")
    if user_id == SUPER_ADMIN:
        b.button(text="👮‍♂️ Admin qo'shish")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def skip_photo_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ O'tkazib yuborish")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def location_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Manzilni yuborish", request_location=True)],
            [KeyboardButton(text="✍️ Qo'lda yozish")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def admin_confirm_kb(order_id):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"approve_{order_id}")
    b.button(text="❌ Rad etish", callback_data=f"reject_{order_id}")
    return b.adjust(2).as_markup()

# ==================== 5. GLOBAL VA START HANDLERS ====================
@router.message(F.text == "❌ Bekor qilish", StateFilter("*"))
async def cancel_all(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🛑 Bekor qilindi.", reply_markup=await main_menu_kb(message.from_user.id))

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)",
            (message.from_user.id, message.from_user.full_name)
        )
        await db.commit()
    await message.answer(
        f"Assalomu alaykum <b>{message.from_user.full_name}</b>! 🌟\nXush kelibsiz!",
        reply_markup=await main_menu_kb(message.from_user.id)
    )

@router.message(F.text == "🏠 Asosiy menyu")
async def home_btn(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=await main_menu_kb(message.from_user.id))

# ==================== 6. ADMIN TASDIQLASH ====================
async def order_reminder(bot: Bot, order_id: int):
    await asyncio.sleep(300)
    if order_id in pending_orders and pending_orders[order_id] == "Kutilmoqda":
        try:
            await bot.send_message(
                SUPER_ADMIN,
                f"⚠️ <b>ESLATMA!</b>\nBuyurtma №{order_id} hali tasdiqlanmadi!"
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def admin_decision(call: types.CallbackQuery, bot: Bot):
    parts = call.data.split("_", 1)
    action = parts[0]
    o_id = int(parts[1])

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (o_id,)) as cur:
            order = await cur.fetchone()

        if not order:
            return await call.answer("Buyurtma topilmadi!")

        if action == "approve":
            await db.execute("UPDATE orders SET status='Tasdiqlandi' WHERE id=?", (o_id,))
            async with db.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?", (o_id,)) as items_cur:
                items = await items_cur.fetchall()
            for i in items:
                await db.execute("UPDATE products SET stock=stock-? WHERE id=?", (i['quantity'], i['product_id']))
            await db.commit()
            pending_orders[o_id] = "Tasdiqlandi"
            await call.message.edit_text(f"✅ Buyurtma №{o_id} tasdiqlandi.")
            try:
                await bot.send_message(
                    order['user_id'],
                    f"🎉 <b>Xushxabar!</b>\nBuyurtma №{o_id} tasdiqlandi! Tez orada yetkazamiz."
                )
            except Exception:
                pass
        else:
            await db.execute("UPDATE orders SET status='Rad etildi' WHERE id=?", (o_id,))
            pending_orders[o_id] = "Rad etildi"
            await db.commit()
            await call.message.edit_text(f"❌ Buyurtma №{o_id} rad etildi.")
            try:
                await bot.send_message(
                    order['user_id'],
                    f"😔 <b>Uzr!</b>\nBuyurtma №{o_id} rad etildi."
                )
            except Exception:
                pass

# ==================== 7. FOYDALANUVCHI: BUYURTMALARIM ====================
@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (message.from_user.id,)
        ) as cur:
            orders = await cur.fetchall()

    if not orders:
        return await message.answer("Sizda hali buyurtmalar yo'q.")

    txt = "📦 <b>Sizning buyurtmalaringiz:</b>\n\n"
    for o in orders:
        status_icon = {"Kutilmoqda": "⏳", "Tasdiqlandi": "✅", "Rad etildi": "❌"}.get(o['status'], "❓")
        txt += f"{status_icon} <b>№{o['id']}</b> — {o['total']:,} so'm — {o['status']}\n"
        txt += f"   📅 {o['created_at'][:16]}\n\n"

    await message.answer(txt)

# ==================== 8. KATALOG (PAGINATION) ====================
@router.message(F.text == "🛍 Katalog")
async def show_user_catalog(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()

    if not cats:
        return await message.answer("Hozircha bo'limlar mavjud emas.")

    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c['name'], callback_data=f"ucat_{c['id']}_0")
    b.adjust(2)
    await message.answer("📂 Bo'limni tanlang:", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("ucat_"))
async def user_pagination(call: types.CallbackQuery):
    parts = call.data.split("_")
    c_id, page = int(parts[1]), int(parts[2])
    limit = 2

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE category_id=? AND stock>0", (c_id,)
        ) as cur:
            all_prods = await cur.fetchall()

    if not all_prods:
        return await call.answer("Bu bo'limda mahsulot yo'q.", show_alert=True)

    total_pages = math.ceil(len(all_prods) / limit)
    start = page * limit
    current_prods = all_prods[start: start + limit]

    text = f"📦 <b>Mahsulotlar ({page+1}/{total_pages}):</b>\n\n"
    b = InlineKeyboardBuilder()

    for p in current_prods:
        text += f"🔹 <b>{p['name']}</b>\n💬 {p['description'] or ''}\n💰 {p['price']:,} so'm | 📦 Zaxira: {p['stock']}\n\n"
        b.button(text=f"🛒 {p['name'][:15]}", callback_data=f"uadd_{p['id']}")

    b.adjust(1)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"ucat_{c_id}_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"ucat_{c_id}_{page+1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="uback_cats"))

    try:
        await call.message.edit_text(text, reply_markup=b.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=b.as_markup())

@router.callback_query(F.data == "uback_cats")
async def uback_cats(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()

    if not cats:
        return await call.message.edit_text("Bo'limlar yo'q.")

    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c['name'], callback_data=f"ucat_{c['id']}_0")
    b.adjust(2)
    await call.message.edit_text("📂 Bo'limni tanlang:", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("uadd_"))
async def add_to_cart(call: types.CallbackQuery):
    p_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id FROM cart WHERE user_id=? AND product_id=?",
            (call.from_user.id, p_id)
        ) as cur:
            res = await cur.fetchone()
        if res:
            await db.execute(
                "UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?",
                (call.from_user.id, p_id)
            )
        else:
            await db.execute(
                "INSERT INTO cart (user_id, product_id) VALUES (?, ?)",
                (call.from_user.id, p_id)
            )
        await db.commit()
    await call.answer("Savatga qo'shildi! 🛒")

# ==================== 9. SAVATCHA ====================
@router.message(F.text == "🛒 Savatcha")
async def view_cart(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.id, c.quantity, p.name, p.price
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.user_id=?
        """, (message.from_user.id,)) as cur:
            items = await cur.fetchall()

    if not items:
        return await message.answer("🛒 Savatingiz bo'sh.")

    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    b = InlineKeyboardBuilder()
    for i in items:
        tot += i['price'] * i['quantity']
        txt += f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,} so'm\n"
        b.button(text=f"🗑 {i['name'][:12]}", callback_data=f"cdel_{i['id']}")

    txt += f"\n💰 Jami: <b>{tot:,} so'm</b>"
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout"),
        InlineKeyboardButton(text="🗑 Tozalash", callback_data="cclear")
    )
    await message.answer(txt, reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("cdel_"))
async def cart_delete_item(call: types.CallbackQuery):
    cart_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE id=? AND user_id=?", (cart_id, call.from_user.id))
        await db.commit()
    await call.answer("O'chirildi.")
    # Savatchani yangilash
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.id, c.quantity, p.name, p.price
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.user_id=?
        """, (call.from_user.id,)) as cur:
            items = await cur.fetchall()

    if not items:
        await call.message.edit_text("🛒 Savatingiz bo'sh.")
        return

    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    b = InlineKeyboardBuilder()
    for i in items:
        tot += i['price'] * i['quantity']
        txt += f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,} so'm\n"
        b.button(text=f"🗑 {i['name'][:12]}", callback_data=f"cdel_{i['id']}")

    txt += f"\n💰 Jami: <b>{tot:,} so'm</b>"
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout"),
        InlineKeyboardButton(text="🗑 Tozalash", callback_data="cclear")
    )
    await call.message.edit_text(txt, reply_markup=b.as_markup())

@router.callback_query(F.data == "cclear")
async def cclear(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE user_id=?", (call.from_user.id,))
        await db.commit()
    await call.message.edit_text("🗑 Savatcha tozalandi.")

# ==================== 10. BUYURTMA BERISH (CHECKOUT) ====================
@router.callback_query(F.data == "checkout")
async def checkout_step1(call: types.CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer("📞 Telefon raqamingizni yuboring:", reply_markup=phone_kb())
    await state.set_state(OrderFSM.phone)

@router.message(OrderFSM.phone)
async def checkout_step2(message: types.Message, state: FSMContext):
    if message.contact:
        ph = message.contact.phone_number
    elif message.text and message.text != "❌ Bekor qilish":
        ph = message.text
    else:
        return
    await state.update_data(phone=ph)
    await message.answer("📍 Manzilingizni yuboring:", reply_markup=location_kb())
    await state.set_state(OrderFSM.location)

@router.message(OrderFSM.location)
async def checkout_step3(message: types.Message, state: FSMContext):
    if message.location:
        loc = f"https://maps.google.com/?q={message.location.latitude},{message.location.longitude}"
        await state.update_data(address=loc)
        await show_final_confirm(message, state)
    elif message.text == "✍️ Qo'lda yozish":
        await message.answer(
            "Manzilingizni kiriting:",
            reply_markup=cancel_kb()
        )
        await state.set_state(OrderFSM.address)
    elif message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=await main_menu_kb(message.from_user.id))

@router.message(OrderFSM.address)
async def checkout_step3_manual(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await show_final_confirm(message, state)

async def show_final_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.quantity, p.name, p.price
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.user_id=?
        """, (message.from_user.id,)) as cur:
            items = await cur.fetchall()

    if not items:
        await message.answer("Savat bo'sh!", reply_markup=await main_menu_kb(message.from_user.id))
        await state.clear()
        return

    tot = sum(i['price'] * i['quantity'] for i in items)
    items_txt = "\n".join([f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,} so'm" for i in items])
    txt = (
        f"📋 <b>Buyurtmani tasdiqlang:</b>\n\n"
        f"{items_txt}\n\n"
        f"💰 Jami: <b>{tot:,} so'm</b>\n"
        f"📞 Tel: {data['phone']}\n"
        f"📍 Manzil: {data['address']}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlayman", callback_data="fconf")
    b.button(text="❌ Bekor qilish", callback_data="cancel_checkout")
    await message.answer(txt, reply_markup=b.adjust(1).as_markup(), disable_web_page_preview=True)
    await state.set_state(OrderFSM.confirm)

@router.callback_query(F.data == "cancel_checkout")
async def cancel_checkout(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Bekor qilindi.", reply_markup=await main_menu_kb(call.from_user.id))

@router.callback_query(OrderFSM.confirm, F.data == "fconf")
async def order_final(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    u_id = call.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.quantity, p.id, p.price, p.name, p.stock
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.user_id=?
        """, (u_id,)) as cur:
            itms = await cur.fetchall()

        if not itms:
            await call.answer("Savat bo'sh!", show_alert=True)
            await state.clear()
            return

        # Zaxira tekshirish
        for i in itms:
            if i['quantity'] > i['stock']:
                await call.answer(f"'{i['name']}' mahsulotidan yetarli zaxira yo'q!", show_alert=True)
                return

        tot = sum(i['price'] * i['quantity'] for i in itms)
        c = await db.execute(
            "INSERT INTO orders (user_id, phone, address, total) VALUES (?,?,?,?)",
            (u_id, data['phone'], data['address'], tot)
        )
        o_id = c.lastrowid
        for i in itms:
            await db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?,?,?,?)",
                (o_id, i['id'], i['quantity'], i['price'])
            )
        await db.execute("DELETE FROM cart WHERE user_id=?", (u_id,))
        await db.commit()

    pending_orders[o_id] = "Kutilmoqda"
    await state.clear()
    await call.message.delete()
    await call.message.answer(
        f"⏳ Buyurtma №{o_id} yuborildi. Admin tasdiqlashini kuting!",
        reply_markup=await main_menu_kb(u_id)
    )

    items_txt = "\n".join([f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,} so'm" for i in itms])
    addr_line = f"<a href='{data['address']}'>Manzil</a>" if data['address'].startswith("http") else data['address']
    await bot.send_message(
        SUPER_ADMIN,
        f"🆕 <b>YANGI BUYURTMA #{o_id}</b>\n\n{items_txt}\n\n💰 Jami: {tot:,} so'm\n📞 {data['phone']}\n📍 {addr_line}",
        reply_markup=admin_confirm_kb(o_id)
    )
    asyncio.create_task(order_reminder(bot, o_id))

# ==================== 11. ADMIN PANEL ====================
@router.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        return await message.answer("Ruxsat yo'q.")
    await message.answer("⚙️ Admin panel:", reply_markup=admin_menu_kb(message.from_user.id))

# --- BO'LIM QO'SHISH ---
@router.message(F.text == "📁 Bo'lim qo'shish")
async def admin_cat_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Yangi bo'lim nomini yozing:", reply_markup=cancel_kb())
    await state.set_state(AdminCategory.name)

@router.message(AdminCategory.name)
async def admin_cat_save(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO categories (name) VALUES (?)", (message.text,))
            await db.commit()
            await message.answer("✅ Bo'lim qo'shildi.", reply_markup=admin_menu_kb(message.from_user.id))
        except Exception:
            await message.answer("❌ Bu nom allaqachon mavjud!", reply_markup=admin_menu_kb(message.from_user.id))
    await state.clear()

# --- MAHSULOT QO'SHISH ---
@router.message(F.text == "➕ Mahsulot qo'shish")
async def admin_prod_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur:
            cats = await cur.fetchall()
    if not cats:
        return await message.answer("Avval bo'lim yarating!")
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c['name'], callback_data=f"setcat_{c['id']}")
    b.adjust(2)
    await message.answer("Bo'limni tanlang:", reply_markup=b.as_markup())
    await state.set_state(AdminProduct.category_id)

@router.callback_query(AdminProduct.category_id, F.data.startswith("setcat_"))
async def admin_prod_cat(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_id=int(call.data.split("_")[1]))
    await call.message.answer("Mahsulot nomini yozing:", reply_markup=cancel_kb())
    await state.set_state(AdminProduct.name)

@router.message(AdminProduct.name)
async def admin_prod_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Tavsifini yozing:")
    await state.set_state(AdminProduct.description)

@router.message(AdminProduct.description)
async def admin_prod_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Narxini kiriting (so'mda):")
    await state.set_state(AdminProduct.price)

@router.message(AdminProduct.price)
async def admin_prod_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat son kiriting:")
    await state.update_data(price=int(message.text))
    await message.answer("Zaxira miqdorini kiriting:")
    await state.set_state(AdminProduct.stock)

@router.message(AdminProduct.stock)
async def admin_prod_stock(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat son kiriting:")
    await state.update_data(stock=int(message.text))
    await message.answer("Rasm yuboring yoki o'tkazib yuboring:", reply_markup=skip_photo_kb())
    await state.set_state(AdminProduct.photo)

@router.message(AdminProduct.photo)
async def admin_prod_photo(message: types.Message, state: FSMContext):
    if message.text == "⏭ O'tkazib yuborish":
        ph = None
    elif message.photo:
        ph = message.photo[-1].file_id
    else:
        return await message.answer("Rasm yuboring yoki o'tkazib yuboring:", reply_markup=skip_photo_kb())

    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO products (category_id, name, description, price, stock, photo_id) VALUES (?,?,?,?,?,?)",
            (data['category_id'], data['name'], data['description'], data['price'], data['stock'], ph)
        )
        await db.commit()
    await message.answer("✅ Mahsulot qo'shildi!", reply_markup=admin_menu_kb(message.from_user.id))
    await state.clear()

# --- MAHSULOT TAHRIRLASH ---
@router.message(F.text == "✏️ Mahsulot tahrirlash")
async def admin_edit_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name FROM products") as cur:
            prods = await cur.fetchall()
    if not prods:
        return await message.answer("Mahsulotlar yo'q.")
    b = InlineKeyboardBuilder()
    for p in prods:
        b.button(text=p['name'], callback_data=f"edit_pid_{p['id']}")
    b.adjust(2)
    await message.answer("Tahrirlash uchun mahsulot tanlang:", reply_markup=b.as_markup())
    await state.set_state(AdminEdit.product_id)

@router.callback_query(AdminEdit.product_id, F.data.startswith("edit_pid_"))
async def admin_edit_choose_field(call: types.CallbackQuery, state: FSMContext):
    p_id = int(call.data.split("_")[2])
    await state.update_data(product_id=p_id)
    b = InlineKeyboardBuilder()
    for field in ["name", "description", "price", "stock"]:
        labels = {"name": "Nomi", "description": "Tavsif", "price": "Narx", "stock": "Zaxira"}
        b.button(text=labels[field], callback_data=f"edit_field_{field}")
    b.adjust(2)
    await call.message.answer("Qaysi maydonni tahrirlash?", reply_markup=b.as_markup())
    await state.set_state(AdminEdit.choose_field)

@router.callback_query(AdminEdit.choose_field, F.data.startswith("edit_field_"))
async def admin_edit_get_value(call: types.CallbackQuery, state: FSMContext):
    field = call.data.split("_")[2]
    await state.update_data(choose_field=field)
    await call.message.answer(f"Yangi qiymatni kiriting:", reply_markup=cancel_kb())
    await state.set_state(AdminEdit.new_value)

@router.message(AdminEdit.new_value)
async def admin_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data['choose_field']
    value = int(message.text) if field in ("price", "stock") and message.text.isdigit() else message.text

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, data['product_id']))
        await db.commit()
    await message.answer("✅ Yangilandi.", reply_markup=admin_menu_kb(message.from_user.id))
    await state.clear()

# --- MAHSULOT O'CHIRISH ---
@router.message(F.text == "🗑 Mahsulot o'chirish")
async def admin_delete_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name FROM products") as cur:
            prods = await cur.fetchall()
    if not prods:
        return await message.answer("Mahsulotlar yo'q.")
    b = InlineKeyboardBuilder()
    for p in prods:
        b.button(text=p['name'], callback_data=f"del_pid_{p['id']}")
    b.adjust(2)
    await message.answer("O'chirish uchun mahsulot tanlang:", reply_markup=b.as_markup())
    await state.set_state(AdminDelete.product_id)

@router.callback_query(AdminDelete.product_id, F.data.startswith("del_pid_"))
async def admin_delete_confirm(call: types.CallbackQuery, state: FSMContext):
    p_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM products WHERE id=?", (p_id,))
        await db.commit()
    await call.message.answer("✅ Mahsulot o'chirildi.", reply_markup=admin_menu_kb(call.from_user.id))
    await state.clear()

# --- BARCHA BUYURTMALAR ---
@router.message(F.text == "📋 Barcha buyurtmalar")
async def admin_all_orders(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20") as cur:
            orders = await cur.fetchall()
    if not orders:
        return await message.answer("Buyurtmalar yo'q.")
    txt = "📋 <b>Barcha buyurtmalar (oxirgi 20):</b>\n\n"
    for o in orders:
        status_icon = {"Kutilmoqda": "⏳", "Tasdiqlandi": "✅", "Rad etildi": "❌"}.get(o['status'], "❓")
        txt += f"{status_icon} <b>№{o['id']}</b> | {o['total']:,} so'm | {o['status']}\n"
        txt += f"   📞 {o['phone']} | 📅 {o['created_at'][:16]}\n\n"
    await message.answer(txt)

# --- XABAR TARQATISH ---
@router.message(F.text == "📢 Xabar tarqatish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Tarqatmoqchi bo'lgan xabaringizni yozing:", reply_markup=cancel_kb())
    await state.set_state(AdminBroadcast.msg)

@router.message(AdminBroadcast.msg)
async def broadcast_send(message: types.Message, state: FSMContext, bot: Bot):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = await cur.fetchall()

    sent, failed = 0, 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, message.text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Xabar yuborildi.\n✅ Muvaffaqiyatli: {sent}\n❌ Xato: {failed}",
        reply_markup=admin_menu_kb(message.from_user.id)
    )
    await state.clear()

# --- ADMIN QO'SHISH (faqat SUPER_ADMIN) ---
@router.message(F.text == "👮‍♂️ Admin qo'shish")
async def add_admin_start(message: types.Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN:
        return
    await message.answer("Yangi admin user_id raqamini kiriting:", reply_markup=cancel_kb())
    await state.set_state(SuperAdminState.new_admin_id)

@router.message(SuperAdminState.new_admin_id)
async def add_admin_save(message: types.Message, state: FSMContext):
    if not message.text.lstrip("-").isdigit():
        return await message.answer("❌ Noto'g'ri ID format. Qayta kiriting:")
    new_id = int(message.text)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
        await db.commit()
    await message.answer(f"✅ {new_id} admin qilib tayinlandi.", reply_markup=admin_menu_kb(message.from_user.id))
    await state.clear()

# ==================== 12. MAIN ====================
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 BOT ISHGA TUSHDI!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
