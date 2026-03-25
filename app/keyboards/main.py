import asyncpg
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from app.db.cache import cached_subcategories, cached_products


# ── Reply-клавиатура ─────────────────────────────────────────

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏪 Магазин")],
            [KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="👤 Личный кабинет")],
        ],
        resize_keyboard=True,
    )


# ── Каталог (1-й уровень) ────────────────────────────────────

def catalog_menu(categories: list) -> InlineKeyboardMarkup:
    """Принимает список записей из БД."""
    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"cat:{cat['id']}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Подкатегории или товары (2-й уровень) ────────────────────

async def subcategory_or_items_menu(
    pool: asyncpg.Pool,
    cat_id: int,
    parent_back: str,
) -> InlineKeyboardMarkup:
    """Если есть подкатегории — показывает их, иначе товары."""
    subcats = await cached_subcategories(pool, cat_id)
    if subcats:
        buttons = [
            [InlineKeyboardButton(
                text=sub["name"],
                callback_data=f"sub:{cat_id}:{sub['id']}"
            )]
            for sub in subcats
        ]
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=parent_back)])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    # Нет подкатегорий — товары
    products = await cached_products(pool, cat_id)
    return items_menu(products, back_callback=parent_back)


# ── Список товаров ───────────────────────────────────────────

def items_menu(products: list, back_callback: str) -> InlineKeyboardMarkup:
    """
    Каждая кнопка товара кодирует back_callback внутри себя,
    чтобы после «Добавить» знать куда вернуться.
    """
    buttons = [
        [InlineKeyboardButton(
            text=f"{p['name']} — {p['price']} ₽",
            callback_data=f"item:{p['id']}:{back_callback}"
        )]
        for p in products
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Карточка товара ──────────────────────────────────────────

def item_card_menu(product_id: int, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="➕ Добавить в корзину",
                callback_data=f"add:{product_id}:{back_callback}"
            )],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)],
        ]
    )


# ── Корзина ──────────────────────────────────────────────────

def cart_menu(has_items: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_items:
        buttons.append([InlineKeyboardButton(text="✅ Оформить заказ",  callback_data="cart:checkout")])
        buttons.append([InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton(text="🏪 В магазин", callback_data="to_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Способ доставки ──────────────────────────────────────────

def delivery_menu(from_profile: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚪 Оставить у двери", callback_data="delivery:door")],
        [InlineKeyboardButton(text="🤝 Отдать в руки",    callback_data="delivery:hand")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Подтверждение заказа ─────────────────────────────────────

def order_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить",          callback_data="order:pay")],
            [InlineKeyboardButton(text="✏️ Изменить доставку",  callback_data="order:change_delivery")],
            [InlineKeyboardButton(text="❌ Отменить заказ",     callback_data="order:cancel")],
        ]
    )


# ── Личный кабинет ───────────────────────────────────────────

def profile_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Мои заказы",           callback_data="profile:orders")],
            [InlineKeyboardButton(text="🚚 Тип доставки",         callback_data="profile:delivery")],
            [InlineKeyboardButton(text="📍 Номер комнаты",        callback_data="profile:room")],
            [InlineKeyboardButton(text="👥 Реферальная программа",callback_data="profile:referral")],
        ]
    )


def profile_referral_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile:back")],
        ]
    )
