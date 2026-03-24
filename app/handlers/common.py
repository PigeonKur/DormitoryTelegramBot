from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import (
    catalog_menu, subcategory_menu, items_menu, item_card_menu, profile_menu
)
from app.data.catalog import CATALOG, ITEMS_INDEX

router = Router()


# ───────────────────────────── Магазин ──────────────────────────────────────

@router.message(F.text == "🏪 Магазин")
async def shop_handler(message: types.Message):
    await message.answer("🏪 Выберите категорию:", reply_markup=catalog_menu())


# ───────────────────────────── Личный кабинет ───────────────────────────────

@router.message(F.text == "👤 Личный кабинет")
async def profile_handler(message: types.Message):
    await message.answer("👤 Личный кабинет", reply_markup=profile_menu())


@router.callback_query(F.data.startswith("profile:"))
async def profile_callback(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]
    if action == "orders":
        await callback.message.edit_text("📦 История заказов пока пуста.\n(Появится после подключения БД)")
    elif action == "delivery":
        await callback.message.edit_text("🚪 Смена типа доставки будет доступна после подключения БД.")
    elif action == "room":
        await callback.message.edit_text("📍 Номер комнаты будет сохраняться после подключения БД.")
    await callback.answer()


# ───────────────────────────── Навигация по каталогу ────────────────────────

@router.callback_query(F.data == "to_catalog")
async def to_catalog(callback: types.CallbackQuery):
    await callback.message.edit_text("🏪 Выберите категорию:", reply_markup=catalog_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_callback(callback: types.CallbackQuery):
    cat_key = callback.data.split(":")[1]
    cat = CATALOG.get(cat_key)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    if "subcategories" in cat:
        # Есть подкатегории — показываем их
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите подкатегорию:",
            reply_markup=subcategory_menu(cat_key)
        )
    else:
        # Нет подкатегорий — сразу показываем товары
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите товар:",
            reply_markup=items_menu(cat["items"], back_callback="to_catalog")
        )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def subcategory_callback(callback: types.CallbackQuery):
    _, cat_key, sub_key = callback.data.split(":")
    cat = CATALOG.get(cat_key)
    sub = cat["subcategories"].get(sub_key) if cat else None
    if not sub:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        f"{sub['name']}\n\nВыберите товар:",
        reply_markup=items_menu(sub["items"], back_callback=f"cat:{cat_key}")
    )
    await callback.answer()


# ───────────────────────────── Карточка товара ──────────────────────────────

@router.callback_query(F.data.startswith("item:"))
async def item_callback(callback: types.CallbackQuery):
    item_id = callback.data.split(":")[1]
    item = ITEMS_INDEX.get(item_id)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    # Определяем кнопку "Назад"
    if "subcategory" in item:
        back_cb = f"sub:{item['category']}:{item['subcategory']}"
    else:
        back_cb = f"cat:{item['category']}"

    text = (
        f"🛍 <b>{item['name']}</b>\n\n"
        f"💰 Цена: <b>{item['price']} ₽</b>\n\n"
        f"Добавить товар в корзину?"
    )
    await callback.message.edit_text(text, reply_markup=item_card_menu(item_id, back_cb), parse_mode="HTML")
    await callback.answer()
