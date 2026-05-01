from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.content import (
    BTN_BACK,
    BTN_CLOSING,
    BTN_INVOICES,
    BTN_LINE,
    BTN_MOVE,
    BTN_OPENING,
    BTN_TECH,
    BTN_WRITE_OFF,
    RATING_LABELS,
)


def main_menu_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_OPENING),
                KeyboardButton(text=BTN_CLOSING),
            ],
            [
                KeyboardButton(text=BTN_LINE),
                KeyboardButton(text=BTN_TECH),
            ],
            [
                KeyboardButton(text=BTN_INVOICES),
                KeyboardButton(text=BTN_MOVE),
                KeyboardButton(text=BTN_WRITE_OFF),
            ],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def line_rating_inline() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for value, label in RATING_LABELS.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"line_rate:{value}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_switch_inline(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, переключить", callback_data=f"switch_yes:{action}"),
                InlineKeyboardButton(text="Нет", callback_data="switch_no"),
            ]
        ]
    )


def tech_pick_inline(indices: list[int], names: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for i, name in zip(indices, names):
        buttons.append([InlineKeyboardButton(text=name[:64], callback_data=f"tech_pick:{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def tech_pick_page_inline(
    *,
    matches: list[dict],
    offset: int,
    page_size: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    n = len(matches)
    end = min(offset + page_size, n)
    for i in range(offset, end):
        name = str(matches[i].get("name", ""))[:64]
        rows.append([InlineKeyboardButton(text=name, callback_data=f"tech_pick:{i}")])
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_off = max(0, offset - page_size)
        nav.append(InlineKeyboardButton(text="◀️ Стр.", callback_data=f"tech_nav:{prev_off}"))
    if end < n:
        nav.append(InlineKeyboardButton(text="Стр. ▶️", callback_data=f"tech_nav:{end}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
