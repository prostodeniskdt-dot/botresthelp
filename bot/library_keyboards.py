from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import LIBRARY_PAGE_SIZE
from bot.library_data import LIBRARY_SECTIONS, LibraryStore


def _nav_row(prefix: str, page: int, total: int, page_size: int) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}"))
    if (page + 1) * page_size < total:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}"))
    return buttons


def library_home_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, label in LIBRARY_SECTIONS:
        row.append(InlineKeyboardButton(text=label, callback_data=f"lb:s:{code}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_groups_keyboard(
    store: LibraryStore,
    section_code: str,
    page: int,
    *,
    page_size: int = LIBRARY_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    groups = store.groups_by_section.get(section_code, [])
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(groups))
    for idx in range(start, end):
        label = groups[idx][:60] or f"Группа {idx + 1}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"lb:g:{section_code}:{idx}:0")])
    nav = _nav_row(f"lb:sg:{section_code}", page, len(groups), page_size)
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 В библиотеку", callback_data="lb:h")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_items_keyboard(
    store: LibraryStore,
    section_code: str,
    group_idx: int,
    page: int,
    *,
    page_size: int = LIBRARY_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    items = store.items_in_group(section_code, group_idx)
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(items))
    for item in items[start:end]:
        title = str(item.get("title", ""))[:60]
        item_id = str(item.get("id", ""))
        rows.append([InlineKeyboardButton(text=title, callback_data=f"lb:i:{item_id}")])
    nav = _nav_row(f"lb:ip:{section_code}:{group_idx}", page, len(items), page_size)
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ К группам", callback_data=f"lb:s:{section_code}:0"),
            InlineKeyboardButton(text="🏠 В библиотеку", callback_data="lb:h"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_search_results_keyboard(
    items: list[dict[str, Any]],
    page: int,
    *,
    page_size: int = LIBRARY_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(items))
    for item in items[start:end]:
        title = str(item.get("title", ""))[:50]
        section = str(item.get("section_name", ""))[:10]
        label = f"{title} ({section})"[:64]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"lb:i:{item['id']}")])
    nav = _nav_row("lb:sp", page, len(items), page_size)
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 В библиотеку", callback_data="lb:h")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_card_keyboard(
    item: dict[str, Any],
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    item_id = str(item.get("id", ""))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Как сказать гостю", callback_data=f"lb:v:{item_id}:s"),
                InlineKeyboardButton(text="📖 История", callback_data=f"lb:v:{item_id}:h"),
            ],
            [
                InlineKeyboardButton(text="❓ Аттестация", callback_data=f"lb:v:{item_id}:q"),
                InlineKeyboardButton(text="⚠️ Важно", callback_data=f"lb:v:{item_id}:w"),
            ],
            [
                InlineKeyboardButton(text="🧾 Все данные", callback_data=f"lb:v:{item_id}:f"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback),
                InlineKeyboardButton(text="🏠 В библиотеку", callback_data="lb:h"),
            ],
        ]
    )


def library_storytelling_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    nav = _nav_row("lb:st", page, total, 1)
    rows: list[list[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 В библиотеку", callback_data="lb:h")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
