import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import cart_menu, delivery_menu, order_confirm_menu
from app.db.queries import (
    get_product, create_order, get_user,
    set_delivery_type, update_order_status
)
from app.states.cart import CartFlow

router = Router()

DELIVERY_LABELS = {
    "hand": "🤝 Отдать в руки",
    "door": "🚪 Оставить у двери",
}

# ── Вспомогательные функции ──────────────────────────────────

async def get_cart(state: FSMContext) -> dict:
    """Корзина в FSM: {product_id(str): quantity(int)}"""
    data = await state.get_data()
    return data.get("cart", {})

async def save_cart(state: FSMContext, cart: dict):
    await state.update_data(cart=cart)

async def format_cart_text(cart: dict, pool: asyncpg.Pool) -> str:
    if not cart:
        return "🛒 Ваша корзина пуста."

    lines = ["🛒 <b>Ваша корзина:</b>\n"]
    total = 0
    for pid_str, qty in cart.items():
        item = await get_product(pool, int(pid_str))
        if not item:
            continue
        subtotal = item["price"] * qty
        total += subtotal
        lines.append(f"• {item['name']} × {qty} = <b>{subtotal} ₽</b>")

    lines.append(f"\n💰 <b>Итого: {total} ₽</b>")
    return "\n".join(lines)


# ── Добавить в корзину ───────────────────────────────────────

@router.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    parts = callback.data.split(":")   # add:<product_id>:<back_callback>
    product_id = int(parts[1])
    back_cb = parts[2] if len(parts) > 2 else "to_catalog"

    item = await get_product(pool, product_id)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    cart = await get_cart(state)
    pid_str = str(product_id)
    cart[pid_str] = cart.get(pid_str, 0) + 1
    await save_cart(state, cart)

    qty = cart[pid_str]
    await callback.answer(f"✅ «{item['name']}» добавлен в корзину (×{qty})")

    # ── Фикс: возвращаемся назад к списку товаров ──
    from app.db.queries import get_category, get_products
    from app.keyboards.main import items_menu, subcategory_or_items_menu

    # back_cb может быть: "to_catalog", "cat:5", "sub:3:7"
    if back_cb == "to_catalog":
        from app.db.queries import get_root_categories
        from app.keyboards.main import catalog_menu
        cats = await get_root_categories(pool)
        await callback.message.edit_text("🏪 Выберите категорию:", reply_markup=catalog_menu(cats))

    elif back_cb.startswith("cat:"):
        cat_id = int(back_cb.split(":")[1])
        cat = await get_category(pool, cat_id)
        products = await get_products(pool, cat_id)
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback="to_catalog")
        )

    elif back_cb.startswith("sub:"):
        _, cat_id_str, sub_id_str = back_cb.split(":")
        sub = await get_category(pool, int(sub_id_str))
        products = await get_products(pool, int(sub_id_str))
        await callback.message.edit_text(
            f"{sub['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback=f"cat:{cat_id_str}")
        )


# ── Просмотр корзины ─────────────────────────────────────────

@router.message(F.text == "🛒 Корзина")
async def view_cart(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    cart = await get_cart(state)
    text = await format_cart_text(cart, pool)
    await message.answer(text, reply_markup=cart_menu(has_items=bool(cart)), parse_mode="HTML")


# ── Изменить количество ──────────────────────────────────────

@router.callback_query(F.data.startswith("qty:"))
async def change_qty(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    _, action, pid_str = callback.data.split(":")
    cart = await get_cart(state)

    if pid_str not in cart:
        await callback.answer("Товар не найден в корзине", show_alert=True)
        return

    if action == "inc":
        cart[pid_str] += 1
    elif action == "dec":
        cart[pid_str] -= 1
        if cart[pid_str] <= 0:
            del cart[pid_str]
    elif action == "del":
        del cart[pid_str]

    await save_cart(state, cart)
    text = await format_cart_text(cart, pool)
    await callback.message.edit_text(text, reply_markup=cart_menu(has_items=bool(cart)), parse_mode="HTML")
    await callback.answer()


# ── Очистить корзину ─────────────────────────────────────────

@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: types.CallbackQuery, state: FSMContext):
    await save_cart(state, {})
    await callback.message.edit_text("🗑 Корзина очищена.", reply_markup=cart_menu(has_items=False))
    await callback.answer()


# ── Оформление: шаг 1 — доставка ────────────────────────────

@router.callback_query(F.data == "cart:checkout")
async def checkout_start(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    cart = await get_cart(state)
    if not cart:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    user = await get_user(pool, callback.from_user.id)
    saved_delivery = user["delivery_type"] if user else None

    if saved_delivery:
        await show_order_summary(callback, state, pool, saved_delivery)
    else:
        await state.set_state(CartFlow.choosing_delivery)
        await callback.message.edit_text(
            "🚚 Как вам доставить заказ?\n\n"
            "<i>Настройка сохранится. Изменить можно в 👤 Личном кабинете.</i>",
            reply_markup=delivery_menu(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(CartFlow.choosing_delivery, F.data.startswith("delivery:"))
async def delivery_chosen(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    delivery_type = callback.data.split(":")[1]
    # Сохраняем выбор в БД
    await set_delivery_type(pool, callback.from_user.id, delivery_type)
    await show_order_summary(callback, state, pool, delivery_type)
    await callback.answer()


# Смена доставки из профиля
@router.callback_query(F.data.startswith("delivery:"))
async def delivery_from_profile(callback: types.CallbackQuery, pool: asyncpg.Pool):
    delivery_type = callback.data.split(":")[1]
    await set_delivery_type(pool, callback.from_user.id, delivery_type)
    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    await callback.message.edit_text(f"✅ Тип доставки изменён: <b>{label}</b>", parse_mode="HTML")
    await callback.answer()


# ── Оформление: шаг 2 — итоговая форма ──────────────────────

async def show_order_summary(
    callback: types.CallbackQuery,
    state: FSMContext,
    pool: asyncpg.Pool,
    delivery_type: str,
):
    cart = await get_cart(state)
    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    cart_text = await format_cart_text(cart, pool)

    text = (
        f"{cart_text}\n\n"
        f"📦 Доставка: <b>{label}</b>\n\n"
        f"Всё верно? Подтвердите заказ."
    )
    await state.update_data(delivery_type=delivery_type)
    await state.set_state(CartFlow.reviewing)
    await callback.message.edit_text(text, reply_markup=order_confirm_menu(), parse_mode="HTML")


# ── Оформление: изменить доставку ───────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:change_delivery")
async def change_delivery(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CartFlow.choosing_delivery)
    await callback.message.edit_text(
        "🚚 Выберите новый способ доставки:",
        reply_markup=delivery_menu()
    )
    await callback.answer()


# ── Оформление: отмена ───────────────────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:cancel")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.message.edit_text(
        "❌ Заказ отменён. Корзина сохранена.",
        reply_markup=cart_menu(has_items=True)
    )
    await callback.answer()


# ── Оформление: оплата (заглушка) ────────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:pay")
async def pay_order(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    cart = await get_cart(state)
    data = await state.get_data()
    delivery_type = data.get("delivery_type", "hand")

    # Собираем позиции и считаем итог
    items = []
    total = 0
    for pid_str, qty in cart.items():
        item = await get_product(pool, int(pid_str))
        if not item:
            continue
        subtotal = item["price"] * qty
        total += subtotal
        items.append({
            "product_id": item["id"],
            "name": item["name"],
            "price": item["price"],
            "quantity": qty,
        })

    # Создаём заказ в БД
    order_id = await create_order(
        pool=pool,
        user_id=callback.from_user.id,
        delivery_type=delivery_type,
        total_price=total,
        items=items,
    )
    await update_order_status(pool, order_id, "paid")

    # Очищаем корзину
    await save_cart(state, {})
    await state.set_state(None)

    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    await callback.message.edit_text(
        f"✅ <b>Заказ №{order_id} принят!</b>\n\n"
        f"💰 Сумма: <b>{total} ₽</b>\n"
        f"📦 Доставка: <b>{label}</b>\n\n"
        f"💳 <i>Интеграция оплаты будет добавлена позже.</i>\n\n"
        f"Спасибо за заказ! Ожидайте 🙌",
        parse_mode="HTML"
    )
    await callback.answer("Заказ оформлен!", show_alert=True)
