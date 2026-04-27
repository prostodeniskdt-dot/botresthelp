from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.middlewares._event import user_from_event
from bot.storage import default_session, load_sessions, save_sessions, session_lock


def _normalize_session(session: dict[str, Any]) -> dict[str, Any]:
    normalized = default_session()
    normalized.update(session)
    if not isinstance(normalized.get("step"), int) or normalized["step"] < 0:
        normalized["step"] = 0
    return normalized


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
            data["session"] = default_session()
            return await handler(event, data)

        key = str(user_id)
        async with session_lock(key):
            sessions = await load_sessions()
            if key not in sessions:
                sessions[key] = default_session()
            else:
                sessions[key] = _normalize_session(sessions[key])
            session = sessions[key]
            data["session"] = session
            data["_sessions_dict"] = sessions
            data["_session_key"] = key

            try:
                return await handler(event, data)
            finally:
                await save_sessions(sessions)
