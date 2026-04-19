from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.content import BTN_CLOSING, BTN_LINE, BTN_OPENING, BTN_TECH, RATING_LABELS


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
