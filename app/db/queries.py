"""
Все SQL-запросы проекта.
Каждая функция принимает pool (или conn) первым аргументом.
"""
import asyncpg


# ════════════════════════════════════════════════════════════
#  ПОЛЬЗОВАТЕЛИ
# ════════════════════════════════════════════════════════════

async def upsert_user(pool: asyncpg.Pool, telegram_id: int, username: str | None, full_name: str) -> None:
    """Создаёт пользователя или обновляет имя/username если уже есть."""
    await pool.execute("""
        INSERT INTO users (id, username, full_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (id) DO UPDATE
            SET username  = EXCLUDED.username,
                full_name = EXCLUDED.full_name
    """, telegram_id, username, full_name)


async def get_user(pool: asyncpg.Pool, telegram_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM users WHERE id = $1", telegram_id)


async def set_delivery_type(pool: asyncpg.Pool, telegram_id: int, delivery_type: str) -> None:
    await pool.execute(
        "UPDATE users SET delivery_type = $1 WHERE id = $2",
        delivery_type, telegram_id
    )


async def set_room_number(pool: asyncpg.Pool, telegram_id: int, room: str) -> None:
    await pool.execute(
        "UPDATE users SET room_number = $1 WHERE id = $2",
        room, telegram_id
    )


# ════════════════════════════════════════════════════════════
#  КАТАЛОГ
# ════════════════════════════════════════════════════════════

async def get_root_categories(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Категории верхнего уровня (без родителя)."""
    return await pool.fetch("""
        SELECT id, slug, name
        FROM categories
        WHERE parent_id IS NULL
        ORDER BY sort_order, id
    """)


async def get_subcategories(pool: asyncpg.Pool, parent_id: int) -> list[asyncpg.Record]:
    """Подкатегории для указанного родителя."""
    return await pool.fetch("""
        SELECT id, slug, name
        FROM categories
        WHERE parent_id = $1
        ORDER BY sort_order, id
    """, parent_id)


async def get_category(pool: asyncpg.Pool, category_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM categories WHERE id = $1", category_id)


async def get_category_by_slug(pool: asyncpg.Pool, slug: str) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM categories WHERE slug = $1", slug)


async def get_products(pool: asyncpg.Pool, category_id: int) -> list[asyncpg.Record]:
    """Товары категории, только в наличии."""
    return await pool.fetch("""
        SELECT id, name, price
        FROM products
        WHERE category_id = $1 AND in_stock = TRUE
        ORDER BY sort_order, id
    """, category_id)


async def get_product(pool: asyncpg.Pool, product_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM products WHERE id = $1 AND in_stock = TRUE",
        product_id
    )


# ════════════════════════════════════════════════════════════
#  ЗАКАЗЫ
# ════════════════════════════════════════════════════════════

async def create_order(
    pool: asyncpg.Pool,
    user_id: int,
    delivery_type: str,
    total_price: int,
    items: list[dict],          # [{"product_id", "name", "price", "quantity"}, ...]
) -> int:
    """Создаёт заказ и его позиции в одной транзакции. Возвращает id заказа."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            order_id = await conn.fetchval("""
                INSERT INTO orders (user_id, delivery_type, total_price)
                VALUES ($1, $2, $3)
                RETURNING id
            """, user_id, delivery_type, total_price)

            await conn.executemany("""
                INSERT INTO order_items (order_id, product_id, name, price, quantity)
                VALUES ($1, $2, $3, $4, $5)
            """, [
                (order_id, i["product_id"], i["name"], i["price"], i["quantity"])
                for i in items
            ])

    return order_id


async def get_user_orders(pool: asyncpg.Pool, user_id: int) -> list[asyncpg.Record]:
    """Последние 10 заказов пользователя."""
    return await pool.fetch("""
        SELECT id, total_price, delivery_type, status, created_at
        FROM orders
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 10
    """, user_id)


async def get_order_items(pool: asyncpg.Pool, order_id: int) -> list[asyncpg.Record]:
    return await pool.fetch("""
        SELECT name, price, quantity
        FROM order_items
        WHERE order_id = $1
    """, order_id)


async def update_order_status(pool: asyncpg.Pool, order_id: int, status: str) -> None:
    await pool.execute(
        "UPDATE orders SET status = $1 WHERE id = $2",
        status, order_id
    )
