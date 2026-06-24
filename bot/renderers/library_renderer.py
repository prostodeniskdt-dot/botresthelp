from __future__ import annotations

from typing import Any

from bot.library_data import ALLERGEN_DISCLAIMER, SALE_FIELD_KEYS, WARN_FIELD_KEYS
from bot.renderers.common import escape_html, join_blocks, render_bullets, render_card_title, render_section

SECTION_EMOJI = {
    "cocktails": "🍸",
    "infusions": "🍶",
    "wine": "🍷",
    "spirits": "🥃",
    "beer_soft": "🍺",
    "prep": "🧪",
    "sales": "💬",
    "dictionary": "📖",
    "allergens": "⚠️",
}


def _field(fields: dict[str, Any], key: str) -> str:
    val = fields.get(key)
    if val is None:
        return ""
    return str(val).strip()


def _first_field(fields: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = _field(fields, key)
        if val:
            return val
    return ""


def _subtitle(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    section = str(item.get("section_code") or "")
    group = str(item.get("group") or "").strip()

    if section == "wine":
        parts = [
            group,
            _field(fields, "Страна"),
            _field(fields, "Регион/аппелласьон"),
        ]
    elif section == "spirits":
        parts = [
            group or _field(fields, "Категория"),
            _field(fields, "Страна/регион"),
            _field(fields, "Стиль/выдержка"),
        ]
    elif section == "infusions":
        parts = [group, _field(fields, "Профиль"), _field(fields, "База")]
    elif section == "cocktails":
        parts = [group, _field(fields, "Основа"), _field(fields, "Метод")]
    elif section == "beer_soft":
        parts = [group, _field(fields, "Стиль/состав")]
    elif section == "prep":
        parts = [group, _field(fields, "Где используется")]
    elif section == "sales":
        parts = [group]
    elif section == "dictionary":
        parts = [_field(fields, "Блок")]
    elif section == "allergens":
        parts = [group or _field(fields, "Риск/аллерген")]
    else:
        parts = [group, str(item.get("section_name") or "")]
    return " • ".join(part for part in parts if part)


def _price_block(item: dict[str, Any]) -> str:
    price = str(item.get("price") or "").strip()
    fmt = str(item.get("format_or_serving") or "").strip()
    if fmt and price:
        line = f"{fmt} — {price}"
    elif price:
        line = price
    elif fmt:
        line = fmt
    else:
        return ""
    return render_section("Порция / цена", [escape_html(line)], "💰")


def _section_blocks(item: dict[str, Any], keys: list[tuple[str, str, str]]) -> list[str]:
    fields = item.get("fields") or {}
    blocks: list[str] = []
    for field_key, title, emoji in keys:
        val = _field(fields, field_key)
        if not val:
            continue
        if "•" in val or ";" in val or "," in val and len(val) > 40:
            lines = [render_bullets(part.strip() for part in val.replace(";", ",").split(",") if part.strip())]
        else:
            lines = [escape_html(val)]
        blocks.append(render_section(title, lines, emoji))
    return blocks


def render_library_summary(item: dict[str, Any]) -> str:
    section = str(item.get("section_code") or "")
    emoji = SECTION_EMOJI.get(section, "📋")
    title = str(item.get("title") or "")
    header = render_card_title(emoji, title, _subtitle(item))
    blocks = [_price_block(item)]

    if section == "wine":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Сорт(а)", "Сортовой состав", "🍇"),
                    ("Стиль", "Стиль", "🥂"),
                    ("Тело/кислотность/танин", "Профиль", "👅"),
                    ("Ароматика", "Ароматика", "🌿"),
                    ("Pairing", "Pairing", "🍽"),
                    ("Продажная история", "Продажная история", "💬"),
                ],
            )
        )
    elif section == "spirits":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Страна/регион", "Происхождение", "🌍"),
                    ("Сырье/база", "Сырьё / база", "🌾"),
                    ("Стиль/выдержка", "Стиль / выдержка", "🏷"),
                    ("Вкус", "Вкус", "👅"),
                    ("Подача", "Подача", "🍽"),
                    ("Кому предложить", "Кому предложить", "👤"),
                    ("Готовая фраза продажи", "Как продать гостю", "💬"),
                ],
            )
        )
    elif section == "cocktails":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Ключевой состав", "Состав", "🧾"),
                    ("TTK / граммовка", "Граммовка", "⚖️"),
                    ("Вкус", "Вкус", "👅"),
                    ("Метод", "Метод", "⚙️"),
                    ("Бокал", "Бокал", "🍷"),
                    ("Лед/гарнир", "Лёд / гарнир", "🧊"),
                    ("Кому предложить", "Кому предложить", "👤"),
                    ("Готовая фраза продажи", "Фраза продажи", "💬"),
                ],
            )
        )
    elif section == "infusions":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("База", "База", "🥃"),
                    ("Ключевой состав / TTK", "Состав", "🧾"),
                    ("Вкус", "Вкус", "👅"),
                    ("Сервис / кому предложить", "Кому предложить", "👤"),
                    ("История для гостя", "История", "💬"),
                ],
            )
        )
    elif section == "beer_soft":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Стиль/состав", "Стиль / состав", "🍺"),
                    ("Вкус", "Вкус", "👅"),
                    ("Подача", "Подача", "🍽"),
                    ("Кому предложить", "Кому предложить", "👤"),
                    ("Фраза гостю", "Фраза гостю", "💬"),
                ],
            )
        )
    elif section == "prep":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Ключевые ингредиенты", "Ингредиенты", "🧾"),
                    ("Краткий метод", "Метод", "⚙️"),
                    ("Выход", "Выход", "📦"),
                    ("Что дает во вкусе", "Во вкусе", "👅"),
                    ("Что знать официанту", "Важно знать", "📌"),
                ],
            )
        )
    elif section == "sales":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Уточняющий вопрос", "Вопрос гостю", "❓"),
                    ("Что предложить", "Что предложить", "🍸"),
                    ("Почему подходит", "Почему подходит", "✅"),
                    ("Мягкий заход", "Мягкий заход", "💬"),
                    ("Фраза апсейла", "Апсейл", "⬆️"),
                ],
            )
        )
    elif section == "dictionary":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Простое объяснение", "Объяснение", "📖"),
                    ("Что сказать гостю/стажеру", "Как сказать", "💬"),
                    ("Пример", "Пример", "📝"),
                ],
            )
        )
    elif section == "allergens":
        blocks.extend(
            _section_blocks(
                item,
                [
                    ("Где встречается", "Где встречается", "📍"),
                    ("Что спросить/сказать", "Что спросить / сказать", "💬"),
                    ("Альтернатива", "Альтернатива", "🔄"),
                ],
            )
        )
    else:
        fields = item.get("fields") or {}
        generic = [
            render_section(str(key), [escape_html(str(val))], "📌")
            for key, val in fields.items()
            if str(val).strip() and key not in {"Название", "Блок", "Категория", "Раздел", "Цена"}
        ]
        blocks.extend(generic[:8])

    return join_blocks([header, *blocks])


def render_library_sale(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    title = escape_html(str(item.get("title") or ""))
    phrase = _first_field(fields, SALE_FIELD_KEYS)
    pretty = _field(fields, "Красивое описание для гостя")
    story = _field(fields, "Сторителлинг 20–30 сек") or _field(fields, "История для гостя")
    blocks = [render_card_title("💬", f"Фраза продажи — {title}", _subtitle(item))]
    if phrase:
        blocks.append(render_section("Готовая фраза", [escape_html(phrase)], "💬"))
    if pretty:
        blocks.append(render_section("Описание для гостя", [escape_html(pretty)], "✨"))
    if story:
        blocks.append(render_section("Сторителлинг", [escape_html(story)], "🎙"))
    if len(blocks) == 1:
        blocks.append("Готовая фраза не указана.")
    return join_blocks(blocks)


def render_library_qa(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    title = escape_html(str(item.get("title") or ""))
    question = _field(fields, "Вопрос") or _field(fields, "Зацепка для аттестации")
    answer = _field(fields, "Ответ") or _field(fields, "Что запомнить на аттестацию")
    blocks = [render_card_title("🎓", f"Аттестация — {title}", _subtitle(item))]
    if question:
        blocks.append(render_section("Вопрос", [escape_html(question)], "❓"))
    if answer:
        blocks.append(render_section("Ответ", [escape_html(answer)], "✅"))
    if not question and not answer:
        blocks.append("Вопрос и ответ для этой позиции не указаны.")
    return join_blocks(blocks)


def render_library_warning(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    title = escape_html(str(item.get("title") or ""))
    blocks = [render_card_title("⚠️", f"Важно — {title}", _subtitle(item)), escape_html(ALLERGEN_DISCLAIMER)]
    found = False
    warn_lines: list[str] = []
    for key in WARN_FIELD_KEYS:
        val = _field(fields, key)
        if val:
            warn_lines.append(f"<b>{escape_html(key)}:</b> {escape_html(val)}")
            found = True
    if warn_lines:
        blocks.append(render_section("Предупреждения", warn_lines, "⚠️"))
    elif not found:
        blocks.append("Отдельных предупреждений нет — всё равно уточняйте аллергии у гостя.")
    return join_blocks(blocks)


def render_library_full(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    blocks = [render_library_summary(item)]
    extra = [
        render_section(str(key), [escape_html(str(val))], "📌")
        for key, val in fields.items()
        if str(val).strip()
    ]
    if extra:
        blocks.append(join_blocks(extra))
    return join_blocks(blocks)


def render_library_card(item: dict[str, Any], view: str = "d") -> str:
    if view == "s":
        return render_library_sale(item)
    if view == "q":
        return render_library_qa(item)
    if view == "w":
        return render_library_warning(item)
    if view == "f":
        return render_library_full(item)
    return render_library_summary(item)
