from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from bot.storage import default_session

logger = logging.getLogger(__name__)


async def deliver_report(
    *,
    session: dict[str, Any],
    action: str,
    flow: str,
    user_id: int,
    reply_to: Message,
    report: Callable[[], Awaitable[Any]],
    bad_request_detail: str | None = None,
) -> bool:
    detail = bad_request_detail or (
        "Не удалось отправить отчёт в группу. Проверьте, что бот добавлен в группу и может писать."
    )
    try:
        await report()
        logger.info("report_ok action=%s user_id=%s flow=%s", action, user_id, flow)
        return True
    except TelegramBadRequest as e:
        logger.exception("report_fail action=%s user_id=%s flow=%s err=TelegramBadRequest", action, user_id, flow)
        session.clear()
        session.update(default_session())
        try:
            await reply_to.answer(f"{detail}\nОшибка API: {e}")
        except Exception:
            logger.exception("deliver_report reply failed")
        return False
    except Exception as e:
        logger.exception("report_fail action=%s user_id=%s flow=%s", action, user_id, flow)
        session.clear()
        session.update(default_session())
        try:
            await reply_to.answer(f"Ошибка при отправке отчёта: {type(e).__name__}: {e}")
        except Exception:
            logger.exception("deliver_report reply failed")
        return False
