from __future__ import annotations

import logging
from typing import Any

from aiogram.types import Message

from bot.handlers.constants import CURRENT_FLOW_GROUP, FLOW_MENU_MAP
from bot.storage import default_session

logger = logging.getLogger(__name__)


def reset_session(session: dict[str, Any]) -> None:
    new = default_session()
    session.clear()
    session.update(new)


def flow_label(flow: str) -> str:
    return {
        "opening": "чек-лист открытия",
        "closing_photo": "чек-лист закрытия (фото)",
        "closing_text": "чек-лист закрытия (текст)",
        "line_photo": "лайн-чек",
        "line_rating": "лайн-чек (оценка)",
        "tech": "тех-карты",
        "invoices_product": "накладные",
        "invoices_supplier": "накладные",
        "invoices_date": "накладные",
        "invoices_photos": "накладные (фото)",
        "move_what": "перемещение",
        "move_why": "перемещение",
        "move_date": "перемещение",
        "move_from_to": "перемещение",
        "write_off_what": "списание",
        "write_off_why": "списание",
        "write_off_date": "списание",
        "write_off_photo": "списание (фото)",
    }.get(flow, flow)


def largest_photo_file_id(message: Message) -> str | None:
    if not message.photo:
        return None
    return message.photo[-1].file_id


def step_index(session: dict[str, Any], total: int) -> int:
    step = session.get("step", 0)
    if not isinstance(step, int) or step < 0 or step >= total:
        logger.warning("Некорректный шаг сценария: flow=%s step=%r total=%s", session.get("flow"), step, total)
        session["step"] = 0
        return 0
    return step


async def safe_answer(message: Message, text: str, **kwargs: Any) -> None:
    try:
        await message.answer(text, **kwargs)
    except Exception:
        logger.exception("Не удалось отправить ответ пользователю")


def requested_flow_from_menu(text: str) -> str | None:
    return FLOW_MENU_MAP.get(text.strip())


def current_flow_group(session: dict[str, Any]) -> str | None:
    return CURRENT_FLOW_GROUP.get(session.get("flow", "idle"), None)
