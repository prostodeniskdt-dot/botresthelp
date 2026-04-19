"""
Структура техкарты из тела ТТК (табуляции + метки Бокал/Метод/…) и HTML для Telegram.
"""

from __future__ import annotations

import html
import re
from typing import Any

LABEL_RE = re.compile(
    r"^\s*(Бокал|Метод|Лед|Украшение|Пребэтч|Выход)\s*:\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

KEY_MAP = {
    "бокал": "glass",
    "метод": "method",
    "лед": "ice",
    "украшение": "garnish",
    "пребэтч": "prebatch",
    "выход": "yield",
}

_META_ORDER: tuple[tuple[str, str], ...] = (
    ("method", "Метод"),
    ("glass", "Бокал"),
    ("ice", "Лед"),
    ("garnish", "Украшение"),
    ("prebatch", "Пребэтч"),
    ("yield", "Выход"),
)


def _ingredient_join(parts: list[str]) -> str:
    return "  ".join(p.strip() for p in parts if p.strip())


def _format_plain_ingredient(s: str) -> str:
    s = s.strip()
    m = re.match(r"^([\d.,]+)\s+(\S+)\s+(.+)$", s)
    if m:
        return f"{m.group(1)}  {m.group(2)}  {m.group(3).strip()}"
    return s


def _starts_amount(s: str) -> bool:
    return bool(re.match(r"^[\d.,]+\s*", s.strip()))


def _set_meta(meta: dict[str, str | None], key: str, value: str) -> None:
    value = (value or "").strip()
    if not value:
        return
    if meta.get(key):
        return
    meta[key] = value


def _label_match(part: str) -> tuple[str | None, str]:
    m = LABEL_RE.match(part.strip())
    if not m:
        return None, part
    ru = m.group(1).lower()
    key = KEY_MAP.get(ru)
    if not key:
        return None, part
    return key, (m.group(2) or "").strip()


def _parse_plain_line(
    line: str,
    ingredients: list[str],
    notes: list[str],
    meta: dict[str, str | None],
) -> None:
    key, rest = _label_match(line)
    if key:
        _set_meta(meta, key, rest)
        return
    low = line.lower().strip()
    if low in ("подача:", "приготовление:"):
        return
    if _starts_amount(line):
        ingredients.append(_format_plain_ingredient(line))
        return
    notes.append(line.strip())


def _parse_tab_line(
    line: str,
    ingredients: list[str],
    notes: list[str],
    meta: dict[str, str | None],
) -> None:
    parts = [p.strip() for p in line.split("\t")]
    i = 0
    while i < len(parts):
        p = parts[i]
        if not p:
            i += 1
            continue

        key, rest = _label_match(p)
        if key:
            val = rest
            if not val and i + 1 < len(parts):
                nk, _ = _label_match(parts[i + 1])
                if not nk:
                    val = parts[i + 1]
                    i += 1
            _set_meta(meta, key, val)
            i += 1
            continue

        if not _starts_amount(p):
            j = i + 1
            while j < len(parts):
                if _label_match(parts[j])[0]:
                    break
                if _starts_amount(parts[j]):
                    break
                j += 1
            chunk = parts[i:j]
            lead = " ".join(chunk).strip()
            if lead:
                notes.append(lead)
            i = j
            continue

        seg_start = i
        i += 1
        while i < len(parts):
            nk, _ = _label_match(parts[i])
            if nk:
                break
            if _starts_amount(parts[i]) and i > seg_start:
                break
            i += 1
        seg = parts[seg_start:i]
        if seg:
            ingredients.append(_ingredient_join(seg))


def parse_ttk_body(text: str) -> dict[str, Any]:
    text = text.replace("\r\n", "\n").strip()
    ingredients: list[str] = []
    notes: list[str] = []
    meta: dict[str, str | None] = {
        "method": None,
        "glass": None,
        "ice": None,
        "garnish": None,
        "prebatch": None,
        "yield": None,
    }

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            _parse_tab_line(line, ingredients, notes, meta)
        else:
            _parse_plain_line(line, ingredients, notes, meta)

    out: dict[str, Any] = {"ingredients": ingredients, "notes": notes}
    for k, v in meta.items():
        if v:
            out[k] = v
    return out


def recipe_to_html(recipe: dict[str, Any]) -> str:
    """Форматирует карточку: notes (инструкции), ингредиенты, затем мета с жирными подписями."""
    if recipe.get("text") and not recipe.get("ingredients"):
        return html.escape(str(recipe["text"]).strip())

    lines: list[str] = []
    notes = recipe.get("notes") or []
    for n in notes:
        t = str(n).strip()
        if t:
            if lines:
                lines.append("")
            lines.append(html.escape(t))

    ingredients = recipe.get("ingredients") or []
    if ingredients:
        if lines:
            lines.append("")
        for ing in ingredients:
            lines.append(html.escape(str(ing).strip()))

    meta_lines: list[str] = []
    for key, label in _META_ORDER:
        val = recipe.get(key)
        if not val:
            continue
        meta_lines.append(f"<b>{html.escape(label)}:</b>  {html.escape(str(val).strip())}")

    if meta_lines:
        if lines:
            lines.append("")
        lines.extend(meta_lines)

    return "\n".join(lines) if lines else "Текст техкарты пуст."


def recipe_search_blob(r: dict[str, Any]) -> str:
    parts: list[str] = [str(r.get("name", ""))]
    if r.get("aliases") and isinstance(r["aliases"], list):
        parts.extend(str(a) for a in r["aliases"])
    parts.extend(str(x) for x in (r.get("ingredients") or []))
    for key, _ in _META_ORDER:
        v = r.get(key)
        if v:
            parts.append(str(v))
    parts.extend(str(x) for x in (r.get("notes") or []))
    if r.get("text"):
        parts.append(str(r["text"]))
    return " ".join(parts)
