import asyncpg
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.keyboards.main import main_menu
from app.db.queries import upsert_user

router = Router()


@router.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    # Сбрасываем состояние и сохраняем/обновляем пользователя в БД
    await state.clear()
    await upsert_user(
        pool=pool,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        "👋 Добро пожаловать в магазин общежития!\n\n"
        "Здесь вы можете заказать продукты прямо в свою комнату.\n"
        "Выберите нужный раздел 👇",
        reply_markup=main_menu()
    )
