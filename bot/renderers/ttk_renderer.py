from __future__ import annotations

from typing import Any

from bot.renderers.common import (
    CARD_DIVIDER,
    LONG_CARD_THRESHOLD,
    escape_html,
    join_blocks,
    render_bullets,
    render_card_title,
    render_labeled_bullets,
    render_section,
)

CATEGORY_EMOJI = {
    "авторские_коктейли": "🍸",
    "классические_коктейли": "🥃",
    "авторские_чаи": "🫖",
    "лимонады": "🍋",
    "сезон": "🍷",
    "настойки": "🍶",
    "заготовки": "🧪",
    "чай_кофе": "☕",
    "signature_cocktails": "🍸",
    "classic_cocktails": "🥃",
    "signature_tea": "🫖",
    "lemonades": "🍋",
    "infusions": "🍶",
    "preparations": "🧪",
    "tea_coffee": "☕",
}


def _category_emoji(item: dict[str, Any]) -> str:
    cat_id = str(item.get("category_id") or "")
    if cat_id in CATEGORY_EMOJI:
        return CATEGORY_EMOJI[cat_id]
    title = str(item.get("category") or "")
    return title.split()[0] if title else "📋"


def _service_value(item: dict[str, Any], ru_key: str, en_key: str) -> str:
    val = item.get(en_key)
    if val:
        return str(val).strip()
    service = item.get("service") or {}
    if isinstance(service, dict):
        return str(service.get(ru_key) or "").strip()
    return ""


def _ingredient_lines(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for ing in item.get("ingredients") or []:
        if not isinstance(ing, dict):
            continue
        amount = str(ing.get("amount") or "").strip()
        unit = str(ing.get("unit") or "").strip()
        name = str(ing.get("name") or "").strip()
        if not name:
            continue
        qty = " ".join(part for part in (amount, unit) if part).strip()
        if qty:
            lines.append(f"{qty} — {name}")
        else:
            lines.append(name)
    return lines


def _ingredients_block(item: dict[str, Any]) -> str:
    lines = _ingredient_lines(item)
    if not lines:
        return ""
    return render_section("Состав", [render_bullets(lines)], "🧾")


def _service_block(item: dict[str, Any]) -> str:
    pairs = [
        ("Бокал", _service_value(item, "Бокал", "glass")),
        ("Метод", _service_value(item, "Метод", "method")),
        ("Лёд", _service_value(item, "Лед", "ice")),
        ("Украшение", _service_value(item, "Украшение", "garnish")),
    ]
    prebatch = _service_value(item, "Пребэтч", "prebatch")
    body = render_labeled_bullets(pairs)
    if prebatch:
        prebatch_block = render_section("Пребэтч", [escape_html(prebatch)], "🧴")
        return join_blocks([render_section("Подача", [body], "🍽") if body else "", prebatch_block])
    if not body:
        return ""
    return render_section("Подача", [body], "🍽")


def _preparation_block(item: dict[str, Any]) -> str:
    blocks: list[str] = []
    preparation = str(item.get("preparation") or "").strip()
    if preparation:
        blocks.append(render_section("Приготовление", [escape_html(preparation)], "⚙️"))
    output = str(item.get("output") or "").strip()
    if output:
        blocks.append(render_section("Выход", [escape_html(output)], "📦"))
    notes = [str(n).strip() for n in (item.get("notes") or []) if str(n).strip()]
    if notes:
        blocks.append(render_section("Примечания", [render_bullets(notes)], "📝"))
    return join_blocks(blocks)


def _header(item: dict[str, Any]) -> str:
    emoji = _category_emoji(item)
    title = str(item.get("title") or "")
    subtitle = str(item.get("category") or "")
    return render_card_title(emoji, title, subtitle)


def render_ttk_card(item: dict[str, Any], view: str = "d") -> str:
    header = _header(item)
    ingredients = _ingredients_block(item)
    service = _service_block(item)
    preparation = _preparation_block(item)

    if view == "i":
        return join_blocks([header, ingredients]) or header
    if view == "s":
        return join_blocks([header, service]) or header
    if view == "p":
        return join_blocks([header, preparation]) or header
    if view == "f":
        return join_blocks([header, ingredients, service, preparation]) or header

    full = join_blocks([header, ingredients, service, preparation])
    if len(full) <= LONG_CARD_THRESHOLD:
        return full

    short = join_blocks([header, ingredients, service])
    if preparation:
        short += f"\n\n<i>Есть технология приготовления — откройте «⚙️ Приготовление» или «📄 Все данные».</i>"
    return short


def ttk_card_is_long(item: dict[str, Any]) -> bool:
    full = render_ttk_card(item, "f")
    return len(full) > LONG_CARD_THRESHOLD
