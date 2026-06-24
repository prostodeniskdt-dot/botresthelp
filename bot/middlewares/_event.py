"""В dp.update.middleware() в aiogram 3 передаётся Update, а не Message."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User


def user_from_event(event: TelegramObject) -> User | None:
    if isinstance(event, Update):
        if event.message:
            return event.message.from_user
        if event.edited_message:
            return event.edited_message.from_user
        if event.callback_query:
            return event.callback_query.from_user
        return None
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return None
