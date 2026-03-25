"""
Простой in-memory кэш для каталога.
TTL по умолчанию — 10 минут. Сбрасывается вручную после изменений в БД.
"""

import time
import asyncpg
from app.db.queries import (
    get_root_categories,
    get_subcategories,
    get_products,
    get_category,
)

CACHE_TTL = 600

_cache: dict[str, tuple] = {}


def _is_fresh(key: str) -> bool:
    if key not in _cache:
        return False
    _, ts = _cache[key]
    return (time.monotonic() - ts) < CACHE_TTL


def _get(key: str):
    if _is_fresh(key):
        data, _ = _cache[key]
        return data
    return None


def _set(key: str, data):
    _cache[key] = (data, time.monotonic())


def invalidate():
    """Полный сброс кэша — вызывать после любых изменений в каталоге."""
    _cache.clear()


async def cached_root_categories(pool: asyncpg.Pool) -> list:
    key = "root_cats"
    data = _get(key)
    if data is None:
        data = await get_root_categories(pool)
        _set(key, data)
    return data


async def cached_subcategories(pool: asyncpg.Pool, parent_id: int) -> list:
    key = f"subcats:{parent_id}"
    data = _get(key)
    if data is None:
        data = await get_subcategories(pool, parent_id)
        _set(key, data)
    return data


async def cached_products(pool: asyncpg.Pool, category_id: int) -> list:
    key = f"products:{category_id}"
    data = _get(key)
    if data is None:
        data = await get_products(pool, category_id)
        _set(key, data)
    return data


async def cached_category(pool: asyncpg.Pool, category_id: int):
    key = f"cat:{category_id}"
    data = _get(key)
    if data is None:
        data = await get_category(pool, category_id)
        _set(key, data)
    return data
