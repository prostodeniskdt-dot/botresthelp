from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import Message

from bot.content import CLOSING_PHOTO_ITEMS, LINE_PHOTO_ITEMS, OPENING_ITEMS
from bot.handlers.helpers import largest_photo_file_id
from bot.handlers.prompts import (
    send_closing_photo_prompt,
    send_closing_text_prompt,
    send_invoices_prompt,
    send_line_photo_prompt,
    send_line_rating,
    send_opening_prompt,
)
from bot.keyboards import main_menu_reply
from bot.report_delivery import deliver_report
from bot.reports import (
    send_invoices_report,
    send_opening_report,
    send_write_off_report,
)
from bot.shift_reminders import record_opening_completed
from bot.handlers.helpers import reset_session

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.photo)
async def on_photo(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow")
    fid = largest_photo_file_id(message)
    if not fid:
        return

    if flow == "opening":
        i = session["step"]
        session["opening"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(OPENING_ITEMS):
            await send_opening_prompt(message, session)
        else:
            if not message.from_user:
                return
            u_local = message.from_user
            opening_local = list(session["opening"])
            ok = await deliver_report(
                session=session,
                action="opening",
                flow="opening",
                user_id=u_local.id,
                reply_to=message,
                report=lambda: send_opening_report(message.bot, u_local, OPENING_ITEMS, opening_local),
                bad_request_detail=(
                    "Не удалось отправить отчёт в группу. Убедитесь, что бот добавлен в группу и может писать. "
                    "ID группы в переменных должен быть с минусом (например -1003927366109)."
                ),
            )
            if not ok:
                return
            await record_opening_completed(message.from_user.id, message.from_user.username)
            logger.info(
                "flow_done flow=opening user_id=%s",
                message.from_user.id,
            )
            await message.answer(
                "Отчёт по открытию отправлен в группу администратора. Спасибо! 🎉",
                reply_markup=main_menu_reply(),
            )
            reset_session(session)
        return

    if flow == "closing_photo":
        i = session["step"]
        session["closing_photos"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(CLOSING_PHOTO_ITEMS):
            await send_closing_photo_prompt(message, session)
        else:
            session["flow"] = "closing_text"
            session["step"] = 0
            await send_closing_text_prompt(message, session)
        return

    if flow == "line_photo":
        i = session["step"]
        session["line_photos"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(LINE_PHOTO_ITEMS):
            await send_line_photo_prompt(message, session)
        else:
            session["flow"] = "line_rating"
            await send_line_rating(message, session)
        return

    if flow == "invoices_photos":
        photos = session.setdefault("invoice_photos", [])
        photos.append(fid)
        if len(photos) < 2:
            await message.answer(
                "Фото принято. Нужно ещё одно фото ✅",
                reply_markup=main_menu_reply(),
            )
            await send_invoices_prompt(message, session)
            return
        if not message.from_user:
            return
        inv = session.get("invoices") or {}

        ok = await deliver_report(
            session=session,
            action="invoices",
            flow="invoices_photos",
            user_id=message.from_user.id,
            reply_to=message,
            report=lambda u=message.from_user, p=photos[:2], i2=inv: send_invoices_report(
                message.bot,
                u,
                str(i2.get("product", "")),
                str(i2.get("supplier", "")),
                str(i2.get("date", "")),
                p,
            ),
        )
        if not ok:
            return
        logger.info("flow_done flow=invoices user_id=%s", message.from_user.id)
        await message.answer(
            "Спасибо, ваша накладная отправлена 💚",
            reply_markup=main_menu_reply(),
        )
        reset_session(session)
        return

    if flow == "write_off_photo":
        session["write_off_photo"] = fid
        if not message.from_user:
            return
        wo = session.get("write_off") or {}
        ok = await deliver_report(
            session=session,
            action="write_off",
            flow="write_off_photo",
            user_id=message.from_user.id,
            reply_to=message,
            report=lambda u=message.from_user: send_write_off_report(
                message.bot,
                u,
                str(wo.get("what", "")),
                str(wo.get("why", "")),
                str(wo.get("date", "")),
                fid,
            ),
        )
        if not ok:
            return
        logger.info("flow_done flow=write_off user_id=%s", message.from_user.id)
        await message.answer("Спасибо, списали ✅", reply_markup=main_menu_reply())
        reset_session(session)
        return

    await message.answer("Сейчас фото не ожидается. Выберите действие в меню 📋")
