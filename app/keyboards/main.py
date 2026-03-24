from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from app.data.catalog import CATALOG


# ───────────────────────────── Reply-клавиатура ─────────────────────────────

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏪 Магазин")],
            [KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="👤 Личный кабинет")],
        ],
        resize_keyboard=True,
    )


# ───────────────────────────── Каталог (1-й уровень) ────────────────────────

def catalog_menu() -> InlineKeyboardMarkup:
    """Динамически строит главное меню каталога из CATALOG."""
    buttons = []
    for key, cat in CATALOG.items():
        buttons.append([InlineKeyboardButton(text=cat["name"], callback_data=f"cat:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ───────────────────────────── Подкатегории (2-й уровень) ───────────────────

def subcategory_menu(cat_key: str) -> InlineKeyboardMarkup:
    """Меню подкатегорий, если они есть; иначе сразу список товаров."""
    cat = CATALOG[cat_key]
    buttons = []
    if "subcategories" in cat:
        for sub_key, sub in cat["subcategories"].items():
            buttons.append([
                InlineKeyboardButton(text=sub["name"], callback_data=f"sub:{cat_key}:{sub_key}")
            ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="to_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ───────────────────────────── Товары (список) ──────────────────────────────

def items_menu(items: list, back_callback: str) -> InlineKeyboardMarkup:
    """Список товаров с ценой; кнопка Назад."""
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton(
                text=f"{item['name']} — {item['price']} ₽",
                callback_data=f"item:{item['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ───────────────────────────── Карточка товара ──────────────────────────────

def item_card_menu(item_id: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить в корзину", callback_data=f"add:{item_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)],
        ]
    )


# ───────────────────────────── Корзина ──────────────────────────────────────

def cart_menu(has_items: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_items:
        buttons.append([InlineKeyboardButton(text="✅ Оформить заказ", callback_data="cart:checkout")])
        buttons.append([InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart:clear")])
    buttons.append([InlineKeyboardButton(text="🏪 В магазин", callback_data="to_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_item_menu(item_id: str) -> InlineKeyboardMarkup:
    """Кнопки управления количеством внутри корзины."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data=f"qty:dec:{item_id}"),
                InlineKeyboardButton(text="➕", callback_data=f"qty:inc:{item_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"qty:del:{item_id}"),
            ]
        ]
    )


# ───────────────────────────── Способ доставки ──────────────────────────────

def delivery_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Оставить у двери", callback_data="delivery:door")],
            [InlineKeyboardButton(text="🤝 Отдать в руки",    callback_data="delivery:hand")],
        ]
    )


# ───────────────────────────── Подтверждение заказа ─────────────────────────

def order_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить",         callback_data="order:pay")],
            [InlineKeyboardButton(text="✏️ Изменить доставку", callback_data="order:change_delivery")],
            [InlineKeyboardButton(text="❌ Отменить заказ",    callback_data="order:cancel")],
        ]
    )


# ───────────────────────────── Личный кабинет ───────────────────────────────

def profile_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Мои заказы",          callback_data="profile:orders")],
            [InlineKeyboardButton(text="🚪 Изменить тип доставки", callback_data="profile:delivery")],
            [InlineKeyboardButton(text="📍 Мой номер комнаты",    callback_data="profile:room")],
        ]
    )
