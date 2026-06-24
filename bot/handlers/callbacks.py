from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.content import LINE_PHOTO_ITEMS, LINE_RATING_QUESTION
from bot.handlers.helpers import reset_session
from bot.keyboards import main_menu_reply
from bot.report_delivery import deliver_report
from bot.reports import send_line_report
from bot.shift_reminders import record_line_completed

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("line_rate:"))
async def on_line_rate(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if session.get("flow") != "line_rating":
        await callback.answer("Сначала пройдите фото-пункты лайн-чека.", show_alert=True)
        return
    if not callback.data or not callback.message or not callback.from_user:
        await callback.answer()
        return
    try:
        value = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    session["line_rating"] = value
    from bot.content import RATING_LABELS

    label = RATING_LABELS.get(value, str(value))

    lp = list(session.get("line_photos") or [])
    u = callback.from_user

    async def run_report() -> None:
        await send_line_report(
            callback.bot,
            u,
            LINE_PHOTO_ITEMS,
            lp,
            LINE_RATING_QUESTION,
            value,
            label,
        )

    ok = await deliver_report(
        session=session,
        action="line",
        flow="line_rating",
        user_id=u.id,
        reply_to=callback.message,
        report=run_report,
        bad_request_detail=(
            "Не удалось отправить отчёт в группу. Проверьте бота в группе и ID (с минусом для супергруппы)."
        ),
    )
    if not ok:
        await callback.answer()
        return
    await record_line_completed()
    logger.info("flow_done flow=line user_id=%s", u.id)
    await callback.message.answer(
        "Лайн-чек отправлен в группу администратора. Спасибо! 🙌",
        reply_markup=main_menu_reply(),
    )
    reset_session(session)
    await callback.answer()
