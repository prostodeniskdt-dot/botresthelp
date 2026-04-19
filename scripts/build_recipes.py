"""
Сборка data/recipes.json из data/ttk_source.txt.
Запуск: python scripts/build_recipes.py
(Дубликат логики scripts/build_recipes.mjs — нужен Node для проверки: node scripts/build_recipes.mjs)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "ttk_source.txt"
OUT = ROOT / "data" / "recipes.json"

TITLE_RE = re.compile(r"^(.+?)\s+(Подача:?|Приготовление:?|Метод:?)\s*$")


def clean_name(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[ЕЕ]\s+", "", s)
    return s.strip()


def skip_body_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", s):
        return True
    if s == "[":
        return True
    if s == "Е":
        return True
    return False


def parse_ttk(text: str) -> list[dict[str, str]]:
    text = re.sub(r"--\s*\d+\s+of\s+\d+\s*--", "", text)
    lines = text.split("\n")
    recipes: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = TITLE_RE.match(line)
        if not m:
            i += 1
            continue
        if m.group(2).startswith("Метод") and re.match(r"^\d", line.strip()):
            i += 1
            continue
        name = clean_name(m.group(1))
        if not name:
            i += 1
            continue
        i += 1
        body: list[str] = []
        while i < len(lines):
            nxt = lines[i].strip()
            if TITLE_RE.match(nxt):
                mm = TITLE_RE.match(nxt)
                assert mm is not None
                if mm.group(2).startswith("Метод") and re.match(r"^\d", nxt):
                    body.append(lines[i])
                    i += 1
                    continue
                break
            if skip_body_line(lines[i]):
                i += 1
                continue
            body.append(lines[i])
            i += 1
        text_body = "\n".join(body).strip().replace("\r\n", "\n")
        if not text_body:
            continue
        if name in recipes and len(text_body) <= len(recipes[name]):
            continue
        recipes[name] = text_body

    return [{"name": k, "text": v} for k, v in sorted(recipes.items(), key=lambda x: x[0].lower())]


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Нет файла {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")
    items = parse_ttk(text)
    OUT.write_text(
        json.dumps({"recipes": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Записано {len(items)} техкарт в {OUT}")


if __name__ == "__main__":
    main()
