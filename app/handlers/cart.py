from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import (
    cart_menu, delivery_menu, order_confirm_menu, catalog_menu, main_menu
)
from app.data.catalog import ITEMS_INDEX
from app.states.cart import CartFlow

router = Router()

async def get_cart(state: FSMContext) -> dict:
    """Возвращает корзину из FSM-хранилища. Структура: {item_id: quantity}"""
    data = await state.get_data()
    return data.get("cart", {})

async def save_cart(state: FSMContext, cart: dict):
    await state.update_data(cart=cart)

def format_cart_text(cart: dict) -> str:
    """Формирует текст с составом корзины и итоговой суммой."""
    if not cart:
        return "🛒 Ваша корзина пуста."

    lines = ["🛒 <b>Ваша корзина:</b>\n"]
    total = 0
    for item_id, qty in cart.items():
        item = ITEMS_INDEX.get(item_id)
        if not item:
            continue
        subtotal = item["price"] * qty
        total += subtotal
        lines.append(f"• {item['name']} × {qty} = <b>{subtotal} ₽</b>")

    lines.append(f"\n💰 <b>Итого: {total} ₽</b>")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: types.CallbackQuery, state: FSMContext):
    item_id = callback.data.split(":")[1]
    item = ITEMS_INDEX.get(item_id)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    cart = await get_cart(state)
    cart[item_id] = cart.get(item_id, 0) + 1
    await save_cart(state, cart)

    qty = cart[item_id]
    await callback.answer(
        f"✅ «{item['name']}» добавлен в корзину (×{qty})",
        show_alert=False
    )



@router.message(F.text == "🛒 Корзина")
async def view_cart(message: types.Message, state: FSMContext):
    cart = await get_cart(state)
    text = format_cart_text(cart)
    await message.answer(text, reply_markup=cart_menu(has_items=bool(cart)), parse_mode="HTML")



@router.callback_query(F.data.startswith("qty:"))
async def change_qty(callback: types.CallbackQuery, state: FSMContext):
    _, action, item_id = callback.data.split(":")
    cart = await get_cart(state)

    if item_id not in cart:
        await callback.answer("Товар не найден в корзине", show_alert=True)
        return

    if action == "inc":
        cart[item_id] += 1
    elif action == "dec":
        cart[item_id] -= 1
        if cart[item_id] <= 0:
            del cart[item_id]
    elif action == "del":
        del cart[item_id]

    await save_cart(state, cart)
    text = format_cart_text(cart)
    await callback.message.edit_text(text, reply_markup=cart_menu(has_items=bool(cart)), parse_mode="HTML")
    await callback.answer()



@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: types.CallbackQuery, state: FSMContext):
    await save_cart(state, {})
    await callback.message.edit_text("🗑 Корзина очищена.", reply_markup=cart_menu(has_items=False))
    await callback.answer()



@router.callback_query(F.data == "cart:checkout")
async def checkout_start(callback: types.CallbackQuery, state: FSMContext):
    cart = await get_cart(state)
    if not cart:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    data = await state.get_data()
    saved_delivery = data.get("delivery_type")

    if saved_delivery:
        await show_order_summary(callback, state, saved_delivery)
    else:
        await state.set_state(CartFlow.choosing_delivery)
        await callback.message.edit_text(
            "🚚 Как вам доставить заказ?\n\n"
            "<i>Это настройка сохранится. Изменить можно в 👤 Личном кабинете.</i>",
            reply_markup=delivery_menu(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(CartFlow.choosing_delivery, F.data.startswith("delivery:"))
async def delivery_chosen(callback: types.CallbackQuery, state: FSMContext):
    delivery_type = callback.data.split(":")[1]
    delivery_label = "🚪 Оставить у двери" if delivery_type == "door" else "🤝 Отдать в руки"

    await state.update_data(delivery_type=delivery_type, delivery_label=delivery_label)
    await show_order_summary(callback, state, delivery_type)
    await callback.answer()


async def show_order_summary(callback: types.CallbackQuery, state: FSMContext, delivery_type: str):
    cart = await get_cart(state)
    data = await state.get_data()
    delivery_label = data.get("delivery_label", "🤝 Отдать в руки")

    cart_text = format_cart_text(cart)
    text = (
        f"{cart_text}\n\n"
        f"📦 Доставка: <b>{delivery_label}</b>\n\n"
        f"Всё верно? Подтвердите заказ или внесите изменения."
    )
    await state.set_state(CartFlow.reviewing)
    await callback.message.edit_text(text, reply_markup=order_confirm_menu(), parse_mode="HTML")



@router.callback_query(CartFlow.reviewing, F.data == "order:change_delivery")
async def change_delivery(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CartFlow.choosing_delivery)
    await callback.message.edit_text(
        "🚚 Выберите новый способ доставки:",
        reply_markup=delivery_menu()
    )
    await callback.answer()


# ─── Оформление заказа: отмена ───────────────────────────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:cancel")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.message.edit_text(
        "❌ Заказ отменён. Ваша корзина сохранена.",
        reply_markup=cart_menu(has_items=True)
    )
    await callback.answer()


# ─── Оформление заказа: оплата (заглушка) ────────────────────────────────────

@router.callback_query(CartFlow.reviewing, F.data == "order:pay")
async def pay_order(callback: types.CallbackQuery, state: FSMContext):
    cart = await get_cart(state)
    data = await state.get_data()
    delivery_label = data.get("delivery_label", "")

    # Считаем итог
    total = sum(
        ITEMS_INDEX[iid]["price"] * qty
        for iid, qty in cart.items()
        if iid in ITEMS_INDEX
    )

    # Очищаем корзину и сбрасываем состояние
    await save_cart(state, {})
    await state.set_state(None)

    await callback.message.edit_text(
        f"✅ <b>Заказ принят!</b>\n\n"
        f"💰 Сумма: <b>{total} ₽</b>\n"
        f"📦 Доставка: <b>{delivery_label}</b>\n\n"
        f"💳 <i>Интеграция оплаты будет добавлена позже.</i>\n\n"
        f"Спасибо за заказ! Ожидайте доставку. 🙌",
        parse_mode="HTML"
    )
    await callback.answer("Заказ оформлен!", show_alert=True)
