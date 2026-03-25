import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.db.queries import (
    get_user_stats, set_room_number, set_delivery_type,
    get_user_orders, get_order_items,
    get_referral_history, get_referrals_list,
)
from app.keyboards.main import profile_menu, delivery_menu, profile_referral_menu
from app.states.cart import CartFlow

router = Router()

DELIVERY_LABELS = {
    "hand": "🤝 Отдать в руки",
    "door": "🚪 Оставить у двери",
}


# ── Главная страница кабинета ────────────────────────────────

@router.message(F.text == "👤 Личный кабинет")
async def profile_handler(message: types.Message, pool: asyncpg.Pool):
    user = await get_user_stats(pool, message.from_user.id)
    if not user:
        await message.answer("Профиль не найден. Введите /start")
        return

    delivery = DELIVERY_LABELS.get(user["delivery_type"], "—")
    room = user["room_number"] or "не указан"

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🏷 Имя: <b>{user['full_name']}</b>\n"
        f"📍 Комната: <b>{room}</b>\n"
        f"🚚 Доставка: <b>{delivery}</b>\n"
        f"💰 Бонусный баланс: <b>{user['balance']} ₽</b>\n"
        f"👥 Приглашено друзей: <b>{user['referral_count']}</b>\n"
        f"🛍 Потрачено всего: <b>{user['total_spent']} ₽</b>"
    )
    await message.answer(text, reply_markup=profile_menu(), parse_mode="HTML")


# ── Мои заказы ───────────────────────────────────────────────

@router.callback_query(F.data == "profile:orders")
async def profile_orders(callback: types.CallbackQuery, pool: asyncpg.Pool):
    orders = await get_user_orders(pool, callback.from_user.id)
    if not orders:
        await callback.message.edit_text(
            "📦 Заказов пока нет.\n\nПерейдите в 🏪 Магазин и сделайте первый заказ!",
            reply_markup=_back_to_profile_kb()
        )
        await callback.answer()
        return

    STATUS = {"pending": "⏳ Ожидает", "paid": "✅ Оплачен", "cancelled": "❌ Отменён"}
    lines = ["📦 <b>Последние заказы:</b>\n"]
    for o in orders:
        date = o["created_at"].strftime("%d.%m %H:%M")
        status = STATUS.get(o["status"], o["status"])
        delivery = DELIVERY_LABELS.get(o["delivery_type"], "—")
        lines.append(
            f"{status} <b>№{o['id']}</b> — {o['total_price']} ₽\n"
            f"   📅 {date} | {delivery}"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_to_profile_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Смена типа доставки ──────────────────────────────────────

@router.callback_query(F.data == "profile:delivery")
async def profile_delivery(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🚚 Выберите тип доставки по умолчанию:",
        reply_markup=delivery_menu(from_profile=True)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delivery:"))
async def delivery_chosen(callback: types.CallbackQuery, pool: asyncpg.Pool):
    delivery_type = callback.data.split(":")[1]
    await set_delivery_type(pool, callback.from_user.id, delivery_type)
    label = DELIVERY_LABELS.get(delivery_type, delivery_type)
    await callback.message.edit_text(
        f"✅ Тип доставки изменён: <b>{label}</b>",
        reply_markup=_back_to_profile_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Номер комнаты ────────────────────────────────────────────

@router.callback_query(F.data == "profile:room")
async def profile_room(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CartFlow.entering_room)
    await callback.message.edit_text(
        "📍 Введите номер вашей комнаты:\n"
        "<i>Например: 214 или А-305</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(CartFlow.entering_room)
async def process_room(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    room = message.text.strip()
    if len(room) > 20:
        await message.answer("❌ Слишком длинный номер. Попробуй ещё раз:")
        return

    await set_room_number(pool, message.from_user.id, room)
    await state.clear()
    await message.answer(
        f"✅ Номер комнаты сохранён: <b>{room}</b>",
        parse_mode="HTML",
        reply_markup=profile_menu()
    )


# ── Реферальная программа ────────────────────────────────────

@router.callback_query(F.data == "profile:referral")
async def profile_referral(callback: types.CallbackQuery, pool: asyncpg.Pool):
    user = await get_user_stats(pool, callback.from_user.id)
    ref_code = user["ref_code"] or "—"

    # Формируем ссылку
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={ref_code}"

    history = await get_referral_history(pool, callback.from_user.id)
    referrals = await get_referrals_list(pool, callback.from_user.id)

    lines = [
        f"👥 <b>Реферальная программа</b>\n",
        f"🔗 Ваша ссылка:\n<code>{ref_link}</code>\n",
        f"💰 Вы получаете <b>10%</b> бонусами с каждого заказа приглашённого.\n",
        f"🏷 Ваш баланс: <b>{user['balance']} ₽</b>",
        f"👤 Приглашено: <b>{user['referral_count']}</b> чел.\n",
    ]

    if referrals:
        lines.append("─── Приглашённые ───")
        for r in referrals[:5]:
            date = r["created_at"].strftime("%d.%m.%Y")
            lines.append(f"• {r['full_name']} (с {date})")

    if history:
        lines.append("\n─── Последние начисления ───")
        for h in history[:5]:
            date = h["created_at"].strftime("%d.%m %H:%M")
            lines.append(f"• +{h['amount']} ₽ от {h['referee_name']} ({date})")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=profile_referral_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "profile:back")
async def profile_back(callback: types.CallbackQuery, pool: asyncpg.Pool):
    user = await get_user_stats(pool, callback.from_user.id)
    delivery = DELIVERY_LABELS.get(user["delivery_type"], "—")
    room = user["room_number"] or "не указан"
    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🏷 Имя: <b>{user['full_name']}</b>\n"
        f"📍 Комната: <b>{room}</b>\n"
        f"🚚 Доставка: <b>{delivery}</b>\n"
        f"💰 Бонусный баланс: <b>{user['balance']} ₽</b>\n"
        f"👥 Приглашено друзей: <b>{user['referral_count']}</b>\n"
        f"🛍 Потрачено всего: <b>{user['total_spent']} ₽</b>"
    )
    await callback.message.edit_text(text, reply_markup=profile_menu(), parse_mode="HTML")
    await callback.answer()


# ── Вспомогательные клавиатуры ───────────────────────────────

def _back_to_profile_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile:back")]
    ])
