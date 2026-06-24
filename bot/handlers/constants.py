from bot.content import (
    BTN_CLOSING,
    BTN_INVOICES,
    BTN_LIBRARY,
    BTN_LINE,
    BTN_MOVE,
    BTN_OPENING,
    BTN_TTK,
    BTN_WRITE_OFF,
)

MENU_BUTTONS = {
    BTN_OPENING,
    BTN_CLOSING,
    BTN_LINE,
    BTN_TTK,
    BTN_LIBRARY,
    BTN_INVOICES,
    BTN_MOVE,
    BTN_WRITE_OFF,
}

FLOW_MENU_MAP: dict[str, str] = {
    BTN_OPENING: "opening",
    BTN_CLOSING: "closing",
    BTN_LINE: "line",
    BTN_TTK: "ttk",
    BTN_LIBRARY: "library",
    BTN_INVOICES: "invoices",
    BTN_MOVE: "move",
    BTN_WRITE_OFF: "write_off",
}

CURRENT_FLOW_GROUP: dict[str, str | None] = {
    "idle": None,
    "opening": "opening",
    "closing_photo": "closing",
    "closing_text": "closing",
    "line_photo": "line",
    "line_rating": "line",
    "ttk_search": "ttk",
    "invoices_product": "invoices",
    "invoices_supplier": "invoices",
    "invoices_date": "invoices",
    "invoices_photos": "invoices",
    "move_what": "move",
    "move_why": "move",
    "move_date": "move",
    "move_from_to": "move",
    "write_off_what": "write_off",
    "write_off_why": "write_off",
    "write_off_date": "write_off",
    "write_off_photo": "write_off",
    "library_search": "library",
}
