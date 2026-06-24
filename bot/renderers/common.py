from __future__ import annotations

import html
from typing import Iterable

CARD_DIVIDER = "━━━━━━━━━━━━━━"
MESSAGE_LIMIT = 4000
LONG_CARD_THRESHOLD = 3500


def escape_html(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value).strip())


def render_card_title(emoji: str, title: str, subtitle: str | None = None) -> str:
    lines = [f"{emoji} <b>{escape_html(title)}</b>"]
    if subtitle:
        lines.append(f"<code>{escape_html(subtitle)}</code>")
    lines.append(CARD_DIVIDER)
    return "\n".join(lines)


def render_section(title: str, lines: Iterable[str], emoji: str | None = None) -> str:
    header = f"{emoji} " if emoji else ""
    header += f"<b>{escape_html(title)}</b>"
    parts = [header]
    for line in lines:
        text = str(line).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def render_bullets(items: Iterable[str], *, prefix: str = "•") -> str:
    rows: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            rows.append(f"{prefix} {escape_html(text)}")
    return "\n".join(rows)


def render_labeled_bullets(pairs: Iterable[tuple[str, str]], *, prefix: str = "•") -> str:
    rows: list[str] = []
    for label, value in pairs:
        label = str(label).strip()
        value = str(value).strip()
        if not value:
            continue
        if label:
            rows.append(f"{prefix} <b>{escape_html(label)}:</b> {escape_html(value)}")
        else:
            rows.append(f"{prefix} {escape_html(value)}")
    return "\n".join(rows)


def join_blocks(blocks: Iterable[str]) -> str:
    return "\n\n".join(block for block in blocks if block and block.strip())


def split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks
