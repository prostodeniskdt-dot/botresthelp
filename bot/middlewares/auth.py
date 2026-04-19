from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.content import MSG_NOT_EMPLOYEE
from bot.storage import load_allowed_users, user_allowed


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        rules = await load_allowed_users()
        if not user_allowed(user.id, user.username, rules):
            if isinstance(event, Message):
                await event.answer(MSG_NOT_EMPLOYEE)
            elif isinstance(event, CallbackQuery):
                await event.answer(MSG_NOT_EMPLOYEE, show_alert=True)
            return None

        return await handler(event, data)
