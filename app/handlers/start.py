from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.keyboards.main import main_menu

router = Router()


@router.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в магазин общежития!\n\n"
        "Здесь вы можете заказать продукты прямо в свою комнату.\n"
        "Выберите нужный раздел 👇",
        reply_markup=main_menu()
    )
