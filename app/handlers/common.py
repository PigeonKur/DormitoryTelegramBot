import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import (
    catalog_menu, subcategory_or_items_menu, items_menu,
    item_card_menu, profile_menu
)
from app.db.queries import (
    get_root_categories, get_subcategories, get_category,
    get_products, get_product, get_user, get_user_orders
)

router = Router()

DELIVERY_LABELS = {
    "hand": "🤝 Отдать в руки",
    "door": "🚪 Оставить у двери",
}


# ── Магазин ─────────────────────────────────────────────────

@router.message(F.text == "🏪 Магазин")
async def shop_handler(message: types.Message, pool: asyncpg.Pool):
    cats = await get_root_categories(pool)
    await message.answer("🏪 Выберите категорию:", reply_markup=catalog_menu(cats))


# ── Личный кабинет ───────────────────────────────────────────

@router.message(F.text == "👤 Личный кабинет")
async def profile_handler(message: types.Message, pool: asyncpg.Pool):
    user = await get_user(pool, message.from_user.id)
    delivery = DELIVERY_LABELS.get(user["delivery_type"], "—") if user else "—"
    room = user["room_number"] or "не указан" if user else "—"

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🚚 Тип доставки: <b>{delivery}</b>\n"
        f"📍 Номер комнаты: <b>{room}</b>"
    )
    await message.answer(text, reply_markup=profile_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("profile:"))
async def profile_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    action = callback.data.split(":")[1]

    if action == "orders":
        orders = await get_user_orders(pool, callback.from_user.id)
        if not orders:
            await callback.message.edit_text("📦 Заказов пока нет.")
        else:
            lines = ["📦 <b>Последние заказы:</b>\n"]
            for o in orders:
                date = o["created_at"].strftime("%d.%m.%Y %H:%M")
                status_icon = {"pending": "⏳", "paid": "✅", "cancelled": "❌"}.get(o["status"], "❓")
                lines.append(f"{status_icon} №{o['id']} — {o['total_price']} ₽ ({date})")
            await callback.message.edit_text("\n".join(lines), parse_mode="HTML")

    elif action == "delivery":
        from app.keyboards.main import delivery_menu
        await callback.message.edit_text(
            "🚚 Выберите тип доставки по умолчанию:",
            reply_markup=delivery_menu(from_profile=True)
        )
    elif action == "room":
        await callback.message.edit_text(
            "📍 Введите номер вашей комнаты (например: <b>214</b>):",
            parse_mode="HTML"
        )
        from app.states.cart import CartFlow
        # Используем отдельное состояние для ввода комнаты
        # (добавим в states/cart.py)

    await callback.answer()


# ── Навигация по каталогу ────────────────────────────────────

@router.callback_query(F.data == "to_catalog")
async def to_catalog(callback: types.CallbackQuery, pool: asyncpg.Pool):
    cats = await get_root_categories(pool)
    await callback.message.edit_text("🏪 Выберите категорию:", reply_markup=catalog_menu(cats))
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    cat_id = int(callback.data.split(":")[1])
    cat = await get_category(pool, cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    subcats = await get_subcategories(pool, cat_id)
    if subcats:
        # Есть подкатегории — показываем их
        kb = await subcategory_or_items_menu(pool, cat_id, parent_back="to_catalog")
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите подкатегорию:",
            reply_markup=kb
        )
    else:
        # Нет подкатегорий — сразу товары
        products = await get_products(pool, cat_id)
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback="to_catalog")
        )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def subcategory_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    _, cat_id_str, sub_id_str = callback.data.split(":")
    sub_id = int(sub_id_str)
    sub = await get_category(pool, sub_id)
    if not sub:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return

    products = await get_products(pool, sub_id)
    await callback.message.edit_text(
        f"{sub['name']}\n\nВыберите товар:",
        reply_markup=items_menu(products, back_callback=f"cat:{cat_id_str}")
    )
    await callback.answer()


# ── Карточка товара ──────────────────────────────────────────

@router.callback_query(F.data.startswith("item:"))
async def item_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    parts = callback.data.split(":")   # item:<product_id>:<back_callback>
    product_id = int(parts[1])
    back_cb = parts[2] if len(parts) > 2 else "to_catalog"

    item = await get_product(pool, product_id)
    if not item:
        await callback.answer("Товар не найден или закончился", show_alert=True)
        return

    text = (
        f"🛍 <b>{item['name']}</b>\n\n"
        f"💰 Цена: <b>{item['price']} ₽</b>\n\n"
        f"Добавить товар в корзину?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=item_card_menu(product_id, back_cb),
        parse_mode="HTML"
    )
    await callback.answer()
