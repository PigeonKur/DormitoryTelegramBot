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
#  ПОЛЬЗОВАТЕЛИ — РАСШИРЕННЫЕ
# ════════════════════════════════════════════════════════════

async def get_user_stats(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    """Пользователь + кол-во рефералов + сумма всех заказов."""
    return await pool.fetchrow("""
        SELECT
            u.*,
            COUNT(DISTINCT r.id)  AS referral_count,
            COALESCE(SUM(o.total_price) FILTER (WHERE o.status = 'paid'), 0) AS total_spent
        FROM users u
        LEFT JOIN users r  ON r.referred_by = u.id
        LEFT JOIN orders o ON o.user_id = u.id
        WHERE u.id = $1
        GROUP BY u.id
    """, user_id)


async def get_user_by_ref_code(pool: asyncpg.Pool, ref_code: str) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM users WHERE ref_code = $1", ref_code)


async def set_ref_code(pool: asyncpg.Pool, user_id: int, ref_code: str) -> None:
    await pool.execute(
        "UPDATE users SET ref_code = $1 WHERE id = $2",
        ref_code, user_id
    )


async def set_referred_by(pool: asyncpg.Pool, user_id: int, referrer_id: int) -> None:
    """Записываем реферера — только если ещё не установлен."""
    await pool.execute("""
        UPDATE users SET referred_by = $1
        WHERE id = $2 AND referred_by IS NULL
    """, referrer_id, user_id)


async def add_balance(pool: asyncpg.Pool, user_id: int, amount: int) -> int:
    """Начисляет бонусы. Возвращает новый баланс."""
    row = await pool.fetchrow("""
        UPDATE users SET balance = balance + $1
        WHERE id = $2
        RETURNING balance
    """, amount, user_id)
    return row["balance"]


async def spend_balance(pool: asyncpg.Pool, user_id: int, amount: int) -> bool:
    """Списывает бонусы если хватает. Возвращает True при успехе."""
    row = await pool.fetchrow("""
        UPDATE users SET balance = balance - $1
        WHERE id = $2 AND balance >= $1
        RETURNING balance
    """, amount, user_id)
    return row is not None


# ════════════════════════════════════════════════════════════
#  РЕФЕРАЛЬНЫЕ НАЧИСЛЕНИЯ
# ════════════════════════════════════════════════════════════

# Процент от суммы заказа, который идёт рефереру (10%)
REFERRAL_PERCENT = 10

async def process_referral_reward(
    pool: asyncpg.Pool,
    referee_id: int,
    order_id: int,
    order_total: int,
) -> int | None:
    """
    Начисляет бонус рефереру при оплате заказа.
    Возвращает id реферера если начисление прошло, иначе None.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Находим реферера
            row = await conn.fetchrow(
                "SELECT referred_by FROM users WHERE id = $1", referee_id
            )
            if not row or not row["referred_by"]:
                return None

            referrer_id = row["referred_by"]
            amount = max(1, order_total * REFERRAL_PERCENT // 100)

            # Начисляем баланс
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE id = $2",
                amount, referrer_id
            )

            # Пишем в историю
            await conn.execute("""
                INSERT INTO referral_rewards (referrer_id, referee_id, order_id, amount)
                VALUES ($1, $2, $3, $4)
            """, referrer_id, referee_id, order_id, amount)

    return referrer_id


async def get_referral_history(pool: asyncpg.Pool, user_id: int) -> list[asyncpg.Record]:
    """История реферальных начислений для пользователя."""
    return await pool.fetch("""
        SELECT
            rr.amount,
            rr.created_at,
            u.full_name AS referee_name
        FROM referral_rewards rr
        JOIN users u ON u.id = rr.referee_id
        WHERE rr.referrer_id = $1
        ORDER BY rr.created_at DESC
        LIMIT 20
    """, user_id)


async def get_referrals_list(pool: asyncpg.Pool, user_id: int) -> list[asyncpg.Record]:
    """Список приглашённых пользователей."""
    return await pool.fetch("""
        SELECT full_name, created_at
        FROM users
        WHERE referred_by = $1
        ORDER BY created_at DESC
    """, user_id)

# ════════════════════════════════════════════════════════════
#  КОРЗИНА
# ════════════════════════════════════════════════════════════

async def cart_add_item(pool: asyncpg.Pool, user_id: int, product_id: int) -> int:
    """Добавляет товар или увеличивает количество. Возвращает новое quantity."""
    row = await pool.fetchrow("""
        INSERT INTO cart_items (user_id, product_id, quantity)
        VALUES ($1, $2, 1)
        ON CONFLICT (user_id, product_id)
        DO UPDATE SET quantity = cart_items.quantity + 1
        RETURNING quantity
    """, user_id, product_id)
    return row["quantity"]


async def cart_get_items(pool: asyncpg.Pool, user_id: int) -> list[asyncpg.Record]:
    """Возвращает все позиции корзины с данными товара."""
    return await pool.fetch("""
        SELECT
            ci.product_id,
            ci.quantity,
            p.name,
            p.price,
            p.in_stock
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.user_id = $1
        ORDER BY ci.added_at
    """, user_id)


async def cart_change_qty(pool: asyncpg.Pool, user_id: int, product_id: int, delta: int) -> int:
    """Изменяет количество на delta. Если <= 0 — удаляет. Возвращает новое quantity (0 = удалено)."""
    row = await pool.fetchrow("""
        UPDATE cart_items
        SET quantity = GREATEST(0, quantity + $3)
        WHERE user_id = $1 AND product_id = $2
        RETURNING quantity
    """, user_id, product_id, delta)

    if not row or row["quantity"] == 0:
        await pool.execute(
            "DELETE FROM cart_items WHERE user_id = $1 AND product_id = $2",
            user_id, product_id
        )
        return 0
    return row["quantity"]


async def cart_delete_item(pool: asyncpg.Pool, user_id: int, product_id: int) -> None:
    await pool.execute(
        "DELETE FROM cart_items WHERE user_id = $1 AND product_id = $2",
        user_id, product_id
    )


async def cart_clear(pool: asyncpg.Pool, user_id: int) -> None:
    await pool.execute("DELETE FROM cart_items WHERE user_id = $1", user_id)


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

# ════════════════════════════════════════════════════════════
#  АДМИН — УПРАВЛЕНИЕ КАТАЛОГОМ
# ════════════════════════════════════════════════════════════

async def admin_add_product(
    pool: asyncpg.Pool,
    category_id: int,
    name: str,
    price: int,
) -> int:
    """Добавляет товар. Возвращает id."""
    row = await pool.fetchrow("""
        INSERT INTO products (category_id, name, price)
        VALUES ($1, $2, $3)
        RETURNING id
    """, category_id, name, price)
    return row["id"]


async def admin_edit_product_name(pool: asyncpg.Pool, product_id: int, name: str) -> None:
    await pool.execute("UPDATE products SET name = $1 WHERE id = $2", name, product_id)


async def admin_edit_product_price(pool: asyncpg.Pool, product_id: int, price: int) -> None:
    await pool.execute("UPDATE products SET price = $1 WHERE id = $2", price, product_id)


async def admin_toggle_stock(pool: asyncpg.Pool, product_id: int) -> bool:
    """Переключает in_stock. Возвращает новое значение."""
    row = await pool.fetchrow("""
        UPDATE products SET in_stock = NOT in_stock
        WHERE id = $1 RETURNING in_stock
    """, product_id)
    return row["in_stock"]


async def admin_delete_product(pool: asyncpg.Pool, product_id: int) -> None:
    await pool.execute("DELETE FROM products WHERE id = $1", product_id)


async def admin_add_category(
    pool: asyncpg.Pool,
    name: str,
    parent_id: int | None = None,
) -> int:
    row = await pool.fetchrow("""
        INSERT INTO categories (name, slug, parent_id)
        VALUES ($1, $2, $3)
        RETURNING id
    """, name, _slugify(name), parent_id)
    return row["id"]


async def admin_get_all_products(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("""
        SELECT p.id, p.name, p.price, p.in_stock, c.name AS category_name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        ORDER BY c.name, p.name
    """)


async def admin_get_stats(pool: asyncpg.Pool) -> asyncpg.Record:
    return await pool.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM users)                              AS total_users,
            (SELECT COUNT(*) FROM orders WHERE status = 'paid')       AS total_orders,
            (SELECT COALESCE(SUM(total_price),0) FROM orders
             WHERE status = 'paid')                                   AS total_revenue,
            (SELECT COUNT(*) FROM orders
             WHERE status = 'paid'
             AND created_at >= NOW() - INTERVAL '1 day')              AS orders_today,
            (SELECT COALESCE(SUM(total_price),0) FROM orders
             WHERE status = 'paid'
             AND created_at >= NOW() - INTERVAL '1 day')              AS revenue_today
    """)


def _slugify(name: str) -> str:
    import re, uuid
    slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", name).strip("_").lower()
    return slug or str(uuid.uuid4())[:8]


# ════════════════════════════════════════════════════════════
#  СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЕЙ
# ════════════════════════════════════════════════════════════

async def save_user_message(pool: asyncpg.Pool, user_id: int, text: str) -> int:
    row = await pool.fetchrow("""
        INSERT INTO user_messages (user_id, text)
        VALUES ($1, $2) RETURNING id
    """, user_id, text)
    return row["id"]


async def get_unread_messages(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("""
        SELECT um.id, um.text, um.created_at,
               u.full_name, u.username, u.id AS user_id
        FROM user_messages um
        JOIN users u ON u.id = um.user_id
        WHERE um.is_read = FALSE
        ORDER BY um.created_at DESC
        LIMIT 30
    """)


async def get_all_messages(pool: asyncpg.Pool, offset: int = 0, limit: int = 10) -> list[asyncpg.Record]:
    return await pool.fetch("""
        SELECT um.id, um.text, um.created_at, um.is_read, um.replied_at,
               u.full_name, u.username, u.id AS user_id
        FROM user_messages um
        JOIN users u ON u.id = um.user_id
        ORDER BY um.created_at DESC
        LIMIT $1 OFFSET $2
    """, limit, offset)


async def count_all_messages(pool: asyncpg.Pool) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM user_messages")


async def mark_message_read(pool: asyncpg.Pool, message_id: int) -> None:
    await pool.execute(
        "UPDATE user_messages SET is_read = TRUE WHERE id = $1", message_id
    )


async def mark_message_replied(pool: asyncpg.Pool, message_id: int) -> None:
    await pool.execute("""
        UPDATE user_messages SET is_read = TRUE, replied_at = NOW()
        WHERE id = $1
    """, message_id)


# ════════════════════════════════════════════════════════════
#  ПОИСК ТОВАРОВ
# ════════════════════════════════════════════════════════════

async def search_products(pool: asyncpg.Pool, query: str) -> list[asyncpg.Record]:
    """Полнотекстовый поиск по названию товара (регистронезависимый)."""
    return await pool.fetch("""
        SELECT p.id, p.name, p.price, p.in_stock,
               c.name AS category_name, c.id AS category_id,
               c.parent_id
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.in_stock = TRUE
          AND p.name ILIKE $1
        ORDER BY p.name
        LIMIT 20
    """, f"%{query}%")


# ════════════════════════════════════════════════════════════
#  РАССЫЛКА
# ════════════════════════════════════════════════════════════

async def get_all_user_ids(pool: asyncpg.Pool) -> list[int]:
    rows = await pool.fetch("SELECT id FROM users")
    return [r["id"] for r in rows]

