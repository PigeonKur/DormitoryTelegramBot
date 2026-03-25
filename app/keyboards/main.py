import asyncpg
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from app.db.cache import cached_subcategories, cached_products


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏪 Магазин"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="💬 Поддержка")],
            [KeyboardButton(text="👤 Личный кабинет")],
        ],
        resize_keyboard=True,
    )


def catalog_menu(categories: list) -> InlineKeyboardMarkup:
    """Принимает список записей из БД."""
    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"cat:{cat['id']}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def subcategory_or_items_menu(
    pool: asyncpg.Pool,
    cat_id: int,
    parent_back: str,
) -> InlineKeyboardMarkup:
    """Если есть подкатегории — показывает их, иначе товары."""
    subcats = await cached_subcategories(pool, cat_id)
    if subcats:
        buttons = [
            [
                InlineKeyboardButton(
                    text=sub["name"], callback_data=f"sub:{cat_id}:{sub['id']}"
                )
            ]
            for sub in subcats
        ]
        buttons.append(
            [InlineKeyboardButton(text="🔙 Назад", callback_data=parent_back)]
        )
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    products = await cached_products(pool, cat_id)
    return items_menu(products, back_callback=parent_back)


PAGE_SIZE = 8


def items_menu(
    products: list, back_callback: str, page: int = 0
) -> InlineKeyboardMarkup:
    """
    Список товаров с пагинацией.
    Каждая кнопка кодирует back_callback чтобы после «Добавить» знать куда вернуться.
    """
    total = len(products)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = products[start:end]

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{p['name']} — {p['price']} ₽",
                callback_data=f"item:{p['id']}:{back_callback}",
            )
        ]
        for p in page_items
    ]

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️", callback_data=f"page:{back_callback}:{page - 1}"
            )
        )
    if total > 0:
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{(total - 1) // PAGE_SIZE + 1}", callback_data="noop"
            )
        )
    if end < total:
        nav.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"page:{back_callback}:{page + 1}"
            )
        )
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def item_card_menu(product_id: int, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить в корзину",
                    callback_data=f"add:{product_id}:{back_callback}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)],
        ]
    )


def cart_menu(has_items: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_items:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Оформить заказ", callback_data="cart:checkout"
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🗑 Очистить корзину", callback_data="cart:clear"
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="🏪 В магазин", callback_data="to_catalog")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def delivery_menu(from_profile: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="🚪 Оставить у двери", callback_data="delivery:door"
            )
        ],
        [InlineKeyboardButton(text="🤝 Отдать в руки", callback_data="delivery:hand")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", callback_data="order:pay")],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить доставку", callback_data="order:change_delivery"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить заказ", callback_data="order:cancel"
                )
            ],
        ]
    )


def profile_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Мои заказы", callback_data="profile:orders"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚚 Тип доставки", callback_data="profile:delivery"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📍 Номер комнаты", callback_data="profile:room"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Реферальная программа", callback_data="profile:referral"
                )
            ],
        ]
    )


def profile_referral_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="profile:back")],
        ]
    )
