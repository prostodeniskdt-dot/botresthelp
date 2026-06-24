from __future__ import annotations

import re
from typing import Any

from bot.ttk_data import TtkStore


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _item_blob(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("category") or ""),
        str(item.get("search_text") or ""),
        str(item.get("method") or ""),
        str(item.get("glass") or ""),
        str(item.get("garnish") or ""),
        str(item.get("prebatch") or ""),
        str(item.get("preparation") or ""),
        str(item.get("output") or ""),
    ]
    for ing in item.get("ingredients") or []:
        if isinstance(ing, dict):
            parts.extend(str(ing.get(key) or "") for key in ("amount", "unit", "name"))
    service = item.get("service") or {}
    if isinstance(service, dict):
        parts.extend(str(v) for v in service.values() if v)
    parts.extend(str(n) for n in (item.get("notes") or []))
    return _norm(" ".join(parts))


def search_ttk(store: TtkStore, query: str) -> list[dict[str, Any]]:
    q = _norm(query)
    if not q:
        return []

    results: list[tuple[int, dict[str, Any]]] = []
    for item in store.active_items:
        title = _norm(str(item.get("title") or ""))
        haystack = _item_blob(item)
        score = 0
        if title == q:
            score = 1000
        elif q in title:
            score = 500
        elif q in haystack:
            score = 100
        else:
            words = [w for w in q.split(" ") if len(w) >= 2]
            if words and all(w in haystack for w in words):
                score = 50 + len(words)
        if score:
            results.append((score, item))

    results.sort(key=lambda x: (-x[0], _norm(x[1].get("title", ""))))
    return [item for _, item in results]
