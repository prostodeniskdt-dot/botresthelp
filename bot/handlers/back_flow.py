from __future__ import annotations

from typing import Any

from aiogram.types import Message

from bot.handlers.prompts import (
    send_closing_photo_prompt,
    send_closing_text_prompt,
    send_invoices_prompt,
    send_line_photo_prompt,
    send_move_prompt,
    send_opening_prompt,
    send_write_off_prompt,
)


async def apply_back(message: Message, session: dict[str, Any]) -> bool:
    flow = session.get("flow", "idle")
    if flow == "idle":
        await message.answer("Сейчас нечего откатывать — вы в главном меню.")
        return True

    if flow == "opening":
        if session.get("step", 0) <= 0 or not session.get("opening"):
            await message.answer("Вы на первом пункте открытия — дальше только /cancel.")
            return True
        session["opening"].pop()
        session["step"] = max(0, int(session.get("step", 0)) - 1)
        await send_opening_prompt(message, session)
        return True

    if flow == "closing_photo":
        if session.get("step", 0) <= 0 or not session.get("closing_photos"):
            await message.answer("Вы на первом фото-пункте закрытия.")
            return True
        session["closing_photos"].pop()
        session["step"] = max(0, int(session.get("step", 0)) - 1)
        await send_closing_photo_prompt(message, session)
        return True

    if flow == "closing_text":
        answers = session.setdefault("closing_texts", [])
        if answers:
            answers.pop()
            session["step"] = len(answers)
            await send_closing_text_prompt(message, session)
            return True
        photos = session.get("closing_photos") or []
        if photos:
            session["flow"] = "closing_photo"
            photos.pop()
            session["closing_photos"] = photos
            session["step"] = len(photos)
            await send_closing_photo_prompt(message, session)
            return True
        await message.answer("Не могу откатить текст — нет сохранённых ответов.")
        return True

    if flow == "line_photo":
        if session.get("step", 0) <= 0 or not session.get("line_photos"):
            await message.answer("Вы на первом пункте лайн-чека.")
            return True
        session["line_photos"].pop()
        session["step"] = max(0, int(session.get("step", 0)) - 1)
        await send_line_photo_prompt(message, session)
        return True

    if flow == "line_rating":
        session["flow"] = "line_photo"
        session["line_rating"] = None
        lp = session.setdefault("line_photos", [])
        if lp:
            lp.pop()
        session["step"] = len(lp)
        await send_line_photo_prompt(message, session)
        return True

    if flow == "invoices_supplier":
        session["flow"] = "invoices_product"
        await send_invoices_prompt(message, session)
        return True
    if flow == "invoices_date":
        session["flow"] = "invoices_supplier"
        await send_invoices_prompt(message, session)
        return True
    if flow == "invoices_photos":
        session["flow"] = "invoices_date"
        session["invoice_photos"] = []
        await send_invoices_prompt(message, session)
        return True

    if flow == "move_why":
        session["flow"] = "move_what"
        await send_move_prompt(message, session)
        return True
    if flow == "move_date":
        session["flow"] = "move_why"
        await send_move_prompt(message, session)
        return True
    if flow == "move_from_to":
        session["flow"] = "move_date"
        await send_move_prompt(message, session)
        return True

    if flow == "write_off_why":
        session["flow"] = "write_off_what"
        await send_write_off_prompt(message, session)
        return True
    if flow == "write_off_date":
        session["flow"] = "write_off_why"
        await send_write_off_prompt(message, session)
        return True
    if flow == "write_off_photo":
        session["flow"] = "write_off_date"
        session["write_off_photo"] = None
        await send_write_off_prompt(message, session)
        return True

    if flow == "tech":
        session["tech_matches"] = []
        session["tech_pick_offset"] = 0
        await message.answer("Поиск сброшен. Введите новый запрос по техкартам.")
        return True

    await message.answer("Назад для этого шага пока не настроен — используйте /cancel.")
    return True
