"""
Поиск товаров + обработка неизвестных сообщений.
"""
import asyncpg
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from app.db.queries import search_products, save_user_message
from app.db.cache import cached_products
from app.keyboards.main import items_menu
from config import ADMIN_IDS

router = Router()


class SearchState(StatesGroup):
    waiting_query = State()


# ── Кнопка / команда поиска ──────────────────────────────────

@router.message(F.text == "🔍 Поиск")
@router.message(F.text.startswith("/search"))
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "🔍 Введите название товара или его часть:\n"
        "<i>Например: вода, чипсы, макар</i>",
        parse_mode="HTML"
    )


@router.message(SearchState.waiting_query)
async def search_process(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("❌ Введите минимум 2 символа:")
        return

    await state.clear()
    results = await search_products(pool, query)

    if not results:
        await message.answer(
            f"😔 По запросу <b>«{query}»</b> ничего не найдено.\n\n"
            f"Попробуйте другое слово.",
            parse_mode="HTML"
        )
        return

    # Формируем псевдо-список как для items_menu
    await message.answer(
        f"🔍 Найдено <b>{len(results)}</b> товаров по запросу «{query}»:",
        reply_markup=items_menu(results, back_callback="to_catalog"),
        parse_mode="HTML"
    )


# ── Пагинация ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def pagination_callback(callback: types.CallbackQuery, pool: asyncpg.Pool):
    # Формат: page:<back_callback>:<page_number>
    # back_callback может содержать ":", поэтому берём с конца
    parts = callback.data.split(":")
    page = int(parts[-1])
    back_cb = ":".join(parts[1:-1])

    # Загружаем товары в зависимости от back_callback
    if back_cb.startswith("cat:"):
        cat_id = int(back_cb.split(":")[1])
        products = await cached_products(pool, cat_id)
    elif back_cb.startswith("sub:"):
        sub_parts = back_cb.split(":")
        sub_id = int(sub_parts[2])
        products = await cached_products(pool, sub_id)
    else:
        await callback.answer()
        return

    await callback.message.edit_reply_markup(
        reply_markup=items_menu(products, back_callback=back_cb, page=page)
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()


# ── Неизвестные сообщения ────────────────────────────────────

@router.message()
async def unknown_message(message: types.Message, pool: asyncpg.Pool):
    user_id = message.from_user.id

    # Сохраняем в БД
    await save_user_message(pool, user_id, message.text or "[не текст]")

    await message.answer(
        "📨 Ваше сообщение получено и будет передано администратору.\n"
        "Мы ответим вам в ближайшее время."
    )
