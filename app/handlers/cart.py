import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import cart_menu, delivery_menu, order_confirm_menu
from app.db.queries import (
    get_product, get_user, set_delivery_type, update_order_status,
    cart_add_item, cart_get_items, cart_change_qty, cart_delete_item,
    cart_clear, create_order, process_referral_reward,
)
from app.db.cache import cached_root_categories, cached_category, cached_products
from app.states.cart import CartFlow

router = Router()

DELIVERY_LABELS = {
    "hand": "🤝 Отдать в руки",
    "door": "🚪 Оставить у двери",
}


# ── Вспомогательные функции ──────────────────────────────────

async def format_cart_text(user_id: int, pool: asyncpg.Pool) -> tuple[str, int]:
    """Возвращает (текст корзины, итоговая сумма)."""
    rows = await cart_get_items(pool, user_id)
    if not rows:
        return "🛒 Ваша корзина пуста.", 0

    lines = ["🛒 <b>Ваша корзина:</b>\n"]
    total = 0
    for r in rows:
        if not r["in_stock"]:
            lines.append(f"• ~~{r['name']}~~ — нет в наличии")
            continue
        subtotal = r["price"] * r["quantity"]
        total += subtotal
        lines.append(f"• {r['name']} × {r['quantity']} = <b>{subtotal} ₽</b>")

    lines.append(f"\n💰 <b>Итого: {total} ₽</b>")
    return "\n".join(lines), total


# ── Добавить в корзину ───────────────────────────────────────

@router.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: types.CallbackQuery, pool: asyncpg.Pool):
    parts = callback.data.split(":")
    product_id = int(parts[1])
    back_cb = ":".join(parts[2:]) if len(parts) > 2 else "to_catalog"

    item = await get_product(pool, product_id)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    qty = await cart_add_item(pool, callback.from_user.id, product_id)
    await callback.answer(f"✅ «{item['name']}» в корзине (×{qty})")

    # Возвращаемся назад к списку товаров
    from app.keyboards.main import items_menu, catalog_menu

    if back_cb == "to_catalog":
        cats = await cached_root_categories(pool)
        await callback.message.edit_text(
            "🏪 Выберите категорию:",
            reply_markup=catalog_menu(cats)
        )
    elif back_cb.startswith("cat:"):
        cat_id = int(back_cb.split(":")[1])
        cat = await cached_category(pool, cat_id)
        products = await cached_products(pool, cat_id)
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback="to_catalog")
        )
    elif back_cb.startswith("sub:"):
        sub_parts = back_cb.split(":")
        cat_id_str, sub_id_str = sub_parts[1], sub_parts[2]
        sub = await cached_category(pool, int(sub_id_str))
        products = await cached_products(pool, int(sub_id_str))
        await callback.message.edit_text(
            f"{sub['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback=f"cat:{cat_id_str}")
        )


# ── Просмотр корзины ─────────────────────────────────────────

@router.message(F.text == "🛒 Корзина")
async def view_cart(message: types.Message, pool: asyncpg.Pool):
    text, total = await format_cart_text(message.from_user.id, pool)
    await message.answer(text, reply_markup=cart_menu(has_items=total > 0), parse_mode="HTML")


# ── Изменить количество ──────────────────────────────────────

@router.callback_query(F.data.startswith("qty:"))
async def change_qty(callback: types.CallbackQuery, pool: asyncpg.Pool):
    _, action, pid_str = callback.data.split(":")
    product_id = int(pid_str)
    user_id = callback.from_user.id

    if action == "inc":
        await cart_change_qty(pool, user_id, product_id, +1)
    elif action == "dec":
        await cart_change_qty(pool, user_id, product_id, -1)
    elif action == "del":
        await cart_delete_item(pool, user_id, product_id)

    text, total = await format_cart_text(user_id, pool)
    await callback.message.edit_text(
        text,
        reply_markup=cart_menu(has_items=total > 0),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Очистить корзину ─────────────────────────────────────────

@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: types.CallbackQuery, pool: asyncpg.Pool):
    await cart_clear(pool, callback.from_user.id)
    await callback.message.edit_text(
        "🗑 Корзина очищена.",
        reply_markup=cart_menu(has_items=False)
    )
    await callback.answer()


# ── Оформление: шаг 1 — доставка ────────────────────────────

@router.callback_query(F.data == "cart:checkout")
async def checkout_start(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    rows = await cart_get_items(pool, callback.from_user.id)
    if not rows:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    user = await get_user(pool, callback.from_user.id)
    saved_delivery = user["delivery_type"] if user else None

    if saved_delivery:
        await _show_order_summary(callback, state, pool, saved_delivery)
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
    await set_delivery_type(pool, callback.from_user.id, delivery_type)
    await _show_order_summary(callback, state, pool, delivery_type)
    await callback.answer()


# Смена доставки из профиля (без активного состояния)
@router.callback_query(F.data.startswith("delivery:"))
async def delivery_from_profile(callback: types.CallbackQuery, pool: asyncpg.Pool):
    delivery_type = callback.data.split(":")[1]
    await set_delivery_type(pool, callback.from_user.id, delivery_type)
    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    await callback.message.edit_text(
        f"✅ Тип доставки изменён: <b>{label}</b>",
        parse_mode="HTML"
    )
    await callback.answer()


# ── Оформление: шаг 2 — итоговая форма ──────────────────────

async def _show_order_summary(
    callback: types.CallbackQuery,
    state: FSMContext,
    pool: asyncpg.Pool,
    delivery_type: str,
):
    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    cart_text, total = await format_cart_text(callback.from_user.id, pool)

    if total == 0:
        await callback.answer("Все товары закончились!", show_alert=True)
        return

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
async def cancel_order(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    await state.set_state(None)
    rows = await cart_get_items(pool, callback.from_user.id)
    await callback.message.edit_text(
        "❌ Заказ отменён. Корзина сохранена.",
        reply_markup=cart_menu(has_items=bool(rows))
    )
    await callback.answer()


# ── Оформление: оплата (заглушка) ────────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:pay")
async def pay_order(callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool):
    user_id = callback.from_user.id
    rows = await cart_get_items(pool, user_id)
    data = await state.get_data()
    delivery_type = data.get("delivery_type", "hand")

    if not rows:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    # Собираем позиции только из товаров в наличии
    items = []
    total = 0
    for r in rows:
        if not r["in_stock"]:
            continue
        subtotal = r["price"] * r["quantity"]
        total += subtotal
        items.append({
            "product_id": r["product_id"],
            "name":       r["name"],
            "price":      r["price"],
            "quantity":   r["quantity"],
        })

    # Создаём заказ в БД
    order_id = await create_order(
        pool=pool,
        user_id=user_id,
        delivery_type=delivery_type,
        total_price=total,
        items=items,
    )
    await update_order_status(pool, order_id, "paid")

    # Реферальное начисление
    referrer_id = await process_referral_reward(
        pool=pool,
        referee_id=user_id,
        order_id=order_id,
        order_total=total,
    )
    if referrer_id:
        bonus = max(1, total * 10 // 100)
        try:
            await callback.bot.send_message(
                referrer_id,
                f"💰 Вам начислено <b>{bonus} ₽</b> бонусами — "
                f"ваш реферал сделал заказ на {total} ₽!",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # Очищаем корзину в БД и сбрасываем состояние
    await cart_clear(pool, user_id)
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
