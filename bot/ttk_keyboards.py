from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import TTK_PAGE_SIZE
from bot.renderers.ttk_renderer import ttk_card_is_long
from bot.ttk_data import TtkStore


def _nav_row(prefix: str, page: int, total: int, page_size: int) -> list[InlineKeyboardButton]:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}:{page - 1}"))
    if (page + 1) * page_size < total:
        buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"{prefix}:{page + 1}"))
    return buttons


def ttk_home_keyboard(store: TtkStore) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in store.categories:
        cat_id = str(cat.get("id") or "")
        title = str(cat.get("title") or cat_id)[:60]
        row.append(InlineKeyboardButton(text=title, callback_data=f"tk:c:{cat_id}:0"))
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
    category_id: str,
    page: int,
    *,
    page_size: int = TTK_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    items = store.items_in_category(category_id)
    rows: list[list[InlineKeyboardButton]] = []
    start = page * page_size
    end = min(start + page_size, len(items))
    for item in items[start:end]:
        title = str(item.get("title") or "")[:60]
        item_id = str(item.get("id") or "")
        rows.append([InlineKeyboardButton(text=title, callback_data=f"tk:i:{item_id}")])
    nav = _nav_row(f"tk:cp:{category_id}", page, len(items), page_size)
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
        rows.append([InlineKeyboardButton(text=label, callback_data=f"tk:i:{item['id']}")])
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
    item: dict[str, Any],
    *,
    back_callback: str,
    long_card: bool | None = None,
) -> InlineKeyboardMarkup:
    item_id = str(item.get("id") or "")
    long_card = ttk_card_is_long(item) if long_card is None else long_card
    rows: list[list[InlineKeyboardButton]] = []
    if long_card:
        rows.append(
            [
                InlineKeyboardButton(text="🧾 Состав", callback_data=f"tk:v:{item_id}:i"),
                InlineKeyboardButton(text="🍽 Подача", callback_data=f"tk:v:{item_id}:s"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="⚙️ Приготовление", callback_data=f"tk:v:{item_id}:p"),
                InlineKeyboardButton(text="📄 Все данные", callback_data=f"tk:v:{item_id}:f"),
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
