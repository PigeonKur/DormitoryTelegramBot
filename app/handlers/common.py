import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from app.keyboards.main import (
    catalog_menu,
    subcategory_or_items_menu,
    items_menu,
    item_card_menu,
)
from app.db.queries import get_product
from app.db.cache import (
    cached_root_categories,
    cached_subcategories,
    cached_products,
    cached_category,
)

router = Router()

DELIVERY_LABELS = {
    "hand": "🤝 Отдать в руки",
    "door": "🚪 Оставить у двери",
}


@router.message(F.text == "🏪 Магазин")
async def shop_handler(message: types.Message, pool: asyncpg.Pool):
    cats = await cached_root_categories(pool)
    await message.answer("🏪 Выберите категорию:", reply_markup=catalog_menu(cats))


@router.callback_query(F.data == "to_catalog")
async def to_catalog(callback: types.CallbackQuery, pool: asyncpg.Pool):
    cats = await cached_root_categories(pool)
    await callback.message.edit_text(
        "🏪 Выберите категорию:", reply_markup=catalog_menu(cats)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    cat_id = int(callback.data.split(":")[1])
    cat = await cached_category(pool, cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    subcats = await cached_subcategories(pool, cat_id)
    if subcats:
        kb = await subcategory_or_items_menu(pool, cat_id, parent_back="to_catalog")
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите подкатегорию:", reply_markup=kb
        )
    else:
        products = await cached_products(pool, cat_id)
        await callback.message.edit_text(
            f"{cat['name']}\n\nВыберите товар:",
            reply_markup=items_menu(products, back_callback="to_catalog"),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def subcategory_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    _, cat_id_str, sub_id_str = callback.data.split(":")
    sub_id = int(sub_id_str)
    sub = await cached_category(pool, sub_id)
    if not sub:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return

    products = await cached_products(pool, sub_id)
    await callback.message.edit_text(
        f"{sub['name']}\n\nВыберите товар:",
        reply_markup=items_menu(products, back_callback=f"cat:{cat_id_str}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("item:"))
async def item_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    parts = callback.data.split(":")  # item:<product_id>:<back_callback>
    product_id = int(parts[1])
    back_cb = ":".join(parts[2:]) if len(parts) > 2 else "to_catalog"

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
        text, reply_markup=item_card_menu(product_id, back_cb), parse_mode="HTML"
    )
    await callback.answer()
