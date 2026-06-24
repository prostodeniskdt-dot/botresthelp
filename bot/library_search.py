from __future__ import annotations

import re
from typing import Any

from bot.library_data import LibraryStore


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def search_library(store: LibraryStore, query: str) -> list[dict[str, Any]]:
    q = _norm(query)
    if not q:
        return []

    results: list[tuple[int, dict[str, Any]]] = []
    for item in store.items_by_id.values():
        title = str(item.get("title", ""))
        group = str(item.get("group", ""))
        section_name = str(item.get("section_name", ""))
        searchable = _norm(str(item.get("searchable_text", "")))
        fields = item.get("fields") or {}
        field_blob = _norm(" ".join(str(v) for v in fields.values() if v))
        haystack = " ".join(filter(None, [_norm(title), _norm(group), _norm(section_name), searchable, field_blob]))

        score = 0
        if _norm(title) == q:
            score = 1000
        elif q in _norm(title):
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
