import asyncio
import logging
import aiosqlite
import math
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton

# ==================== 1. SOZLAMALAR ====================
API_TOKEN = "8041760588:AAFLJi1Lg7Oo_1JE5bHsRrUO6k-vp-EWa9w"
SUPER_ADMIN = 8488028783  
DB_NAME = "shop.db"

router = Router()
pending_orders = {} # {order_id: status}

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
    del_admin_id = State()

# ==================== 3. DATABASE ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL,
                name TEXT NOT NULL, description TEXT, price INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0, photo_id TEXT,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id), FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, phone TEXT,
                address TEXT, total INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Kutilmoqda',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, price INTEGER NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )
        """)
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN: return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)) as cur:
            res = await cur.fetchone()
            return bool(res)

# ==================== 4. KEYBOARDS ====================
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
    b.button(text="🗑 Bo'lim o'chirish")
    b.button(text="➕ Mahsulot qo'shish")
    b.button(text="✏️ Mahsulot tahrirlash")
    b.button(text="🗑 Mahsulot o'chirish")
    b.button(text="📋 Barcha buyurtmalar")
    b.button(text="📢 Xabar tarqatish")
    if user_id == SUPER_ADMIN:
        b.button(text="👮‍♂️ Admin qo'shish")
        b.button(text="👮‍♂️ Admin o'chirish")
    b.button(text="🏠 Asosiy menyu")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

def skip_photo_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏭ O'tkazib yuborish")],[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

# ==================== 5. GLOBAL HANDLERS ====================
@router.message(F.text == "❌ Bekor qilish", StateFilter("*"))
async def cancel_all(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🛑 Bekor qilindi.", reply_markup=await main_menu_kb(message.from_user.id))

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (message.from_user.id, message.from_user.full_name))
        await db.commit()
    await message.answer(f"Assalomu alaykum <b>{message.from_user.full_name}</b>! 🌟\nDo'konimizga xush kelibsiz!", reply_markup=await main_menu_kb(message.from_user.id))

@router.message(F.text == "🏠 Asosiy menyu")
async def go_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=await main_menu_kb(message.from_user.id))

# ==================== 6. ADMIN TASDIQLASH VA REMINDER ====================
async def order_reminder(bot: Bot, order_id: int):
    await asyncio.sleep(300)
    if order_id in pending_orders and pending_orders[order_id] == "Kutilmoqda":
        try:
            await bot.send_message(SUPER_ADMIN, f"⚠️ <b>ESLATMA!</b>\n№{order_id} buyurtma hali kutilmoqda!")
        except: pass

@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def admin_decision(call: types.CallbackQuery, bot: Bot):
    action, o_id = call.data.split("_")
    o_id = int(o_id)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (o_id,)) as cur:
            order = await cur.fetchone()
        if not order: return await call.answer("Topilmadi!")

        if action == "approve":
            await db.execute("UPDATE orders SET status='Tasdiqlandi' WHERE id=?", (o_id,))
            async with db.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?", (o_id,)) as it_cur:
                items = await it_cur.fetchall()
                for i in items:
                    await db.execute("UPDATE products SET stock=stock-? WHERE id=?", (i['quantity'], i['product_id']))
            await db.commit()
            pending_orders[o_id] = "Tasdiqlandi"
            await call.message.edit_text(f"✅ №{o_id} tasdiqlandi.")
            try: await bot.send_message(order['user_id'], f"🎉 №{o_id} buyurtmangiz tasdiqlandi!")
            except: pass
        else:
            await db.execute("UPDATE orders SET status='Rad etildi' WHERE id=?", (o_id,))
            pending_orders[o_id] = "Rad etildi"
            await db.commit()
            await call.message.edit_text(f"❌ №{o_id} rad etildi.")
            try: await bot.send_message(order['user_id'], f"😔 №{o_id} buyurtmangiz rad etildi.")
            except: pass

# ==================== 7. FOYDALANUVCHI: KATALOG (PAGINATION) ====================
@router.message(F.text == "🛍 Katalog")
async def user_catalog(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur: cats = await cur.fetchall()
    if not cats: return await message.answer("Bo'limlar yo'q.")
    b = InlineKeyboardBuilder()
    for c in cats: b.button(text=c['name'], callback_data=f"ucat_{c['id']}_0")
    await message.answer("📂 Bo'lim tanlang:", reply_markup=b.adjust(2).as_markup())

@router.callback_query(F.data.startswith("ucat_"))
async def user_pagination(call: types.CallbackQuery):
    _, c_id, page = call.data.split("_")
    c_id, page, limit = int(c_id), int(page), 2
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE category_id=? AND stock>0", (c_id,)) as cur: prods = await cur.fetchall()
    if not prods: return await call.answer("Bo'lim bo'sh.", show_alert=True)
    
    total = math.ceil(len(prods) / limit)
    current = prods[page*limit : (page+1)*limit]
    
    text = f"📦 <b>Mahsulotlar ({page+1}/{total}):</b>\n\n"
    b = InlineKeyboardBuilder()
    for p in current:
        text += f"🔹 <b>{p['name']}</b>\n💰 {p['price']:,} so'm\n\n"
        b.button(text=f"🛒 {p['name'][:10]}", callback_data=f"uadd_{p['id']}")
    
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"ucat_{c_id}_{page-1}"))
    if page < total - 1: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"ucat_{c_id}_{page+1}"))
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="uback_cat"))
    
    try: await call.message.edit_text(text, reply_markup=b.as_markup())
    except: await call.message.answer(text, reply_markup=b.as_markup())

@router.callback_query(F.data == "uback_cat")
async def uback_cat(call: types.CallbackQuery):
    await call.message.delete(); await user_catalog(call.message)

@router.callback_query(F.data.startswith("uadd_"))
async def uadd_cart(call: types.CallbackQuery):
    p_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id FROM cart WHERE user_id=? AND product_id=?", (call.from_user.id, p_id)) as cur:
            if await cur.fetchone(): await db.execute("UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?", (call.from_user.id, p_id))
            else: await db.execute("INSERT INTO cart (user_id, product_id) VALUES (?, ?)", (call.from_user.id, p_id))
        await db.commit()
    await call.answer("Savatga qo'shildi! 🛒")

# ==================== 8. SAVATCHA VA BUYURTMA ====================
@router.message(F.text == "🛒 Savatcha")
async def view_cart(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT c.id, c.quantity, p.name, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?", (message.from_user.id,)) as cur: items = await cur.fetchall()
    if not items: return await message.answer("Savatchangiz bo'sh.")
    
    txt, tot = "🛒 <b>Savatchangiz:</b>\n\n", 0
    b = InlineKeyboardBuilder()
    for i in items:
        tot += i['price']*i['quantity']
        txt += f"▪️ {i['name']} x{i['quantity']} = {i['price']*i['quantity']:,} so'm\n"
        b.button(text=f"🗑 {i['name'][:10]}", callback_data=f"cdel_{i['id']}")
    
    txt += f"\n💰 Jami: <b>{tot:,} so'm</b>"
    b.adjust(1).row(InlineKeyboardButton(text="✅ Buyurtma", callback_data="checkout"), InlineKeyboardButton(text="🗑 Tozalash", callback_data="cclear"))
    await message.answer(txt, reply_markup=b.as_markup())

@router.callback_query(F.data == "cclear")
async def cclear_cart(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE user_id=?", (call.from_user.id,))
        await db.commit()
    await call.message.edit_text("Tozalandi."); await asyncio.sleep(1); await view_cart(call.message)

@router.callback_query(F.data == "checkout")
async def start_checkout(call: types.CallbackQuery, state: FSMContext):
    await call.message.delete(); await call.message.answer("📞 Telefon raqamingizni yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📲 Yuborish", request_contact=True)],[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True))
    await state.set_state(OrderFSM.phone)

@router.message(OrderFSM.phone)
async def get_phone(message: types.Message, state: FSMContext):
    ph = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=ph)
    await message.answer("📍 Manzilingiz (Lokatsiya yoki yozing):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Lokatsiya", request_location=True)],[KeyboardButton(text="✍️ Qo'lda yozish")],[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True))
    await state.set_state(OrderFSM.location)

@router.message(OrderFSM.location)
async def get_location(message: types.Message, state: FSMContext):
    if message.location:
        addr = f"https://www.google.com/maps?q={message.location.latitude},{message.location.longitude}"
        await state.update_data(address=addr); await final_confirm_order(message, state)
    elif message.text == "✍️ Qo'lda yozish":
        await message.answer("To'liq manzilni yozing:", reply_markup=cancel_kb()); await state.set_state(OrderFSM.address)

@router.message(OrderFSM.address)
async def get_address_manual(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text); await final_confirm_order(message, state)

async def final_confirm_order(message, state):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT c.quantity, p.name, p.price FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?", (message.from_user.id,)) as cur: items = await cur.fetchall()
    tot = sum(i['price']*i['quantity'] for i in items)
    txt = f"📋 <b>Tasdiqlang:</b>\n\nJami: {tot:,} so'm\nTel: {data['phone']}\nManzil: {data['address']}"
    b = InlineKeyboardBuilder().button(text="✅ Tasdiqlayman", callback_data="f_conf").button(text="❌ Bekor", callback_data="cancel_all")
    await message.answer(txt, reply_markup=b.adjust(1).as_markup(), disable_web_page_preview=True)
    await state.set_state(OrderFSM.confirm)

@router.callback_query(OrderFSM.confirm, F.data == "f_conf")
async def checkout_final(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data(); u_id = call.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT c.quantity, p.id, p.price, p.name FROM cart c JOIN products p ON c.product_id=p.id WHERE c.user_id=?", (u_id,)) as cur: itms = await cur.fetchall()
        tot = sum(i['price']*i['quantity'] for i in itms)
        c = await db.execute("INSERT INTO orders (user_id, phone, address, total) VALUES (?,?,?,?)", (u_id, data['phone'], data['address'], tot))
        o_id = c.lastrowid
        for i in itms: await db.execute("INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?,?,?,?)", (o_id, i['id'], i['quantity'], i['price']))
        await db.execute("DELETE FROM cart WHERE user_id=?", (u_id,)); await db.commit()
    pending_orders[o_id] = "Kutilmoqda"; await state.clear(); await call.message.delete()
    await call.message.answer(f"⏳ №{o_id} yuborildi. Kuting!", reply_markup=await main_menu_kb(u_id))
    b = InlineKeyboardBuilder().button(text="✅ Tasdiqlash", callback_data=f"approve_{o_id}").button(text="❌ Rad etish", callback_data=f"reject_{o_id}")
    await bot.send_message(SUPER_ADMIN, f"🆕 <b>YANGI BUYURTMA #{o_id}</b>\n💰 {tot:,} so'm\n📞 {data['phone']}\n📍 <a href='{data['address']}'>Manzil</a>", reply_markup=b.adjust(2).as_markup())
    asyncio.create_task(order_reminder(bot, o_id))

# ==================== 9. ADMIN: MAHSULOT QO'SHISH/TAHRIRLASH/O'CHIRISH ====================
@router.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if await is_admin(message.from_user.id): await message.answer("Boshqaruv:", reply_markup=admin_menu_kb(message.from_user.id))

@router.message(F.text == "📁 Bo'lim qo'shish")
async def add_cat(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await message.answer("Nomi:", reply_markup=cancel_kb()); await state.set_state(AdminCategory.name)

@router.message(AdminCategory.name)
async def add_cat_f(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        try: await db.execute("INSERT INTO categories (name) VALUES (?)", (message.text,)); await db.commit(); await message.answer("✅ Qo'shildi.", reply_markup=admin_menu_kb(message.from_user.id))
        except: await message.answer("❌ Xato!", reply_markup=admin_menu_kb(message.from_user.id))
    await state.clear()

@router.message(F.text == "➕ Mahsulot qo'shish")
async def add_p_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM categories") as cur: cats = await cur.fetchall()
    if not cats: return await message.answer("Bo'lim yo'q!")
    b = InlineKeyboardBuilder()
    for c in cats: b.button(text=c['name'], callback_data=f"setp_{c['id']}")
    await message.answer("Bo'lim:", reply_markup=b.adjust(2).as_markup()); await state.set_state(AdminProduct.category_id)

@router.callback_query(AdminProduct.category_id, F.data.startswith("setp_"))
async def set_p_cat(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_id=int(call.data.split("_")[1])); await call.message.answer("Nomi:", reply_markup=cancel_kb()); await state.set_state(AdminProduct.name)

@router.message(AdminProduct.name)
async def set_p_n(m: types.Message, s: FSMContext):
    await s.update_data(name=m.text); await m.answer("Tavsif:"); await s.set_state(AdminProduct.description)

@router.message(AdminProduct.description)
async def set_p_d(m: types.Message, s: FSMContext):
    await s.update_data(description=m.text); await m.answer("Narx:"); await s.set_state(AdminProduct.price)

@router.message(AdminProduct.price)
async def set_p_p(m: types.Message, s: FSMContext):
    if not m.text.isdigit(): return await m.answer("Son!")
    await s.update_data(price=int(m.text)); await m.answer("Zaxira:"); await s.set_state(AdminProduct.stock)

@router.message(AdminProduct.stock)
async def set_p_s(m: types.Message, s: FSMContext):
    if not m.text.isdigit(): return await m.answer("Son!")
    await s.update_data(stock=int(m.text)); await m.answer("Rasm yuboring yoki o'tkazib yuboring:", reply_markup=skip_photo_kb()); await s.set_state(AdminProduct.photo)

@router.message(AdminProduct.photo)
async def set_p_ph(m: types.Message, s: FSMContext):
    d = await s.get_data(); ph = m.photo[-1].file_id if m.photo else None
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (category_id, name, description, price, stock, photo_id) VALUES (?,?,?,?,?,?)", (d['category_id'], d['name'], d['description'], d['price'], d['stock'], ph))
        await db.commit()
    await m.answer("✅ Saqlandi!", reply_markup=admin_menu_kb(m.from_user.id)); await s.clear()

# --- TAHRIRLASH (FULL) ---
@router.message(F.text == "✏️ Mahsulot tahrirlash")
async def edit_p_start(m: types.Message, s: FSMContext):
    if not await is_admin(m.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name FROM products") as cur: pr = await cur.fetchall()
    if not pr: return await m.answer("Yo'q.")
    b = InlineKeyboardBuilder()
    for p in pr: b.button(text=p['name'], callback_data=f"ep_{p['id']}")
    await m.answer("Tanlang:", reply_markup=b.adjust(2).as_markup()); await s.set_state(AdminEdit.product_id)

@router.callback_query(AdminEdit.product_id, F.data.startswith("ep_"))
async def edit_p_field(c: types.CallbackQuery, s: FSMContext):
    await s.update_data(product_id=int(c.data.split("_")[1]))
    b = InlineKeyboardBuilder().button(text="Nom", callback_data="ef_name").button(text="Narx", callback_data="ef_price").button(text="Zaxira", callback_data="ef_stock")
    await c.message.edit_text("Nima o'zgaradi?", reply_markup=b.adjust(2).as_markup()); await s.set_state(AdminEdit.choose_field)

@router.callback_query(AdminEdit.choose_field, F.data.startswith("ef_"))
async def edit_p_val(c: types.CallbackQuery, s: FSMContext):
    f = c.data.split("_")[1]; await s.update_data(choose_field=f); await c.message.answer("Yangi qiymat:", reply_markup=cancel_kb()); await s.set_state(AdminEdit.new_value)

@router.message(AdminEdit.new_value)
async def edit_p_save(m: types.Message, s: FSMContext):
    d = await s.get_data(); f, val = d['choose_field'], m.text
    if f in ['price', 'stock']: val = int(val) if val.isdigit() else 0
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE products SET {f}=? WHERE id=?", (val, d['product_id'])); await db.commit()
    await m.answer("✅ Yangilandi.", reply_markup=admin_menu_kb(m.from_user.id)); await s.clear()

# --- O'CHIRISH (FULL) ---
@router.message(F.text == "🗑 Mahsulot o'chirish")
async def del_p_start(m: types.Message, s: FSMContext):
    if not await is_admin(m.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, name FROM products") as cur: pr = await cur.fetchall()
    if not pr: return await m.answer("Yo'q.")
    b = InlineKeyboardBuilder()
    for p in pr: b.button(text=p['name'], callback_data=f"dp_{p['id']}")
    await m.answer("O'chirish:", reply_markup=b.adjust(2).as_markup()); await s.set_state(AdminDelete.product_id)

@router.callback_query(AdminDelete.product_id, F.data.startswith("dp_"))
async def del_p_conf(c: types.CallbackQuery, s: FSMContext):
    p_id = int(c.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM products WHERE id=?", (p_id,)); await db.commit()
    await c.message.edit_text("✅ O'chirildi."); await s.clear()

# --- BARCHA BUYURTMALAR (ADMIN) ---
@router.message(F.text == "📋 Barcha buyurtmalar")
async def all_orders_a(m: types.Message):
    if not await is_admin(m.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20") as cur: ords = await cur.fetchall()
    if not ords: return await m.answer("Yo'q.")
    txt = "📋 <b>Oxirgi 20 ta:</b>\n\n"
    for o in ords: txt += f"№{o['id']} | {o['total']:,} so'm | {o['status']}\n"
    await m.answer(txt)

# --- XABAR TARQATISH (BROADCAST) ---
@router.message(F.text == "📢 Xabar tarqatish")
async def b_start(m: types.Message, s: FSMContext):
    if not await is_admin(m.from_user.id): return
    await m.answer("Xabarni yozing:", reply_markup=cancel_kb()); await s.set_state(AdminBroadcast.msg)

@router.message(AdminBroadcast.msg)
async def b_send(m: types.Message, s: FSMContext, bot: Bot):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur: users = await cur.fetchall()
    sent, err = 0, 0
    for (uid,) in users:
        try: await bot.send_message(uid, m.text); sent += 1
        except: err += 1
    await m.answer(f"✅ {sent} ta yuborildi, {err} ta xato.", reply_markup=admin_menu_kb(m.from_user.id)); await s.clear()

# --- ADMIN QO'SHISH (SUPER ADMIN) ---
@router.message(F.text == "👮‍♂️ Admin qo'shish")
async def add_a_s(m: types.Message, s: FSMContext):
    if m.from_user.id != SUPER_ADMIN: return
    await m.answer("ID kiriting:", reply_markup=cancel_kb()); await s.set_state(SuperAdminState.new_admin_id)

@router.message(SuperAdminState.new_admin_id)
async def add_a_f(m: types.Message, s: FSMContext):
    if not m.text.isdigit(): return await m.answer("ID!")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(m.text),)); await db.commit()
    await m.answer("✅ Qo'shildi.", reply_markup=admin_menu_kb(m.from_user.id)); await s.clear()

# ==================== 10. MAIN ====================
async def main():
    logging.basicConfig(level=logging.INFO); await init_db()
    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True); print("🚀 ISHGA TUSHDI!"); await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
