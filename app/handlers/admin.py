import asyncpg
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from app.db.cache import invalidate
from app.db.queries import (
    get_root_categories, get_subcategories, get_products, get_product,
    admin_add_product, admin_edit_product_name, admin_edit_product_price,
    admin_toggle_stock, admin_delete_product,
    admin_add_category, admin_get_all_products, admin_get_stats,
)
from app.states.admin import AdminAddProduct, AdminEditProduct, AdminAddCategory

router = Router()

# ── Фильтр: только для админов ───────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── Главное меню админки ─────────────────────────────────────

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm:main")
async def admin_main_cb(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Статистика ───────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def admin_stats(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    s = await admin_get_stats(pool)
    text = (
        f"📊 <b>Статистика магазина</b>\n\n"
        f"👥 Пользователей: <b>{s['total_users']}</b>\n"
        f"📦 Заказов всего: <b>{s['total_orders']}</b>\n"
        f"💰 Выручка всего: <b>{s['total_revenue']} ₽</b>\n\n"
        f"📅 За сегодня:\n"
        f"   Заказов: <b>{s['orders_today']}</b>\n"
        f"   Выручка: <b>{s['revenue_today']} ₽</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=_back_kb("adm:main"),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Список всех товаров ──────────────────────────────────────

@router.callback_query(F.data == "adm:products")
async def admin_products(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    products = await admin_get_all_products(pool)
    if not products:
        await callback.message.edit_text(
            "Товаров нет.",
            reply_markup=_back_kb("adm:main")
        )
        await callback.answer()
        return

    # Группируем по категории
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in products:
        grouped[p["category_name"]].append(p)

    buttons = []
    for cat_name, items in grouped.items():
        buttons.append([types.InlineKeyboardButton(
            text=f"── {cat_name} ──", callback_data="adm:noop"
        )])
        for p in items:
            stock = "✅" if p["in_stock"] else "❌"
            buttons.append([types.InlineKeyboardButton(
                text=f"{stock} {p['name']} — {p['price']} ₽",
                callback_data=f"adm:prod:{p['id']}"
            )])

    buttons.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="adm:main")])
    await callback.message.edit_text(
        "📦 <b>Все товары</b>\nВыберите товар для редактирования:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm:noop")
async def admin_noop(callback: types.CallbackQuery):
    await callback.answer()


# ── Карточка товара (админ) ──────────────────────────────────

@router.callback_query(F.data.startswith("adm:prod:"))
async def admin_product_card(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    product_id = int(callback.data.split(":")[2])
    p = await get_product(pool, product_id)

    # get_product фильтрует in_stock=true, достаём напрямую
    p = await pool.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
    if not p:
        await callback.answer("Товар не найден", show_alert=True)
        return

    stock_label = "✅ В наличии" if p["in_stock"] else "❌ Нет в наличии"
    text = (
        f"🛍 <b>{p['name']}</b>\n"
        f"💰 Цена: <b>{p['price']} ₽</b>\n"
        f"Статус: {stock_label}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=_product_edit_kb(product_id),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Редактирование: название ─────────────────────────────────

@router.callback_query(F.data.startswith("adm:edit_name:"))
async def admin_edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminEditProduct.entering_value)
    await state.update_data(field="name", product_id=product_id)
    await callback.message.edit_text("✏️ Введите новое название товара:")
    await callback.answer()


# ── Редактирование: цена ─────────────────────────────────────

@router.callback_query(F.data.startswith("adm:edit_price:"))
async def admin_edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminEditProduct.entering_value)
    await state.update_data(field="price", product_id=product_id)
    await callback.message.edit_text("💰 Введите новую цену (только цифры):")
    await callback.answer()


@router.message(AdminEditProduct.entering_value)
async def admin_edit_value(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    field = data["field"]
    product_id = data["product_id"]

    if field == "name":
        name = message.text.strip()
        if not name:
            await message.answer("❌ Название не может быть пустым. Попробуй ещё раз:")
            return
        await admin_edit_product_name(pool, product_id, name)
        await message.answer(f"✅ Название изменено: <b>{name}</b>", parse_mode="HTML")

    elif field == "price":
        if not message.text.strip().isdigit():
            await message.answer("❌ Введи целое число. Попробуй ещё раз:")
            return
        price = int(message.text.strip())
        await admin_edit_product_price(pool, product_id, price)
        await message.answer(f"✅ Цена изменена: <b>{price} ₽</b>", parse_mode="HTML")

    invalidate()  # сбрасываем кэш
    await state.clear()
    await message.answer("⚙️ Панель администратора", reply_markup=_admin_main_kb())


# ── Переключить наличие ──────────────────────────────────────

@router.callback_query(F.data.startswith("adm:toggle:"))
async def admin_toggle(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    new_status = await admin_toggle_stock(pool, product_id)
    invalidate()
    status_text = "✅ В наличии" if new_status else "❌ Снято с продажи"
    await callback.answer(f"Статус изменён: {status_text}", show_alert=True)
    # Обновляем карточку
    await admin_product_card(callback, pool)


# ── Удалить товар ────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:del:"))
async def admin_delete_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "⚠️ <b>Удалить товар?</b>\nЭто действие нельзя отменить.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:del_ok:{product_id}")],
            [types.InlineKeyboardButton(text="🔙 Отмена",      callback_data=f"adm:prod:{product_id}")],
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:del_ok:"))
async def admin_delete_ok(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await admin_delete_product(pool, product_id)
    invalidate()
    await callback.message.edit_text(
        "✅ Товар удалён.",
        reply_markup=_back_kb("adm:products")
    )
    await callback.answer()


# ── Добавить товар ───────────────────────────────────────────

@router.callback_query(F.data == "adm:add_product")
async def admin_add_product_start(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    cats = await get_root_categories(pool)
    buttons = []
    for c in cats:
        buttons.append([types.InlineKeyboardButton(
            text=c["name"], callback_data=f"adm:pick_cat:{c['id']}"
        )])
        # Подкатегории
        subcats = await get_subcategories(pool, c["id"])
        for sc in subcats:
            buttons.append([types.InlineKeyboardButton(
                text=f"  ↳ {sc['name']}", callback_data=f"adm:pick_cat:{sc['id']}"
            )])

    buttons.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data="adm:main")])
    await state.set_state(AdminAddProduct.choosing_category)
    await callback.message.edit_text(
        "📦 <b>Добавление товара</b>\nВыберите категорию:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(AdminAddProduct.choosing_category, F.data.startswith("adm:pick_cat:"))
async def admin_pick_category(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await state.set_state(AdminAddProduct.entering_name)
    await callback.message.edit_text("✏️ Введите название товара:")
    await callback.answer()


@router.message(AdminAddProduct.entering_name)
async def admin_product_name(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым:")
        return
    await state.update_data(name=name)
    await state.set_state(AdminAddProduct.entering_price)
    await message.answer(f"💰 Товар: <b>{name}</b>\nВведите цену (₽):", parse_mode="HTML")


@router.message(AdminAddProduct.entering_price)
async def admin_product_price(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(message.from_user.id):
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи целое число:")
        return

    price = int(message.text.strip())
    await state.update_data(price=price)
    data = await state.get_data()
    await state.set_state(AdminAddProduct.confirming)

    await message.answer(
        f"📋 <b>Проверьте данные:</b>\n\n"
        f"Название: <b>{data['name']}</b>\n"
        f"Цена: <b>{price} ₽</b>",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Сохранить", callback_data="adm:save_product")],
            [types.InlineKeyboardButton(text="❌ Отмена",    callback_data="adm:main")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(AdminAddProduct.confirming, F.data == "adm:save_product")
async def admin_save_product(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    data = await state.get_data()
    product_id = await admin_add_product(
        pool, data["category_id"], data["name"], data["price"]
    )
    invalidate()
    await state.clear()
    await callback.message.edit_text(
        f"✅ Товар <b>{data['name']}</b> добавлен (ID: {product_id})",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Добавить категорию ───────────────────────────────────────

@router.callback_query(F.data == "adm:add_category")
async def admin_add_cat_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminAddCategory.entering_name)
    await callback.message.edit_text("🗂 Введите название новой категории:")
    await callback.answer()


@router.message(AdminAddCategory.entering_name)
async def admin_cat_name(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AdminAddCategory.choosing_parent)

    cats = await get_root_categories(pool)
    buttons = [[types.InlineKeyboardButton(
        text="🚫 Без родителя (верхний уровень)", callback_data="adm:cat_parent:0"
    )]]
    for c in cats:
        buttons.append([types.InlineKeyboardButton(
            text=c["name"], callback_data=f"adm:cat_parent:{c['id']}"
        )])
    await message.answer(
        f"Категория: <b>{name}</b>\nВыберите родителя:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(AdminAddCategory.choosing_parent, F.data.startswith("adm:cat_parent:"))
async def admin_cat_parent(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    parent_id_raw = int(callback.data.split(":")[2])
    parent_id = parent_id_raw if parent_id_raw != 0 else None
    data = await state.get_data()

    cat_id = await admin_add_category(pool, data["name"], parent_id)
    invalidate()
    await state.clear()
    await callback.message.edit_text(
        f"✅ Категория <b>{data['name']}</b> добавлена (ID: {cat_id})",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Клавиатуры ───────────────────────────────────────────────

def _admin_main_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Статистика",      callback_data="adm:stats")],
        [types.InlineKeyboardButton(text="📦 Все товары",      callback_data="adm:products")],
        [types.InlineKeyboardButton(text="➕ Добавить товар",   callback_data="adm:add_product")],
        [types.InlineKeyboardButton(text="🗂 Добавить категорию", callback_data="adm:add_category")],
    ])


def _product_edit_kb(product_id: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Название",        callback_data=f"adm:edit_name:{product_id}")],
        [types.InlineKeyboardButton(text="💰 Цена",            callback_data=f"adm:edit_price:{product_id}")],
        [types.InlineKeyboardButton(text="🔄 Наличие",         callback_data=f"adm:toggle:{product_id}")],
        [types.InlineKeyboardButton(text="🗑 Удалить",         callback_data=f"adm:del:{product_id}")],
        [types.InlineKeyboardButton(text="🔙 Назад",           callback_data="adm:products")],
    ])


def _back_kb(callback_data: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])
