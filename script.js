let tg = window.Telegram?.WebApp;
if (tg) tg.expand();

const API_URL = window.location.origin;
let cart = [];
let totalSum = 0;
let categories = [];
let products = [];
let paymentMethods = [];
let activeCategory = 0;
let searchTerm = '';
let locationData = { lat: 0, lon: 0 };

function loadCart() {
    try {
        const saved = localStorage.getItem('uzum_cart');
        if (saved) {
            cart = JSON.parse(saved);
            totalSum = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
        }
    } catch (err) {
        cart = [];
        totalSum = 0;
    }
}

function saveCart() {
    localStorage.setItem('uzum_cart', JSON.stringify(cart));
}

window.addEventListener('beforeunload', saveCart);

async function initApp() {
    loadCart();
    await Promise.all([loadCategories(), loadPaymentMethods()]);
    await loadProducts();
    renderCart();
}

async function loadCategories() {
    try {
        const res = await fetch(API_URL + '/api/categories');
        categories = await res.json();
    } catch (err) {
        categories = [];
    }
    categories.unshift({ id: 0, name: 'Barchasi' });
    renderCategories();
}

async function loadPaymentMethods() {
    try {
        const res = await fetch(API_URL + '/api/payment-methods');
        paymentMethods = await res.json();
    } catch (err) {
        paymentMethods = [
            { id: 0, type: 'cash', name: 'Naqd', details: '' },
            { id: 1, type: 'card', name: 'Karta', details: '' }
        ];
    }
}

async function loadProducts(categoryId = 0) {
    try {
        const query = categoryId ? `?category_id=${categoryId}` : '';
        const res = await fetch(API_URL + '/api/products' + query);
        products = await res.json();
        if (!Array.isArray(products)) products = [];
    } catch (error) {
        products = [];
    }
    renderProducts();
}

function renderCategories() {
    const bucket = document.getElementById('categories');
    if (!bucket) return;

    bucket.innerHTML = categories.map(cat => `
        <div class="category-pill ${cat.id === activeCategory ? 'active' : ''}" onclick="selectCategory(${cat.id})">${cat.name}</div>
    `).join('');
}

function selectCategory(id) {
    activeCategory = id;
    renderCategories();
    loadProducts(id);
}

function searchProducts() {
    searchTerm = document.getElementById('search').value.trim().toLowerCase();
    renderProducts();
}

function renderProducts() {
    const list = document.getElementById('products');
    const filtered = products.filter(p => {
        if (!searchTerm) return true;
        return p.name.toLowerCase().includes(searchTerm) || (p.description || '').toLowerCase().includes(searchTerm);
    });

    if (!filtered.length) {
        list.innerHTML = '<div class="loader">Hozircha mahsulotlar yo\'q yoki qidiruvga mos kelmadi.</div>';
        return;
    }

    list.innerHTML = filtered.map(p => `
        <div class="product-card">
            <div>
                <h3>${p.name}</h3>
                <p>${p.description || 'Tavsif yo‘q.'}</p>
                <p style="margin:0;font-size:13px;color:#666;">${p.category_name ? 'Bo‘lim: ' + p.category_name : ''}</p>
                <p style="margin:8px 0 0;font-weight:700;color:${p.stock > 0 ? '#1d7a2e' : '#c00'};">${p.stock > 0 ? p.stock + ' dona qolgan' : 'Omborda yo‘q'}</p>
            </div>
            <div class="product-actions">
                <span class="price">${Number(p.price).toLocaleString()} so'm</span>
                <button class="btn" ${p.stock <= 0 ? 'disabled style="opacity:.5;cursor:not-allowed;"' : ''} onclick="addToCart(${p.id}, '${escapeHtml(p.name)}', ${p.price})">${p.stock > 0 ? 'Qoʼshish' : 'Qolmagan'}</button>
            </div>
        </div>`).join('');
}

function escapeHtml(text) {
    return String(text).replace(/["'\\<>]/g, char => ({
        '"': '&quot;',
        "'": '&#39;',
        '\\': '&#92;',
        '<': '&lt;',
        '>': '&gt;'
    }[char]));
}

function updateMainButton() {
    if (!tg) return;
    if (!cart.length) {
        tg.MainButton.hide();
        return;
    }
    tg.MainButton.setText(`🛒 Jami: ${totalSum.toLocaleString()} so'm - Buyurtma`);
    tg.MainButton.setParams({ color: '#28a745' });
    tg.MainButton.show();
}

function addToCart(id, name, price) {
    const item = cart.find(i => i.id === id);
    if (item) {
        item.quantity += 1;
    } else {
        cart.push({ id, name, price, quantity: 1 });
    }
    totalSum = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    saveCart();
    renderCart();
    updateMainButton();
}

function removeFromCart(id) {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    item.quantity -= 1;
    if (item.quantity <= 0) {
        cart = cart.filter(i => i.id !== id);
    }
    totalSum = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    saveCart();
    renderCart();
    updateMainButton();
}

function renderCart() {
    const cartBox = document.getElementById('cart');
    if (!cartBox) return;
    if (!cart.length) {
        cartBox.innerHTML = '<div class="loader">Savatingiz bo\'sh. Mahsulot qo\'shing.</div>';
        updateMainButton();
        return;
    }

    const rows = cart.map(item => `
        <div class="cart-item">
            <div>
                <div style="font-weight:700;">${item.name}</div>
                <div style="font-size:13px;color:#666;">${item.price.toLocaleString()} so'm x ${item.quantity}</div>
            </div>
            <div style="text-align:right;">
                <div>${(item.price * item.quantity).toLocaleString()} so'm</div>
                <div style="margin-top:6px;display:flex;gap:6px;justify-content:flex-end;">
                    <button class="small-btn" onclick="removeFromCart(${item.id})">-</button>
                    <button class="small-btn" onclick="addToCart(${item.id}, '${escapeHtml(item.name)}', ${item.price})">+</button>
                </div>
            </div>
        </div>`).join('');

    cartBox.innerHTML = `
        <h3>🛒 Savat</h3>
        ${rows}
        <div class="cart-total">Jami: ${totalSum.toLocaleString()} so'm</div>
        <button class="btn" onclick="showOrderForm()">Buyurtma berish</button>
        <button class="btn" style="background:#777;margin-top:10px;" onclick="clearCart()">Savatchani tozalash</button>
    `;
    updateMainButton();
}

function clearCart() {
    cart = [];
    totalSum = 0;
    saveCart();
    renderCart();
    updateMainButton();
}

function showOrderForm() {
    if (!cart.length) return;
    const cartBox = document.getElementById('cart');
    cartBox.innerHTML = `
        <h3>📍 Buyurtma ma'lumotlari</h3>
        <div class="info-box">Buyurtma oldidan, iltimos, manzilingizni to\'liq kiriting va telefonni aniqlang.</div>
        <div class="order-form">
            <label>Ism</label>
            <input id="order-name" type="text" placeholder="Ismingizni kiriting" />
            <label>Telefon</label>
            <input id="order-phone" type="text" placeholder="+998901234567" />
            <label>Manzil / Mo'ljal</label>
            <textarea id="order-landmark" placeholder="Masalan: Makro orqasi, 4-dom"></textarea>
            <label>To'lov turi</label>
            <select id="order-payment">${renderPaymentOptions()}</select>
            <button class="btn" onclick="submitOrder()">Buyurtmani yuborish</button>
            <button class="btn" style="background:#777;" onclick="renderCart()">Orqaga</button>
        </div>
    `;
    requestLocation();
}

function renderPaymentOptions() {
    if (!paymentMethods.length) {
        return '<option value="Naqd">Naqd</option><option value="Karta">Karta</option>';
    }
    return paymentMethods.map(pm => `<option value="${encodeURIComponent(pm.name)}">${pm.name}</option>`).join('');
}

function requestLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
        position => {
            locationData = { lat: position.coords.latitude, lon: position.coords.longitude };
        },
        () => {
            console.warn('Lokatsiya olinmadi');
        },
        { enableHighAccuracy: true, timeout: 12000 }
    );
}

async function submitOrder() {
    const name = document.getElementById('order-name').value.trim();
    const phone = document.getElementById('order-phone').value.trim();
    const landmark = document.getElementById('order-landmark').value.trim();
    const payment_type = decodeURIComponent(document.getElementById('order-payment').value);

    if (!name || !phone || !landmark) {
        return alert('Iltimos, barcha maydonlarni to\'ldiring.');
    }
    if (!locationData.lat || !locationData.lon) {
        return alert('Iltimos, lokatsiyaga ruxsat bering.');
    }

    const body = {
        name,
        phone,
        landmark,
        payment_type,
        lat: locationData.lat,
        lon: locationData.lon,
        items: cart.map(item => ({ id: item.id, quantity: item.quantity, name: item.name, price: item.price }))
    };

    try {
        const res = await fetch(API_URL + '/api/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Xatolik yuz berdi');
        cart = [];
        totalSum = 0;
        saveCart();
        document.getElementById('cart').innerHTML = `
            <div class="loader" style="color: green;">
                ✅ Buyurtma qabul qilindi!<br />Buyurtma raqami: <b>${data.order_id}</b><br />
                Yo'lkira: <b>${data.delivery_fee.toLocaleString()} so'm</b>
            </div>`;
        updateMainButton();
    } catch (error) {
        alert('Xatolik: ' + error.message);
    }
}

if (tg) {
    tg.onEvent('mainButtonClicked', () => {
        if (!cart.length) return;
        tg.sendData(JSON.stringify(cart));
    });
}

initApp();
