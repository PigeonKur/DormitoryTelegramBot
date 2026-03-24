# import asyncpg

# async def save_application(db, user_id, name, city, age):
#     async with db.acquire() as conn:
#         await conn.execute(
#             """
#             INSERT INTO "telegaTest".applications (user_id, name, city, age)
#             VALUES ($1, $2, $3, $4)
#             """,
#             user_id, name, city, age
#         )


# async def search_user(db, user_id):
#     async with db.acquire() as conn:
#         return await conn.fetch(
#             """
#             SELECT *
#             FROM "telegaTest".applications
#             WHERE user_id = $1
#             ORDER BY id DESC
#             """,
#             user_id
#         )
    
# async def get_all_applications(db):
#     async with db.acquire() as conn:
#         return await conn.fetch(
#             'SELECT * FROM "telegaTest".applications ORDER BY created_at DESC'
#         )
   
# async def update_application_status(db, app_id: int, status: str):
#     async with db.acquire() as conn:
#         await conn.execute(
#             """
#             UPDATE "telegaTest".applications
#             SET status = $1
#             WHERE id = $2
#             """,
#             status, app_id
#         )

# async def get_application_by_id(db, app_id: int):
#     async with db.acquire() as conn:
#         return await conn.fetchrow(
#             'SELECT * FROM "telegaTest".applications WHERE id = $1',
#             app_id
#         )

