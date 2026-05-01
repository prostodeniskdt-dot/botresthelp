from __future__ import annotations

from typing import Any

from aiogram.types import Message

from bot.content import (
    CLOSING_PHOTO_ITEMS,
    CLOSING_TEXT_PROMPTS,
    LINE_PHOTO_ITEMS,
    LINE_RATING_QUESTION,
    MSG_NEED_PHOTO,
    OPENING_ITEMS,
)
from bot.handlers.helpers import flow_label, step_index
from bot.keyboards import line_rating_inline, main_menu_reply


async def send_opening_prompt(message: Message, session: dict[str, Any]) -> None:
    i = step_index(session, len(OPENING_ITEMS))
    text = OPENING_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(OPENING_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def send_closing_photo_prompt(message: Message, session: dict[str, Any]) -> None:
    i = step_index(session, len(CLOSING_PHOTO_ITEMS))
    text = CLOSING_PHOTO_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(CLOSING_PHOTO_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def send_closing_text_prompt(message: Message, session: dict[str, Any]) -> None:
    i = step_index(session, len(CLOSING_TEXT_PROMPTS))
    prompt = CLOSING_TEXT_PROMPTS[i]
    await message.answer(
        f"Текстовый вопрос {i + 1}/{len(CLOSING_TEXT_PROMPTS)}\n\n<b>{prompt}</b>\n\nОтветьте одним сообщением.",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def send_line_photo_prompt(message: Message, session: dict[str, Any]) -> None:
    i = step_index(session, len(LINE_PHOTO_ITEMS))
    text = LINE_PHOTO_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(LINE_PHOTO_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def send_line_rating(message: Message, session: dict[str, Any]) -> None:
    await message.answer(
        f"<b>{LINE_RATING_QUESTION}</b>\n\nВыберите оценку кнопками:",
        reply_markup=line_rating_inline(),
        parse_mode="HTML",
    )


async def send_tech_prompt(message: Message) -> None:
    await message.answer(
        "Напишите название коктейля или ключевые слова. Например: <code>Мохито</code> или <code>ром мох</code>.",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def send_invoices_prompt(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow")
    if flow == "invoices_product":
        await message.answer(
            "Так, так — что у нас приехало? 📦",
            reply_markup=main_menu_reply(),
        )
    elif flow == "invoices_supplier":
        await message.answer("От какого поставщика? 🚚", reply_markup=main_menu_reply())
    elif flow == "invoices_date":
        await message.answer("А какое сегодня число? 📅", reply_markup=main_menu_reply())
    elif flow == "invoices_photos":
        got = len(session.get("invoice_photos") or [])
        await message.answer(
            "Отправь мне две фото накладных. Фото с наименованием, и фото с печатью и подписью 📎"
            + (f"\n\nПринято фото: {got}/2" if got else ""),
            reply_markup=main_menu_reply(),
        )


async def send_move_prompt(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow")
    if flow == "move_what":
        await message.answer("Так, так — что хочешь переместить? 📦", reply_markup=main_menu_reply())
    elif flow == "move_why":
        await message.answer("Зачем? 🤔", reply_markup=main_menu_reply())
    elif flow == "move_date":
        await message.answer("А какое сегодня число? 📅", reply_markup=main_menu_reply())
    elif flow == "move_from_to":
        await message.answer("Откуда и куда ↕️", reply_markup=main_menu_reply())


async def send_write_off_prompt(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow")
    if flow == "write_off_what":
        await message.answer("Так, так — что хочешь списать? 📋", reply_markup=main_menu_reply())
    elif flow == "write_off_why":
        await message.answer("Зачем? 🤔", reply_markup=main_menu_reply())
    elif flow == "write_off_date":
        await message.answer("А какое сегодня число? 📅", reply_markup=main_menu_reply())
    elif flow == "write_off_photo":
        await message.answer(
            "Отправь фото чека списания 📸",
            reply_markup=main_menu_reply(),
        )


async def send_resume_notice(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow", "idle")
    if flow == "idle":
        return
    await message.answer(
        f"У вас незавершён: <b>{flow_label(flow)}</b>. Продолжаем с текущего шага.",
        parse_mode="HTML",
    )
    if flow == "opening":
        await send_opening_prompt(message, session)
    elif flow == "closing_photo":
        await send_closing_photo_prompt(message, session)
    elif flow == "closing_text":
        await send_closing_text_prompt(message, session)
    elif flow == "line_photo":
        await send_line_photo_prompt(message, session)
    elif flow == "line_rating":
        await send_line_rating(message, session)
    elif flow == "tech":
        await send_tech_prompt(message)
    elif isinstance(flow, str) and flow.startswith("invoices_"):
        await send_invoices_prompt(message, session)
    elif isinstance(flow, str) and flow.startswith("move_"):
        await send_move_prompt(message, session)
    elif isinstance(flow, str) and flow.startswith("write_off_"):
        await send_write_off_prompt(message, session)
