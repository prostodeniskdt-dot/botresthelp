from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import TTK_PAGE_SIZE
from bot.renderers.ttk_renderer import ttk_card_is_long
from bot.ttk_data import TtkStore

CALLBACK_LIMIT = 64


def _cb(data: str) -> str:
    if len(data.encode("utf-8")) > CALLBACK_LIMIT:
        raise ValueError(f"callback_data too long ({len(data.encode('utf-8'))} bytes): {data!r}")
    return data


def _nav_row(prefix: str, page: int, total: int, page_size: int) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=_cb(f"{prefix}:{page - 1}")))
    if (page + 1) * page_size < total:
        buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=_cb(f"{prefix}:{page + 1}")))
    return buttons


def ttk_home_keyboard(store: TtkStore) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, cat in enumerate(store.categories):
        title = str(cat.get("title") or cat.get("id") or idx)[:60]
        row.append(InlineKeyboardButton(text=title, callback_data=_cb(f"tk:c:{idx}:0")))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="🔎 Поиск", callback_data="tk:q"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="tk:menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ttk_items_keyboard(
    store: TtkStore,
    category_idx: int,
    page: int,
    *,
    page_size: int = TTK_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    category_id = store.category_id_at(category_idx)
    items = store.items_in_category(category_id)
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(items))
    for item in items[start:end]:
        title = str(item.get("title") or "")[:60]
        item_idx = store.item_idx(str(item.get("id") or ""))
        if item_idx is None:
            continue
        rows.append([InlineKeyboardButton(text=title, callback_data=_cb(f"tk:i:{item_idx}"))])
    nav = _nav_row(f"tk:cp:{category_idx}", page, len(items), page_size)
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="🔎 Поиск", callback_data="tk:q"),
            InlineKeyboardButton(text="📋 Все ТТК", callback_data="tk:h"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="tk:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ttk_search_results_keyboard(
    store: TtkStore,
    items: list[dict[str, Any]],
    page: int,
    *,
    page_size: int = TTK_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(items))
    for item in items[start:end]:
        title = str(item.get("title") or "")[:50]
        category = str(item.get("category") or "")[:12]
        label = f"{title} ({category})"[:64]
        item_idx = store.item_idx(str(item.get("id") or ""))
        if item_idx is None:
            continue
        rows.append([InlineKeyboardButton(text=label, callback_data=_cb(f"tk:i:{item_idx}"))])
    nav = _nav_row("tk:sp", page, len(items), page_size)
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="📋 Все ТТК", callback_data="tk:h"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="tk:menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ttk_card_keyboard(
    store: TtkStore,
    item: dict[str, Any],
    *,
    back_callback: str,
    long_card: bool | None = None,
) -> InlineKeyboardMarkup:
    item_idx = store.item_idx(str(item.get("id") or ""))
    if item_idx is None:
        item_idx = 0
    long_card = ttk_card_is_long(item) if long_card is None else long_card
    rows: list[list[InlineKeyboardButton]] = []
    if long_card:
        rows.append(
            [
                InlineKeyboardButton(text="🧾 Состав", callback_data=_cb(f"tk:v:{item_idx}:i")),
                InlineKeyboardButton(text="🍽 Подача", callback_data=_cb(f"tk:v:{item_idx}:s")),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="⚙️ Приготовление", callback_data=_cb(f"tk:v:{item_idx}:p")),
                InlineKeyboardButton(text="📄 Все данные", callback_data=_cb(f"tk:v:{item_idx}:f")),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ Назад к разделу", callback_data=back_callback),
            InlineKeyboardButton(text="🔎 Поиск", callback_data="tk:q"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="📋 Все ТТК", callback_data="tk:h"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="tk:menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
