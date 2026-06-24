from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.content import BTN_BACK, MSG_MAIN_MENU_HINT
from bot.handlers.back_flow import apply_back
from bot.handlers.helpers import (
    current_flow_group,
    flow_label,
    requested_flow_from_menu,
    reset_session,
)
from bot.handlers.ttk import send_ttk_home
from bot.handlers.prompts import (
    send_closing_photo_prompt,
    send_closing_text_prompt,
    send_invoices_prompt,
    send_line_photo_prompt,
    send_line_rating,
    send_move_prompt,
    send_opening_prompt,
    send_resume_notice,
    send_write_off_prompt,
)
from bot.keyboards import confirm_switch_inline, main_menu_reply
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: dict[str, Any]) -> None:
    await message.answer(
        f"Привет! {MSG_MAIN_MENU_HINT}",
        reply_markup=main_menu_reply(),
    )
    await send_resume_notice(message, session)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: dict[str, Any]) -> None:
    await message.answer(MSG_MAIN_MENU_HINT, reply_markup=main_menu_reply())
    await send_resume_notice(message, session)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, session: dict[str, Any]) -> None:
    reset_session(session)
    await message.answer(
        "Сценарий отменён ✅ Вернитесь в меню или начните заново 👇",
        reply_markup=main_menu_reply(),
    )


@router.message(Command("back"))
async def cmd_back(message: Message, session: dict[str, Any]) -> None:
    await apply_back(message, session)


async def begin_opening(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "opening"
    session["step"] = 0
    session["opening"] = []
    session["opening_item_photos"] = []
    session["pending_switch"] = None
    await send_opening_prompt(message, session)


async def begin_closing(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "closing_photo"
    session["step"] = 0
    session["closing_photos"] = []
    session["closing_texts"] = []
    session["pending_switch"] = None
    await send_closing_photo_prompt(message, session)


async def begin_line(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "line_photo"
    session["step"] = 0
    session["line_photos"] = []
    session["line_rating"] = None
    session["pending_switch"] = None
    await send_line_photo_prompt(message, session)


async def begin_ttk(message: Message, session: dict[str, Any]) -> None:
    session["pending_switch"] = None
    session.pop("ttk_back", None)
    session.pop("ttk_search_results", None)
    await send_ttk_home(message)


async def begin_invoices(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "invoices_product"
    session["step"] = 0
    session["invoices"] = {}
    session["invoice_photos"] = []
    session["pending_switch"] = None
    await send_invoices_prompt(message, session)


async def begin_move(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "move_what"
    session["step"] = 0
    session["move"] = {}
    session["pending_switch"] = None
    await send_move_prompt(message, session)


async def begin_write_off(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "write_off_what"
    session["step"] = 0
    session["write_off"] = {}
    session["write_off_photo"] = None
    session["pending_switch"] = None
    await send_write_off_prompt(message, session)


async def handle_menu_press(message: Message, session: dict[str, Any], text: str) -> bool:
    req = requested_flow_from_menu(text)
    if not req:
        return False

    cur = current_flow_group(session)
    if session.get("flow") == "idle" or cur is None:
        if req == "opening":
            await begin_opening(message, session)
        elif req == "closing":
            await begin_closing(message, session)
        elif req == "line":
            await begin_line(message, session)
        elif req == "ttk":
            await begin_ttk(message, session)
        elif req == "invoices":
            await begin_invoices(message, session)
        elif req == "move":
            await begin_move(message, session)
        elif req == "write_off":
            await begin_write_off(message, session)
        return True

    if cur == req:
        if req == "opening":
            await send_opening_prompt(message, session)
        elif req == "closing":
            if session["flow"] == "closing_photo":
                await send_closing_photo_prompt(message, session)
            else:
                await send_closing_text_prompt(message, session)
        elif req == "line":
            if session["flow"] == "line_photo":
                await send_line_photo_prompt(message, session)
            else:
                await send_line_rating(message, session)
        elif req == "ttk":
            await begin_ttk(message, session)
        elif req == "invoices":
            await send_invoices_prompt(message, session)
        elif req == "move":
            await send_move_prompt(message, session)
        elif req == "write_off":
            await send_write_off_prompt(message, session)
        return True

    session["pending_switch"] = req
    await message.answer(
        f"У вас незавершён {flow_label(session['flow'])}. Переключиться на другой раздел?",
        reply_markup=confirm_switch_inline(req),
    )
    return True


@router.callback_query(F.data.startswith("switch_yes:"))
async def on_switch_yes(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    action = callback.data.split(":", 1)[1]
    session["pending_switch"] = None
    reset_session(session)
    if action == "opening":
        await begin_opening(callback.message, session)
    elif action == "closing":
        await begin_closing(callback.message, session)
    elif action == "line":
        await begin_line(callback.message, session)
    elif action == "ttk":
        await begin_ttk(callback.message, session)
    elif action == "invoices":
        await begin_invoices(callback.message, session)
    elif action == "move":
        await begin_move(callback.message, session)
    elif action == "write_off":
        await begin_write_off(callback.message, session)
    await callback.answer()


@router.callback_query(F.data == "switch_no")
async def on_switch_no(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session["pending_switch"] = None
    if callback.message:
        await callback.message.answer("Продолжаем текущий сценарий.")
    await callback.answer()


@router.message(F.text == BTN_BACK)
async def on_back_button(message: Message, session: dict[str, Any]) -> None:
    await apply_back(message, session)
