import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from app.middleware.antispam import AntispamMiddleware
from app.db.connection import create_pool, close_pool
from app.handlers import start, common, cart, profile, admin, search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    # ── БД ──────────────────────────────────────────────────
    log.info("Подключаемся к базе данных...")
    pool = await create_pool()
    log.info("✅ Пул соединений создан")

    # ── Бот и диспетчер ─────────────────────────────────────
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Прокидываем pool во все хендлеры через workflow_data
    # После этого любой хендлер может принять аргумент pool: asyncpg.Pool
    dp.workflow_data["pool"] = pool

    dp.message.middleware(AntispamMiddleware())
    dp.callback_query.middleware(AntispamMiddleware())

    dp.include_router(start.router)
    dp.include_router(common.router)
    dp.include_router(cart.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(search.router)  # search последним — ловит все неизвестные сообщения

    log.info("✅ Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await close_pool()
        log.info("Пул соединений закрыт")


if __name__ == "__main__":
    asyncio.run(main())
