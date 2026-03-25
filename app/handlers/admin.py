import asyncpg
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from app.db.cache import invalidate
from app.db.queries import (
    get_root_categories,
    get_subcategories,
    get_products,
    get_product,
    admin_add_product,
    admin_edit_product_name,
    admin_edit_product_price,
    admin_toggle_stock,
    admin_delete_product,
    admin_add_category,
    admin_get_all_products,
    admin_get_stats,
    get_unread_messages,
    get_all_messages,
    count_all_messages,
    mark_message_read,
    mark_message_replied,
    get_all_user_ids,
    clear_all_messages,
)
from app.states.admin import (
    AdminAddProduct,
    AdminEditProduct,
    AdminAddCategory,
    AdminReply,
    AdminBroadcast,
)

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm:main")
async def admin_main_cb(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=_admin_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


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
        text, reply_markup=_back_kb("adm:main"), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "adm:products")
async def admin_products(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    products = await admin_get_all_products(pool)
    if not products:
        await callback.message.edit_text(
            "Товаров нет.", reply_markup=_back_kb("adm:main")
        )
        await callback.answer()
        return

    from collections import defaultdict

    grouped = defaultdict(list)
    for p in products:
        grouped[p["category_name"]].append(p)

    buttons = []
    for cat_name, items in grouped.items():
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=f"── {cat_name} ──", callback_data="adm:noop"
                )
            ]
        )
        for p in items:
            stock = "✅" if p["in_stock"] else "❌"
            buttons.append(
                [
                    types.InlineKeyboardButton(
                        text=f"{stock} {p['name']} — {p['price']} ₽",
                        callback_data=f"adm:prod:{p['id']}",
                    )
                ]
            )

    buttons.append(
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="adm:main")]
    )
    await callback.message.edit_text(
        "📦 <b>Все товары</b>\nВыберите товар для редактирования:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "adm:noop")
async def admin_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:"))
async def admin_product_card(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    product_id = int(callback.data.split(":")[2])
    p = await get_product(pool, product_id)

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
        text, reply_markup=_product_edit_kb(product_id), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:edit_name:"))
async def admin_edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminEditProduct.entering_value)
    await state.update_data(field="name", product_id=product_id)
    await callback.message.edit_text("✏️ Введите новое название товара:")
    await callback.answer()


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
async def admin_edit_value(
    message: types.Message, state: FSMContext, pool: asyncpg.Pool
):
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

    invalidate()
    await state.clear()
    await message.answer("⚙️ Панель администратора", reply_markup=_admin_main_kb())


@router.callback_query(F.data.startswith("adm:toggle:"))
async def admin_toggle(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    new_status = await admin_toggle_stock(pool, product_id)
    invalidate()
    status_text = "✅ В наличии" if new_status else "❌ Снято с продажи"
    await callback.answer(f"Статус изменён: {status_text}", show_alert=True)
    await admin_product_card(callback, pool)


@router.callback_query(F.data.startswith("adm:del:"))
async def admin_delete_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    product_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "⚠️ <b>Удалить товар?</b>\nЭто действие нельзя отменить.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="🗑 Да, удалить", callback_data=f"adm:del_ok:{product_id}"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🔙 Отмена", callback_data=f"adm:prod:{product_id}"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
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
        "✅ Товар удалён.", reply_markup=_back_kb("adm:products")
    )
    await callback.answer()


@router.callback_query(F.data == "adm:add_product")
async def admin_add_product_start(
    callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool
):
    if not is_admin(callback.from_user.id):
        return

    cats = await get_root_categories(pool)
    buttons = []
    for c in cats:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=c["name"], callback_data=f"adm:pick_cat:{c['id']}"
                )
            ]
        )
        subcats = await get_subcategories(pool, c["id"])
        for sc in subcats:
            buttons.append(
                [
                    types.InlineKeyboardButton(
                        text=f"  ↳ {sc['name']}",
                        callback_data=f"adm:pick_cat:{sc['id']}",
                    )
                ]
            )

    buttons.append(
        [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="adm:main")]
    )
    await state.set_state(AdminAddProduct.choosing_category)
    await callback.message.edit_text(
        "📦 <b>Добавление товара</b>\nВыберите категорию:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    AdminAddProduct.choosing_category, F.data.startswith("adm:pick_cat:")
)
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
    await message.answer(
        f"💰 Товар: <b>{name}</b>\nВведите цену (₽):", parse_mode="HTML"
    )


@router.message(AdminAddProduct.entering_price)
async def admin_product_price(
    message: types.Message, state: FSMContext, pool: asyncpg.Pool
):
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
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✅ Сохранить", callback_data="adm:save_product"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ Отмена", callback_data="adm:main"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


@router.callback_query(AdminAddProduct.confirming, F.data == "adm:save_product")
async def admin_save_product(
    callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool
):
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
        parse_mode="HTML",
    )
    await callback.answer()


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
    buttons = [
        [
            types.InlineKeyboardButton(
                text="🚫 Без родителя (верхний уровень)",
                callback_data="adm:cat_parent:0",
            )
        ]
    ]
    for c in cats:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=c["name"], callback_data=f"adm:cat_parent:{c['id']}"
                )
            ]
        )
    await message.answer(
        f"Категория: <b>{name}</b>\nВыберите родителя:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(
    AdminAddCategory.choosing_parent, F.data.startswith("adm:cat_parent:")
)
async def admin_cat_parent(
    callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool
):
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
        parse_mode="HTML",
    )
    await callback.answer()


MSGS_PER_PAGE = 5


@router.callback_query(F.data.startswith("adm:messages:"))
async def admin_messages(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split(":")[2])
    offset = page * MSGS_PER_PAGE
    messages = await get_all_messages(pool, offset=offset, limit=MSGS_PER_PAGE)
    total = await count_all_messages(pool)
    unread = await get_unread_messages(pool)
    unread_count = len(unread)

    if not messages:
        await callback.message.edit_text(
            "📨 Сообщений нет.", reply_markup=_back_kb("adm:main")
        )
        await callback.answer()
        return

    buttons = []
    for m in messages:
        status = "🆕" if not m["is_read"] else ("↩️" if m["replied_at"] else "✅")
        uname = f"@{m['username']}" if m["username"] else m["full_name"]
        date = m["created_at"].strftime("%d.%m %H:%M")
        short = m["text"][:30] + ("…" if len(m["text"]) > 30 else "")
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=f"{status} {uname} ({date}): {short}",
                    callback_data=f"adm:msg:{m['id']}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(
            types.InlineKeyboardButton(text="◀️", callback_data=f"adm:messages:{page-1}")
        )
    total_pages = max(1, (total - 1) // MSGS_PER_PAGE + 1)
    nav.append(
        types.InlineKeyboardButton(
            text=f"{page+1}/{total_pages}", callback_data="adm:noop"
        )
    )
    if offset + MSGS_PER_PAGE < total:
        nav.append(
            types.InlineKeyboardButton(text="▶️", callback_data=f"adm:messages:{page+1}")
        )
    if nav:
        buttons.append(nav)
    buttons.append(
        [
            types.InlineKeyboardButton(
                text="🗑 Очистить все", callback_data="adm:messages_clear_confirm"
            )
        ]
    )
    buttons.append(
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="adm:main")]
    )

    unread_label = f" (🆕 {unread_count} непрочитанных)" if unread_count else ""
    await callback.message.edit_text(
        f"📨 <b>Сообщения{unread_label}</b>",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:msg:"))
async def admin_view_message(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return

    msg_id = int(callback.data.split(":")[2])
    rows = await pool.fetch(
        """
        SELECT um.*, u.full_name, u.username, u.id AS user_id
        FROM user_messages um
        JOIN users u ON u.id = um.user_id
        WHERE um.id = $1
    """,
        msg_id,
    )

    if not rows:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    m = rows[0]
    await mark_message_read(pool, msg_id)

    uname = f"@{m['username']}" if m["username"] else m["full_name"]
    date = m["created_at"].strftime("%d.%m.%Y %H:%M")
    replied = (
        f"\n↩️ Отвечено: {m['replied_at'].strftime('%d.%m %H:%M')}"
        if m["replied_at"]
        else ""
    )

    text = (
        f"📨 <b>Сообщение #{m['id']}</b>\n\n"
        f"👤 От: <b>{uname}</b> (ID: {m['user_id']})\n"
        f"📅 {date}{replied}\n\n"
        f"💬 {m['text']}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="↩️ Ответить",
                        callback_data=f"adm:reply:{m['id']}:{m['user_id']}",
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🔙 Назад", callback_data="adm:messages:0"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:reply:"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    msg_id, user_id = int(parts[2]), int(parts[3])
    await state.set_state(AdminReply.entering_text)
    await state.update_data(msg_id=msg_id, user_id=user_id)
    await callback.message.edit_text("✏️ Введите текст ответа пользователю:")
    await callback.answer()


@router.message(AdminReply.entering_text)
async def admin_reply_send(
    message: types.Message, state: FSMContext, pool: asyncpg.Pool
):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    user_id = data["user_id"]
    msg_id = data["msg_id"]

    try:
        await message.bot.send_message(
            user_id,
            f"📨 <b>Ответ от администратора:</b>\n\n{message.text}",
            parse_mode="HTML",
        )
        await mark_message_replied(pool, msg_id)
        await message.answer("✅ Ответ отправлен.", reply_markup=_admin_main_kb())
    except Exception as e:
        await message.answer(
            f"❌ Не удалось отправить: {e}", reply_markup=_admin_main_kb()
        )

    await state.clear()


@router.callback_query(F.data == "adm:messages_clear_confirm")
async def admin_messages_clear_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "⚠️ <b>Удалить все сообщения?</b>\n\nЭто действие нельзя отменить.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="🗑 Да, удалить все", callback_data="adm:messages_clear_ok"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🔙 Отмена", callback_data="adm:messages:0"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "adm:messages_clear_ok")
async def admin_messages_clear_ok(callback: types.CallbackQuery, pool: asyncpg.Pool):
    if not is_admin(callback.from_user.id):
        return
    deleted = await clear_all_messages(pool)
    await callback.message.edit_text(
        f"✅ Удалено <b>{deleted}</b> сообщений.",
        reply_markup=_back_kb("adm:main"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "adm:broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminBroadcast.entering_text)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Введите текст сообщения.\n"
        "<i>Поддерживается HTML-разметка: <b>жирный</b>, <i>курсив</i>, <code>моноширинный</code></i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminBroadcast.entering_text)
async def admin_broadcast_preview(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(text=message.text)
    await message.answer(
        f"<b>Предпросмотр:</b>\n\n{message.text}\n\n" f"Отправить всем пользователям?",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="📢 Отправить", callback_data="adm:broadcast_ok"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ Отмена", callback_data="adm:main"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )


@router.callback_query(AdminBroadcast.entering_text, F.data == "adm:broadcast_ok")
async def admin_broadcast_send(
    callback: types.CallbackQuery, state: FSMContext, pool: asyncpg.Pool
):
    if not is_admin(callback.from_user.id):
        return
    data = await state.get_data()
    text = data["text"]
    user_ids = await get_all_user_ids(pool)

    await callback.message.edit_text(f"⏳ Отправляем {len(user_ids)} пользователям...")

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await callback.bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await callback.message.edit_text(
        f"✅ Рассылка завершена\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        reply_markup=_back_kb("adm:main"),
        parse_mode="HTML",
    )
    await callback.answer()


def _admin_main_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 Статистика", callback_data="adm:stats"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="📦 Все товары", callback_data="adm:products"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="➕ Добавить товар", callback_data="adm:add_product"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🗂 Добавить категорию", callback_data="adm:add_category"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="📨 Сообщения", callback_data="adm:messages:0"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="📢 Рассылка", callback_data="adm:broadcast"
                )
            ],
        ]
    )


def _product_edit_kb(product_id: int) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✏️ Название", callback_data=f"adm:edit_name:{product_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="💰 Цена", callback_data=f"adm:edit_price:{product_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🔄 Наличие", callback_data=f"adm:toggle:{product_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"adm:del:{product_id}"
                )
            ],
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="adm:products")],
        ]
    )


def _back_kb(callback_data: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
        ]
    )
