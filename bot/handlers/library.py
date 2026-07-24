from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import LIBRARY_PAGE_SIZE
from bot.content import BTN_LIBRARY
from bot.keyboards import main_menu_reply
from bot.library_data import (
    LIBRARY_HOME_TEXT,
    SEARCH_EMPTY_TEXT,
    SECTION_LABELS,
    load_library_store,
)
from bot.library_format import (
    format_item_full,
    format_item_history,
    format_item_qa,
    format_item_sale,
    format_item_summary,
    format_item_warning,
    split_message,
)
from bot.library_keyboards import (
    library_card_keyboard,
    library_groups_keyboard,
    library_home_keyboard,
    library_items_keyboard,
    library_search_results_keyboard,
    library_storytelling_keyboard,
)
from bot.library_search import search_library

router = Router()
logger = logging.getLogger(__name__)

_CARD_FORMATTERS = {
    "d": format_item_summary,
    "s": format_item_sale,
    "h": format_item_history,
    "q": format_item_qa,
    "w": format_item_warning,
    "f": format_item_full,
}


async def send_library_home(message: Message) -> None:
    await message.answer(LIBRARY_HOME_TEXT, reply_markup=library_home_keyboard())


def _set_list_back(session: dict[str, Any], section_code: str, group_idx: int, page: int) -> None:
    session["library_back"] = f"lb:g:{section_code}:{group_idx}:{page}"


def _set_search_back(session: dict[str, Any], page: int) -> None:
    session["library_back"] = f"lb:sp:{page}"


async def _send_card(
    target: Message | CallbackQuery,
    item: dict[str, Any],
    view: str,
    session: dict[str, Any],
) -> None:
    formatter = _CARD_FORMATTERS.get(view, format_item_summary)
    text = formatter(item)
    back_cb = str(session.get("library_back") or "lb:h")
    markup = library_card_keyboard(item, back_callback=back_cb)
    chunks = split_message(text)
    message = target if isinstance(target, Message) else target.message
    if message is None:
        return
    if isinstance(target, CallbackQuery) and len(chunks) == 1:
        try:
            await message.edit_text(chunks[0], parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    for idx, chunk in enumerate(chunks):
        reply_markup = markup if idx == len(chunks) - 1 else None
        await message.answer(chunk, parse_mode="HTML", reply_markup=reply_markup)


@router.message(F.text == BTN_LIBRARY)
async def on_library_button(message: Message, session: dict[str, Any]) -> None:
    session.pop("library_back", None)
    session.pop("library_search_results", None)
    if session.get("flow") == "library_search":
        session["flow"] = "idle"
    await send_library_home(message)


@router.callback_query(F.data == "lb:h")
async def on_library_home(callback: CallbackQuery, session: dict[str, Any]) -> None:
    session.pop("library_back", None)
    session.pop("library_search_results", None)
    if session.get("flow") == "library_search":
        session["flow"] = "idle"
    if callback.message:
        await callback.message.answer(LIBRARY_HOME_TEXT, reply_markup=library_home_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("lb:s:"))
async def on_library_section(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    section_code = parts[2]
    try:
        page = int(parts[3])
    except ValueError:
        page = 0

    if section_code == "search":
        session["flow"] = "library_search"
        session.pop("library_back", None)
        await callback.message.answer(
            "🔎 Напишите запрос: название, вкус, ингредиент, категорию или аллерген.",
            reply_markup=main_menu_reply(),
        )
        await callback.answer()
        return

    if section_code == "storytelling":
        store = await load_library_store()
        blocks = store.storytelling_blocks
        page = max(0, min(page, max(0, len(blocks) - 1)))
        text = blocks[page] if blocks else "🎙 Сторителлинг пока пуст."
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=library_storytelling_keyboard(page, len(blocks)),
        )
        await callback.answer()
        return

    store = await load_library_store()
    groups = store.groups_by_section.get(section_code, [])
    label = SECTION_LABELS.get(section_code, section_code)

    if len(groups) <= 1:
        group_idx = 0
        items = store.items_in_group(section_code, group_idx)
        if not items:
            logger.warning("library_empty_section section=%s", section_code)
            await callback.message.edit_text(
                f"{label}\n\nПока нет позиций в этом разделе.",
                reply_markup=library_home_keyboard(),
            )
            await callback.answer()
            return
        _set_list_back(session, section_code, group_idx, 0)
        title = groups[0] if groups else label
        await callback.message.edit_text(
            f"{label} — {title}. Выберите позицию:",
            reply_markup=library_items_keyboard(store, section_code, group_idx, 0),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"{label}. Выберите подкатегорию:",
        reply_markup=library_groups_keyboard(store, section_code, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lb:sg:"))
async def on_library_section_groups_page(callback: CallbackQuery) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    section_code = parts[2]
    page = int(parts[3])
    store = await load_library_store()
    label = SECTION_LABELS.get(section_code, section_code)
    await callback.message.edit_reply_markup(
        reply_markup=library_groups_keyboard(store, section_code, page),
    )
    await callback.answer(f"{label}, стр. {page + 1}")


@router.callback_query(F.data.startswith("lb:g:"))
async def on_library_group(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    section_code = parts[2]
    group_idx = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 0
    store = await load_library_store()
    group_name = store.group_name(section_code, group_idx)
    items = store.items_in_group(section_code, group_idx)
    if not items:
        logger.warning("library_empty_group section=%s group=%s", section_code, group_name)
        await callback.answer("Список пуст", show_alert=True)
        return
    _set_list_back(session, section_code, group_idx, page)
    label = SECTION_LABELS.get(section_code, section_code)
    await callback.message.edit_text(
        f"{label} — {group_name}. Выберите позицию:",
        reply_markup=library_items_keyboard(store, section_code, group_idx, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lb:ip:"))
async def on_library_items_page(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    section_code = parts[2]
    group_idx = int(parts[3])
    page = int(parts[4])
    store = await load_library_store()
    group_name = store.group_name(section_code, group_idx)
    _set_list_back(session, section_code, group_idx, page)
    label = SECTION_LABELS.get(section_code, section_code)
    await callback.message.edit_reply_markup(
        reply_markup=library_items_keyboard(store, section_code, group_idx, page),
    )
    await callback.answer(f"{label} — {group_name}, стр. {page + 1}")


@router.callback_query(F.data.startswith("lb:i:"))
async def on_library_item(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    item_id = callback.data.split(":", 2)[2]
    store = await load_library_store()
    item = store.items_by_id.get(item_id)
    if not item:
        logger.error("library_item_not_found id=%s", item_id)
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    if not session.get("library_back"):
        section = str(item.get("section_code", ""))
        group_idx = store.group_index(section, str(item.get("group") or ""))
        _set_list_back(session, section, group_idx, 0)
    await _send_card(callback, item, "d", session)
    await callback.answer()


@router.callback_query(F.data.startswith("lb:v:"))
async def on_library_item_view(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    item_id = parts[2]
    view = parts[3]
    store = await load_library_store()
    item = store.items_by_id.get(item_id)
    if not item:
        logger.error("library_item_not_found id=%s view=%s", item_id, view)
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await _send_card(callback, item, view, session)
    await callback.answer()


@router.callback_query(F.data.startswith("lb:st:"))
async def on_library_story_page(callback: CallbackQuery) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    page = int(callback.data.split(":", 2)[2])
    store = await load_library_store()
    blocks = store.storytelling_blocks
    page = max(0, min(page, max(0, len(blocks) - 1)))
    text = blocks[page] if blocks else "🎙 Сторителлинг пока пуст."
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=library_storytelling_keyboard(page, len(blocks)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lb:sp:"))
async def on_library_search_page(callback: CallbackQuery, session: dict[str, Any]) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return
    page = int(callback.data.split(":", 2)[2])
    results = session.get("library_search_results") or []
    if not results:
        await callback.answer("Сначала выполните поиск", show_alert=True)
        return
    _set_search_back(session, page)
    await callback.message.edit_text(
        f"Нашёл {len(results)} позиций — выберите:",
        reply_markup=library_search_results_keyboard(results, page, page_size=LIBRARY_PAGE_SIZE),
    )
    await callback.answer(f"Результаты, стр. {page + 1}")


async def handle_library_search(message: Message, session: dict[str, Any], query: str) -> bool:
    if session.get("flow") != "library_search":
        return False
    store = await load_library_store()
    results = search_library(store, query)
    session["library_search_results"] = results
    if not results:
        logger.info("library_search_empty query=%r", query)
        await message.answer(SEARCH_EMPTY_TEXT, reply_markup=library_home_keyboard())
        session["flow"] = "idle"
        return True
    _set_search_back(session, 0)
    if len(results) == 1:
        item = results[0]
        await _send_card(message, item, "d", session)
        session["flow"] = "idle"
        return True
    await message.answer(
        f"Нашёл {len(results)} позиций — выберите:",
        reply_markup=library_search_results_keyboard(results, 0, page_size=LIBRARY_PAGE_SIZE),
    )
    session["flow"] = "idle"
    return True
