from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.content import (
    BTN_CLOSING,
    BTN_LINE,
    BTN_OPENING,
    BTN_TECH,
    CLOSING_PHOTO_ITEMS,
    CLOSING_TEXT_PROMPTS,
    LINE_PHOTO_ITEMS,
    LINE_RATING_QUESTION,
    MSG_MAIN_MENU_HINT,
    MSG_NEED_PHOTO,
    OPENING_ITEMS,
    RATING_LABELS,
)
from bot.keyboards import (
    confirm_switch_inline,
    line_rating_inline,
    main_menu_reply,
    tech_pick_inline,
)
from bot.recipes_search import search_recipes
from bot.reports import send_closing_report, send_line_report, send_opening_report
from bot.storage import default_session, load_recipes

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = {BTN_OPENING, BTN_CLOSING, BTN_LINE, BTN_TECH}

FLOW_MENU_MAP: dict[str, str] = {
    BTN_OPENING: "opening",
    BTN_CLOSING: "closing",
    BTN_LINE: "line",
    BTN_TECH: "tech",
}

CURRENT_FLOW_GROUP: dict[str, str | None] = {
    "idle": None,
    "opening": "opening",
    "closing_photo": "closing",
    "closing_text": "closing",
    "line_photo": "line",
    "line_rating": "line",
    "tech": "tech",
}


def _reset_session(session: dict[str, Any]) -> None:
    new = default_session()
    session.clear()
    session.update(new)


def _flow_label(flow: str) -> str:
    return {
        "opening": "чек-лист открытия",
        "closing_photo": "чек-лист закрытия (фото)",
        "closing_text": "чек-лист закрытия (текст)",
        "line_photo": "лайн-чек",
        "line_rating": "лайн-чек (оценка)",
        "tech": "тех-карты",
    }.get(flow, flow)


def _largest_photo_file_id(message: Message) -> str | None:
    if not message.photo:
        return None
    return message.photo[-1].file_id


async def _send_opening_prompt(message: Message, session: dict[str, Any]) -> None:
    i = session["step"]
    text = OPENING_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(OPENING_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def _send_closing_photo_prompt(message: Message, session: dict[str, Any]) -> None:
    i = session["step"]
    text = CLOSING_PHOTO_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(CLOSING_PHOTO_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def _send_closing_text_prompt(message: Message, session: dict[str, Any]) -> None:
    i = session["step"]
    prompt = CLOSING_TEXT_PROMPTS[i]
    await message.answer(
        f"Текстовый вопрос {i + 1}/{len(CLOSING_TEXT_PROMPTS)}\n\n<b>{prompt}</b>\n\nОтветьте одним сообщением.",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def _send_line_photo_prompt(message: Message, session: dict[str, Any]) -> None:
    i = session["step"]
    text = LINE_PHOTO_ITEMS[i]
    await message.answer(
        f"Пункт {i + 1}/{len(LINE_PHOTO_ITEMS)}\n\n<b>{text}</b>\n\n{MSG_NEED_PHOTO}",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def _send_line_rating(message: Message, session: dict[str, Any]) -> None:
    await message.answer(
        f"<b>{LINE_RATING_QUESTION}</b>\n\nВыберите оценку кнопками:",
        reply_markup=line_rating_inline(),
        parse_mode="HTML",
    )


async def _send_tech_prompt(message: Message) -> None:
    await message.answer(
        "Напишите название коктейля или ключевые слова. Например: <code>Мохито</code> или <code>ром мох</code>.",
        reply_markup=main_menu_reply(),
        parse_mode="HTML",
    )


async def _send_resume_notice(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow", "idle")
    if flow == "idle":
        return
    await message.answer(
        f"У вас незавершён: <b>{_flow_label(flow)}</b>. Продолжаем с текущего шага.",
        parse_mode="HTML",
    )
    if flow == "opening":
        await _send_opening_prompt(message, session)
    elif flow == "closing_photo":
        await _send_closing_photo_prompt(message, session)
    elif flow == "closing_text":
        await _send_closing_text_prompt(message, session)
    elif flow == "line_photo":
        await _send_line_photo_prompt(message, session)
    elif flow == "line_rating":
        await _send_line_rating(message, session)
    elif flow == "tech":
        await _send_tech_prompt(message)


@router.message(CommandStart())
async def cmd_start(message: Message, session: dict[str, Any]) -> None:
    await message.answer(
        f"Привет! {MSG_MAIN_MENU_HINT}",
        reply_markup=main_menu_reply(),
    )
    await _send_resume_notice(message, session)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: dict[str, Any]) -> None:
    await message.answer(MSG_MAIN_MENU_HINT, reply_markup=main_menu_reply())
    await _send_resume_notice(message, session)


async def _begin_opening(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "opening"
    session["step"] = 0
    session["opening"] = []
    session["pending_switch"] = None
    await _send_opening_prompt(message, session)


async def _begin_closing(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "closing_photo"
    session["step"] = 0
    session["closing_photos"] = []
    session["closing_texts"] = []
    session["pending_switch"] = None
    await _send_closing_photo_prompt(message, session)


async def _begin_line(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "line_photo"
    session["step"] = 0
    session["line_photos"] = []
    session["line_rating"] = None
    session["pending_switch"] = None
    await _send_line_photo_prompt(message, session)


async def _begin_tech(message: Message, session: dict[str, Any]) -> None:
    session["flow"] = "tech"
    session["step"] = 0
    session["pending_switch"] = None
    await _send_tech_prompt(message)


def _requested_flow_from_menu(text: str) -> str | None:
    return FLOW_MENU_MAP.get(text.strip())


def _current_flow_group(session: dict[str, Any]) -> str | None:
    return CURRENT_FLOW_GROUP.get(session.get("flow", "idle"), None)


async def _handle_menu_press(message: Message, session: dict[str, Any], text: str) -> bool:
    req = _requested_flow_from_menu(text)
    if not req:
        return False

    cur = _current_flow_group(session)
    if session.get("flow") == "idle" or cur is None:
        if req == "opening":
            await _begin_opening(message, session)
        elif req == "closing":
            await _begin_closing(message, session)
        elif req == "line":
            await _begin_line(message, session)
        elif req == "tech":
            await _begin_tech(message, session)
        return True

    if cur == req:
        if req == "opening":
            await _send_opening_prompt(message, session)
        elif req == "closing":
            if session["flow"] == "closing_photo":
                await _send_closing_photo_prompt(message, session)
            else:
                await _send_closing_text_prompt(message, session)
        elif req == "line":
            if session["flow"] == "line_photo":
                await _send_line_photo_prompt(message, session)
            else:
                await _send_line_rating(message, session)
        elif req == "tech":
            await _send_tech_prompt(message)
        return True

    session["pending_switch"] = req
    await message.answer(
        f"У вас незавершён {_flow_label(session['flow'])}. Переключиться на другой раздел?",
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
    _reset_session(session)
    if action == "opening":
        await _begin_opening(callback.message, session)
    elif action == "closing":
        await _begin_closing(callback.message, session)
    elif action == "line":
        await _begin_line(callback.message, session)
    elif action == "tech":
        await _begin_tech(callback.message, session)
    await callback.answer()


@router.callback_query(F.data == "switch_no")
async def on_switch_no(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session["pending_switch"] = None
    if callback.message:
        await callback.message.answer("Продолжаем текущий сценарий.")
    await callback.answer()


@router.message(F.photo)
async def on_photo(message: Message, session: dict[str, Any]) -> None:
    flow = session.get("flow")
    fid = _largest_photo_file_id(message)
    if not fid:
        return

    if flow == "opening":
        i = session["step"]
        session["opening"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(OPENING_ITEMS):
            await _send_opening_prompt(message, session)
        else:
            if not message.from_user:
                return
            try:
                await send_opening_report(message.bot, message.from_user, OPENING_ITEMS, session["opening"])
            except TelegramBadRequest as e:
                logger.exception("send_opening_report failed")
                await message.answer(
                    "Не удалось отправить отчёт в группу. Убедитесь, что бот добавлен в группу и может писать. "
                    "ID группы в переменных должен быть с минусом (например -1003927366109). "
                    f"Ошибка API: {e}"
                )
                _reset_session(session)
                return
            except Exception as e:
                logger.exception("send_opening_report failed")
                await message.answer(f"Ошибка при отправке отчёта: {type(e).__name__}: {e}")
                _reset_session(session)
                return
            await message.answer("Отчёт по открытию отправлен в группу администратора. Спасибо!")
            _reset_session(session)
        return

    if flow == "closing_photo":
        i = session["step"]
        session["closing_photos"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(CLOSING_PHOTO_ITEMS):
            await _send_closing_photo_prompt(message, session)
        else:
            session["flow"] = "closing_text"
            session["step"] = 0
            await _send_closing_text_prompt(message, session)
        return

    if flow == "line_photo":
        i = session["step"]
        session["line_photos"].append({"file_id": fid, "caption": message.caption or ""})
        session["step"] = i + 1
        if session["step"] < len(LINE_PHOTO_ITEMS):
            await _send_line_photo_prompt(message, session)
        else:
            session["flow"] = "line_rating"
            await _send_line_rating(message, session)
        return

    await message.answer("Сейчас фото не ожидается. Выберите действие в меню.")


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
    label = RATING_LABELS.get(value, str(value))
    try:
        await send_line_report(
            callback.bot,
            callback.from_user,
            LINE_PHOTO_ITEMS,
            session["line_photos"],
            LINE_RATING_QUESTION,
            value,
            label,
        )
    except TelegramBadRequest as e:
        logger.exception("send_line_report failed")
        await callback.message.answer(
            "Не удалось отправить отчёт в группу. Проверьте бота в группе и ID (с минусом для супергруппы). "
            f"{e}"
        )
        _reset_session(session)
        await callback.answer()
        return
    except Exception as e:
        logger.exception("send_line_report failed")
        await callback.message.answer(f"Ошибка отправки отчёта: {e}")
        _reset_session(session)
        await callback.answer()
        return
    await callback.message.answer("Лайн-чек отправлен в группу администратора. Спасибо!")
    _reset_session(session)
    await callback.answer()


@router.callback_query(F.data.startswith("tech_pick:"))
async def on_tech_pick(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if session.get("flow") != "tech":
        await callback.answer()
        return
    if not callback.data or not callback.message:
        await callback.answer()
        return
    idx = int(callback.data.split(":", 1)[1])
    matches = session.get("tech_matches") or []
    if idx < 0 or idx >= len(matches):
        await callback.answer("Устаревший выбор, введите запрос снова.", show_alert=True)
        return
    chosen = matches[idx]
    text = str(chosen.get("text", "")).strip() or "Текст техкарты пуст."
    name = str(chosen.get("name", ""))
    await callback.message.answer(
        f"<b>{html.escape(name)}</b>\n\n{html.escape(text)}",
        parse_mode="HTML",
        reply_markup=main_menu_reply(),
    )
    session["tech_matches"] = []
    await callback.answer()


@router.message(F.text)
async def on_text(message: Message, session: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    if text in MENU_BUTTONS:
        await _handle_menu_press(message, session, text)
        return

    flow = session.get("flow")

    if flow == "closing_text":
        if not message.from_user:
            return
        answers = session.setdefault("closing_texts", [])
        answers.append(text)
        if len(answers) < len(CLOSING_TEXT_PROMPTS):
            session["step"] = len(answers)
            await _send_closing_text_prompt(message, session)
        else:
            try:
                await send_closing_report(
                    message.bot,
                    message.from_user,
                    CLOSING_PHOTO_ITEMS,
                    session["closing_photos"],
                    CLOSING_TEXT_PROMPTS,
                    answers,
                )
            except TelegramBadRequest as e:
                logger.exception("send_closing_report failed")
                await message.answer(
                    "Не удалось отправить отчёт в группу. Проверьте бота в группе и ID (с минусом). "
                    f"{e}"
                )
                _reset_session(session)
                return
            except Exception as e:
                logger.exception("send_closing_report failed")
                await message.answer(f"Ошибка отправки отчёта: {e}")
                _reset_session(session)
                return
            await message.answer("Отчёт по закрытию отправлен в группу администратора. Спасибо!")
            _reset_session(session)
        return

    if flow == "tech":
        recipes = await load_recipes()
        matches = search_recipes(recipes, text)
        session["tech_matches"] = matches
        if not matches:
            await message.answer("Ничего не найдено. Попробуйте другое название или слова.")
            return
        if len(matches) == 1:
            r = matches[0]
            body = str(r.get("text", "")).strip() or "Текст техкарты пуст."
            name = str(r.get("name", ""))
            await message.answer(
                f"<b>{html.escape(name)}</b>\n\n{html.escape(body)}",
                parse_mode="HTML",
                reply_markup=main_menu_reply(),
            )
            return
        cap = min(len(matches), 8)
        names = [str(m.get("name", "")) for m in matches[:cap]]
        idxs = list(range(cap))
        await message.answer(
            "Несколько совпадений — выберите кнопкой:",
            reply_markup=tech_pick_inline(idxs, names),
        )
        return

    if flow == "line_rating":
        await message.answer("Сейчас нужно нажать оценку кнопками под предыдущим сообщением.")
        return

    await message.answer("Выберите действие кнопками меню.", reply_markup=main_menu_reply())
