"""
Антиспам middleware.
Не более MAX_CALLS действий за PERIOD секунд на пользователя.
"""

import time
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

MAX_CALLS = 8
PERIOD = 3.0


class AntispamMiddleware(BaseMiddleware):
    def __init__(self):
        self._history: dict[int, list[float]] = defaultdict(list)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)

        now = time.monotonic()
        self._history[user_id] = [t for t in self._history[user_id] if now - t < PERIOD]

        if len(self._history[user_id]) >= MAX_CALLS:
            if isinstance(event, CallbackQuery):
                await event.answer(
                    "⏳ Не так быстро! Подождите секунду.", show_alert=False
                )
            elif isinstance(event, Message):
                await event.answer("⏳ Не так быстро! Подождите секунду.")
            return

        self._history[user_id].append(now)
        return await handler(event, data)
