from __future__ import annotations

import re
from typing import Any


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def search_recipes(recipes: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = _norm(query)
    if not q:
        return []

    results: list[tuple[int, dict[str, Any]]] = []

    for r in recipes:
        name = str(r.get("name", ""))
        aliases = r.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        haystack = _norm(name + " " + " ".join(str(a) for a in aliases))

        score = 0
        if _norm(name) == q:
            score = 1000
        elif q in haystack:
            score = 100
        else:
            words = [w for w in q.split(" ") if len(w) >= 2]
            if words and all(w in haystack for w in words):
                score = 50 + len(words)

        if score:
            results.append((score, r))

    results.sort(key=lambda x: (-x[0], _norm(x[1].get("name", ""))))
    return [r for _, r in results]
