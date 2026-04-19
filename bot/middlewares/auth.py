from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from bot.content import MSG_NOT_EMPLOYEE
from bot.middlewares._event import user_from_event
from bot.storage import load_allowed_users, user_allowed


async def _send_not_employee(event: TelegramObject) -> None:
    if isinstance(event, Update):
        if event.message:
            await event.message.answer(MSG_NOT_EMPLOYEE)
        elif event.callback_query:
            await event.callback_query.answer(MSG_NOT_EMPLOYEE, show_alert=True)
    elif isinstance(event, Message):
        await event.answer(MSG_NOT_EMPLOYEE)
    elif isinstance(event, CallbackQuery):
        await event.callback_query.answer(MSG_NOT_EMPLOYEE, show_alert=True)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = user_from_event(event)

        if user is None:
            return await handler(event, data)

        rules = await load_allowed_users()
        if not user_allowed(user.id, user.username, rules):
            await _send_not_employee(event)
            return None

        return await handler(event, data)
