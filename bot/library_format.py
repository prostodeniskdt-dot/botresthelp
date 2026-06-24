from __future__ import annotations

import html
from typing import Any

from bot.library_data import (
    ALLERGEN_DISCLAIMER,
    SALE_FIELD_KEYS,
    SUMMARY_FIELD_ORDER,
    WARN_FIELD_KEYS,
)


def _field(fields: dict[str, Any], key: str) -> str:
    val = fields.get(key)
    if val is None:
        return ""
    return str(val).strip()


def _first_field(fields: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, str]:
    for key in keys:
        val = _field(fields, key)
        if val:
            return key, val
    return "", ""


def _header_lines(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    title = str(item.get("title", "")).strip()
    if title:
        lines.append(f"<b>{html.escape(title)}</b>")

    price = str(item.get("price", "")).strip()
    fmt = str(item.get("format_or_serving", "")).strip()
    group = str(item.get("group", "")).strip()
    section_name = str(item.get("section_name", "")).strip()

    if group:
        lines.append(f"Категория: {html.escape(group)}")
    elif section_name:
        lines.append(html.escape(section_name))

    if fmt and price:
        lines.append(f"Порция/цена: {html.escape(fmt)} / {html.escape(price)}")
    elif price:
        lines.append(f"Цена: {html.escape(price)}")
    elif fmt:
        lines.append(f"Формат: {html.escape(fmt)}")
    return lines


def format_item_summary(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    lines = _header_lines(item)
    section_code = str(item.get("section_code", ""))
    for key in SUMMARY_FIELD_ORDER.get(section_code, []):
        val = _field(fields, key)
        if val:
            lines.append(f"{html.escape(key)}: {html.escape(val)}")
    return "\n".join(lines)


def format_item_sale(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    title = html.escape(str(item.get("title", "")))
    _, phrase = _first_field(fields, SALE_FIELD_KEYS)
    story = _field(fields, "Сторителлинг 20–30 сек") or _field(fields, "История для гостя")
    pretty = _field(fields, "Красивое описание для гостя")
    lines = [f"💬 <b>Фраза продажи — {title}</b>"]
    if phrase:
        lines.append(html.escape(phrase))
    if pretty:
        lines.append(f"\n{html.escape(pretty)}")
    if story:
        lines.append(f"\n🎙 {html.escape(story)}")
    if not phrase and not pretty and not story:
        lines.append("Готовая фраза не указана.")
    return "\n".join(lines)


def format_item_qa(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    question = _field(fields, "Вопрос") or _field(fields, "Зацепка для аттестации")
    answer = _field(fields, "Ответ") or _field(fields, "Что запомнить на аттестацию")
    title = html.escape(str(item.get("title", "")))
    if question and answer:
        return (
            f"🎓 <b>Вопрос для аттестации — {title}</b>\n"
            f"Вопрос: {html.escape(question)}\n"
            f"Ответ: {html.escape(answer)}"
        )
    if answer:
        return f"🎓 <b>{title}</b>\nОтвет: {html.escape(answer)}"
    return f"❓ <b>{title}</b>\nВопрос и ответ для этой позиции не указаны."


def format_item_warning(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    title = html.escape(str(item.get("title", "")))
    parts: list[str] = [f"⚠️ <b>Важно — {title}</b>", ALLERGEN_DISCLAIMER]
    found = False
    for key in WARN_FIELD_KEYS:
        val = _field(fields, key)
        if val:
            parts.append(f"\n<b>{html.escape(key)}:</b> {html.escape(val)}")
            found = True
    if not found:
        parts.append("\nОтдельных предупреждений нет — всё равно уточняйте аллергии у гостя.")
    return "\n".join(parts)


def format_item_full(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    lines = _header_lines(item)
    lines.append("")
    for key, val in fields.items():
        text = str(val).strip()
        if text:
            lines.append(f"<b>{html.escape(str(key))}:</b> {html.escape(text)}")
    return "\n".join(lines)


def split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks
