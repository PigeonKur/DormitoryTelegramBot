import random
import string
import asyncpg
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.keyboards.main import main_menu
from app.db.queries import (
    upsert_user, get_user, set_ref_code,
    get_user_by_ref_code, set_referred_by,
)

router = Router()


def _generate_ref_code(user_id: int) -> str:
    """Короткий уникальный реф-код: 3 буквы + 4 цифры из id."""
    letters = random.choices(string.ascii_uppercase, k=3)
    return "".join(letters) + str(user_id)[-4:].zfill(4)


@router.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext, pool: asyncpg.Pool):
    await state.clear()
    user_id = message.from_user.id

    # Создаём/обновляем пользователя
    await upsert_user(
        pool=pool,
        telegram_id=user_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # Генерируем реф-код если ещё нет
    user = await get_user(pool, user_id)
    if not user["ref_code"]:
        await set_ref_code(pool, user_id, _generate_ref_code(user_id))

    # Обрабатываем реферальную ссылку: /start ref_ABC1234
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        ref_code = args[1].strip()
        referrer = await get_user_by_ref_code(pool, ref_code)
        if referrer and referrer["id"] != user_id:
            await set_referred_by(pool, user_id, referrer["id"])
            # Уведомляем реферера
            try:
                await message.bot.send_message(
                    referrer["id"],
                    f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n"
                    f"Вы получите <b>{10}%</b> бонусами с его первого заказа.",
                    parse_mode="HTML"
                )
            except Exception:
                pass  # пользователь мог заблокировать бота

    await message.answer(
        "👋 Добро пожаловать в магазин общежития!\n\n"
        "Здесь вы можете заказать продукты прямо в свою комнату.\n"
        "Выберите нужный раздел 👇",
        reply_markup=main_menu()
    )
