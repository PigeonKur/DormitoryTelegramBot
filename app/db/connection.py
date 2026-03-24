import asyncpg
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

# Глобальный пул — создаётся один раз при старте бота
_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Создаёт пул соединений и возвращает его."""
    global _pool
    _pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=1,
        max_size=10,
        server_settings={
            'search_path': 'dormitory_shop, public'
        }
    )
    return _pool


async def close_pool():
    """Закрывает пул при остановке бота."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Возвращает существующий пул. Вызывать только после create_pool()."""
    if _pool is None:
        raise RuntimeError("Пул соединений не создан. Вызови create_pool() при старте.")
    return _pool
