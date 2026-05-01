from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.content import LINE_PHOTO_ITEMS, LINE_RATING_QUESTION
from bot.handlers.helpers import reset_session
from bot.keyboards import main_menu_reply, tech_pick_page_inline
from bot.recipe_struct import recipe_to_html
from bot.report_delivery import deliver_report
from bot.reports import send_line_report
from bot.shift_reminders import record_line_completed
from bot.config import TECH_PAGE_SIZE

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


@router.callback_query(F.data.startswith("tech_nav:"))
async def on_tech_nav(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if session.get("flow") != "tech":
        await callback.answer()
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        offset = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer()
        return
    matches = session.get("tech_matches") or []
    n = len(matches)
    if n == 0:
        await callback.answer("Сначала введите запрос.", show_alert=True)
        return
    offset = max(0, min(offset, max(0, n - 1)))
    session["tech_pick_offset"] = offset
    await callback.message.edit_reply_markup(
        reply_markup=tech_pick_page_inline(matches=matches, offset=offset, page_size=TECH_PAGE_SIZE),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tech_pick:"))
async def on_tech_pick(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if session.get("flow") != "tech":
        await callback.answer()
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Устаревший выбор, введите запрос снова.", show_alert=True)
        return
    matches = session.get("tech_matches") or []
    if idx < 0 or idx >= len(matches):
        await callback.answer("Устаревший выбор, введите запрос снова.", show_alert=True)
        return
    chosen = matches[idx]
    name = str(chosen.get("name", ""))
    body = recipe_to_html(chosen)
    await callback.message.answer(
        f"<b>{html.escape(name)}</b>\n\n{body}",
        parse_mode="HTML",
        reply_markup=main_menu_reply(),
    )
    session["tech_matches"] = []
    session["tech_pick_offset"] = 0
    await callback.answer()
