from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import Message

from bot.config import TECH_PAGE_SIZE
from bot.content import (
    CLOSING_PHOTO_ITEMS,
    CLOSING_TEXT_PROMPTS,
)
from bot.handlers.constants import MENU_BUTTONS
from bot.handlers.menu import handle_menu_press
from bot.handlers.prompts import (
    send_closing_text_prompt,
    send_invoices_prompt,
    send_line_rating,
    send_move_prompt,
    send_write_off_prompt,
)
from bot.keyboards import main_menu_reply, tech_pick_page_inline
from bot.recipe_struct import recipe_to_html
from bot.report_delivery import deliver_report
from bot.reports import send_closing_report, send_move_report
from bot.storage import load_recipes
from bot.recipes_search import search_recipes
from bot.handlers.helpers import reset_session

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text)
async def on_text(message: Message, session: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    if text in MENU_BUTTONS:
        await handle_menu_press(message, session, text)
        return

    flow = session.get("flow")

    if flow == "closing_text":
        if not message.from_user:
            return
        answers = session.setdefault("closing_texts", [])
        answers.append(text)
        if len(answers) < len(CLOSING_TEXT_PROMPTS):
            session["step"] = len(answers)
            await send_closing_text_prompt(message, session)
        else:
            u = message.from_user
            photos = list(session.get("closing_photos") or [])

            async def run_close() -> None:
                await send_closing_report(
                    message.bot,
                    u,
                    CLOSING_PHOTO_ITEMS,
                    photos,
                    CLOSING_TEXT_PROMPTS,
                    answers,
                )

            ok = await deliver_report(
                session=session,
                action="closing",
                flow="closing_text",
                user_id=u.id,
                reply_to=message,
                report=run_close,
                bad_request_detail=(
                    "Не удалось отправить отчёт в группу. Проверьте бота в группе и ID (с минусом)."
                ),
            )
            if not ok:
                return
            logger.info("flow_done flow=closing user_id=%s", u.id)
            await message.answer(
                "Отчёт по закрытию отправлен в группу администратора. Спасибо! 🌙",
                reply_markup=main_menu_reply(),
            )
            reset_session(session)
        return

    if flow == "invoices_product":
        session.setdefault("invoices", {})["product"] = text
        session["flow"] = "invoices_supplier"
        await send_invoices_prompt(message, session)
        return

    if flow == "invoices_supplier":
        session.setdefault("invoices", {})["supplier"] = text
        session["flow"] = "invoices_date"
        await send_invoices_prompt(message, session)
        return

    if flow == "invoices_date":
        session.setdefault("invoices", {})["date"] = text
        session["flow"] = "invoices_photos"
        session["invoice_photos"] = []
        await send_invoices_prompt(message, session)
        return

    if flow == "invoices_photos":
        await message.answer("Нужно отправить фото. Два фото: наименование и печать/подпись 📸")
        return

    if flow == "move_what":
        session.setdefault("move", {})["what"] = text
        session["flow"] = "move_why"
        await send_move_prompt(message, session)
        return

    if flow == "move_why":
        session.setdefault("move", {})["why"] = text
        session["flow"] = "move_date"
        await send_move_prompt(message, session)
        return

    if flow == "move_date":
        session.setdefault("move", {})["date"] = text
        session["flow"] = "move_from_to"
        await send_move_prompt(message, session)
        return

    if flow == "move_from_to":
        session.setdefault("move", {})["from_to"] = text
        if not message.from_user:
            return
        mv = session.get("move") or {}
        u = message.from_user

        async def run_move() -> None:
            await send_move_report(
                message.bot,
                u,
                str(mv.get("what", "")),
                str(mv.get("why", "")),
                str(mv.get("date", "")),
                str(mv.get("from_to", "")),
            )

        ok = await deliver_report(
            session=session,
            action="move",
            flow="move_from_to",
            user_id=u.id,
            reply_to=message,
            report=run_move,
        )
        if not ok:
            return
        logger.info("flow_done flow=move user_id=%s", u.id)
        await message.answer("Спасибо, переместили 📦", reply_markup=main_menu_reply())
        reset_session(session)
        return

    if flow == "write_off_what":
        session.setdefault("write_off", {})["what"] = text
        session["flow"] = "write_off_why"
        await send_write_off_prompt(message, session)
        return

    if flow == "write_off_why":
        session.setdefault("write_off", {})["why"] = text
        session["flow"] = "write_off_date"
        await send_write_off_prompt(message, session)
        return

    if flow == "write_off_date":
        session.setdefault("write_off", {})["date"] = text
        session["flow"] = "write_off_photo"
        await send_write_off_prompt(message, session)
        return

    if flow == "write_off_photo":
        await message.answer("Нужно отправить фото чека списания 📸")
        return

    if flow == "tech":
        recipes = await load_recipes()
        matches = search_recipes(recipes, text)
        session["tech_matches"] = matches
        session["tech_last_query"] = text
        session["tech_pick_offset"] = 0
        if not matches:
            await message.answer("Ничего не найдено. Попробуйте другое название или слова 🔍")
            return
        if len(matches) == 1:
            r = matches[0]
            name = str(r.get("name", ""))
            body = recipe_to_html(r)
            await message.answer(
                f"<b>{html.escape(name)}</b>\n\n{body}",
                parse_mode="HTML",
                reply_markup=main_menu_reply(),
            )
            return
        await message.answer(
            "Несколько совпадений — выберите кнопкой (есть листание страниц 👇)",
            reply_markup=tech_pick_page_inline(matches=matches, offset=0, page_size=TECH_PAGE_SIZE),
        )
        return

    if flow == "line_rating":
        await message.answer("Сейчас нужно нажать оценку кнопками под предыдущим сообщением ⭐")
        return

    await message.answer(
        "Выберите действие кнопками меню 👇 Командочки: /menu, /cancel",
        reply_markup=main_menu_reply(),
    )
