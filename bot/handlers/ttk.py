from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.config import TTK_PAGE_SIZE
from bot.content import BTN_TTK
from bot.keyboards import main_menu_reply
from bot.renderers.common import split_message
from bot.renderers.ttk_renderer import render_ttk_card
from bot.ttk_data import TTK_HOME_TEXT, SEARCH_EMPTY_TEXT, load_ttk_store
from bot.ttk_keyboards import (
    ttk_card_keyboard,
    ttk_home_keyboard,
    ttk_items_keyboard,
    ttk_search_results_keyboard,
)
from bot.ttk_search import search_ttk

router = Router()
logger = logging.getLogger(__name__)

_CARD_VIEWS = {
    "d": "d",
    "i": "i",
    "s": "s",
    "p": "p",
    "f": "f",
}


async def send_ttk_home(message: Message) -> None:
    store = await load_ttk_store()
    await message.answer(TTK_HOME_TEXT, reply_markup=ttk_home_keyboard(store))


def _set_category_back(session: dict[str, Any], category_idx: int, page: int) -> None:
    session["ttk_back"] = f"tk:c:{category_idx}:{page}"


def _set_search_back(session: dict[str, Any], page: int) -> None:
    session["ttk_back"] = f"tk:sp:{page}"


async def _send_card(
    target: Message | CallbackQuery,
    item: dict[str, Any],
    view: str,
    session: dict[str, Any],
    store: Any,
) -> None:
    text = render_ttk_card(item, _CARD_VIEWS.get(view, "d"))
    back_cb = str(session.get("ttk_back") or "tk:h")
    markup = ttk_card_keyboard(store, item, back_callback=back_cb)
    chunks = split_message(text)
    message = target if isinstance(target, Message) else target.message
    if message is None:
        return
    if isinstance(target, CallbackQuery) and len(chunks) == 1:
        try:
            await message.edit_text(chunks[0], parse_mode="HTML", reply_markup=markup)
            return
        except TelegramBadRequest:
            logger.debug("ttk_card_edit_fallback item=%s", item.get("id"))
        except Exception:
            logger.exception("ttk_card_edit_failed item=%s", item.get("id"))
    for idx, chunk in enumerate(chunks):
        reply_markup = markup if idx == len(chunks) - 1 else None
        await message.answer(chunk, parse_mode="HTML", reply_markup=reply_markup)


@router.message(F.text == BTN_TTK)
async def on_ttk_button(message: Message, session: dict[str, Any]) -> None:
    session.pop("ttk_back", None)
    session.pop("ttk_search_results", None)
    if session.get("flow") == "ttk_search":
        session["flow"] = "idle"
    await send_ttk_home(message)


@router.callback_query(F.data == "tk:h")
async def on_ttk_home(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session.pop("ttk_back", None)
    session.pop("ttk_search_results", None)
    if session.get("flow") == "ttk_search":
        session["flow"] = "idle"
    store = await load_ttk_store()
    if callback.message:
        await callback.message.answer(TTK_HOME_TEXT, reply_markup=ttk_home_keyboard(store))
    await callback.answer()


@router.callback_query(F.data == "tk:menu")
async def on_ttk_main_menu(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session.pop("ttk_back", None)
    session.pop("ttk_search_results", None)
    session["flow"] = "idle"
    if callback.message:
        await callback.message.answer("Главное меню 👇", reply_markup=main_menu_reply())
    await callback.answer()


@router.callback_query(F.data == "tk:q")
async def on_ttk_search_start(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session["flow"] = "ttk_search"
    session.pop("ttk_back", None)
    if callback.message:
        await callback.message.answer(
            "🔎 Напишите запрос: название, ингредиент, метод, бокал или категорию.",
            reply_markup=main_menu_reply(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("tk:c:"))
async def on_ttk_category(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    try:
        category_idx = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except (ValueError, IndexError):
        await callback.answer("Устаревшая кнопка", show_alert=True)
        return
    store = await load_ttk_store()
    category_id = store.category_id_at(category_idx)
    items = store.items_in_category(category_id)
    if not items:
        logger.warning("ttk_empty_category idx=%s id=%s", category_idx, category_id)
        await callback.message.edit_text(
            f"{store.category_title(category_id)}\n\nВ этом разделе пока нет позиций.",
            reply_markup=ttk_home_keyboard(store),
        )
        await callback.answer()
        return
    _set_category_back(session, category_idx, page)
    title = store.category_title(category_id)
    try:
        await callback.message.edit_text(
            f"{title}. Выберите позицию:",
            reply_markup=ttk_items_keyboard(store, category_idx, page),
        )
    except TelegramBadRequest:
        logger.exception("ttk_category_keyboard_failed idx=%s", category_idx)
        await callback.message.answer(
            f"{title}. Выберите позицию:",
            reply_markup=ttk_items_keyboard(store, category_idx, page),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("tk:cp:"))
async def on_ttk_category_page(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    try:
        category_idx = int(parts[2])
        page = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer()
        return
    store = await load_ttk_store()
    _set_category_back(session, category_idx, page)
    await callback.message.edit_reply_markup(
        reply_markup=ttk_items_keyboard(store, category_idx, page),
    )
    await callback.answer(f"Стр. {page + 1}")


@router.callback_query(F.data.startswith("tk:i:"))
async def on_ttk_item(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    try:
        item_idx = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer("Устаревшая кнопка", show_alert=True)
        return
    store = await load_ttk_store()
    item = store.item_at(item_idx)
    if not item or item.get("archived"):
        logger.error("ttk_item_not_found idx=%s", item_idx)
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    if not session.get("ttk_back"):
        cat_id = str(item.get("category_id") or "")
        _set_category_back(session, store.category_idx(cat_id), 0)
    await _send_card(callback, item, "d", session, store)
    await callback.answer()


@router.callback_query(F.data.startswith("tk:v:"))
async def on_ttk_item_view(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    try:
        item_idx = int(parts[2])
    except ValueError:
        await callback.answer("Устаревшая кнопка", show_alert=True)
        return
    view = parts[3]
    store = await load_ttk_store()
    item = store.item_at(item_idx)
    if not item or item.get("archived"):
        logger.error("ttk_item_not_found idx=%s view=%s", item_idx, view)
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await _send_card(callback, item, view, session, store)
    await callback.answer()


@router.callback_query(F.data.startswith("tk:sp:"))
async def on_ttk_search_page(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    page = int(callback.data.split(":", 2)[2])
    results = session.get("ttk_search_results") or []
    if not results:
        await callback.answer("Сначала выполните поиск", show_alert=True)
        return
    store = await load_ttk_store()
    _set_search_back(session, page)
    await callback.message.edit_text(
        f"Нашёл {len(results)} позиций — выберите:",
        reply_markup=ttk_search_results_keyboard(store, results, page, page_size=TTK_PAGE_SIZE),
    )
    await callback.answer(f"Результаты, стр. {page + 1}")


async def handle_ttk_search(message: Message, session: dict[str, Any], query: str) -> bool:
    if session.get("flow") != "ttk_search":
        return False
    store = await load_ttk_store()
    results = search_ttk(store, query)
    session["ttk_search_results"] = results
    if not results:
        logger.info("ttk_search_empty query=%r", query)
        await message.answer(SEARCH_EMPTY_TEXT, reply_markup=ttk_home_keyboard(store))
        session["flow"] = "idle"
        return True
    _set_search_back(session, 0)
    if len(results) == 1:
        await _send_card(message, results[0], "d", session, store)
        session["flow"] = "idle"
        return True
    await message.answer(
        f"Нашёл {len(results)} позиций — выберите:",
        reply_markup=ttk_search_results_keyboard(store, results, 0, page_size=TTK_PAGE_SIZE),
    )
    session["flow"] = "idle"
    return True
