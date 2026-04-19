from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.middlewares._event import user_from_event
from bot.storage import default_session, load_sessions, save_sessions


class SessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = user_from_event(event)
        user_id = user.id if user else None

        if user_id is None:
            return await handler(event, data)

        sessions = await load_sessions()
        key = str(user_id)
        if key not in sessions:
            sessions[key] = default_session()
        session = sessions[key]
        data["session"] = session
        data["_sessions_dict"] = sessions
        data["_session_key"] = key

        try:
            return await handler(event, data)
        finally:
            await save_sessions(sessions)
