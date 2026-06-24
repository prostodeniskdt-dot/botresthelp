from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles

from bot.config import DATA_DIR, LIBRARY_PATH, LIBRARY_SEED_PATH

logger = logging.getLogger(__name__)

LIBRARY_SECTIONS: list[tuple[str, str]] = [
    ("cocktails", "🍸 Коктейли"),
    ("infusions", "🥃 Настойки/наливки"),
    ("wine", "🍷 Вино"),
    ("spirits", "🥃 Крепкий алкоголь"),
    ("beer_soft", "🍺 Пиво / ☕ Безалко"),
    ("prep", "🧪 ПФ / заготовки"),
    ("sales", "💬 Продажи"),
    ("dictionary", "📖 Словарь"),
    ("allergens", "⚠️ Аллергены"),
    ("storytelling", "🎙 Сторителлинг"),
    ("search", "🔎 Поиск по библиотеке"),
]

SECTION_LABELS = dict(LIBRARY_SECTIONS)

SUMMARY_FIELD_ORDER: dict[str, list[str]] = {
    "cocktails": [
        "Основа",
        "Ключевой состав",
        "TTK / граммовка",
        "Вкус",
        "Метод",
        "Бокал",
        "Лед/гарнир",
        "Кому предложить",
        "Готовая фраза продажи",
    ],
    "infusions": [
        "Профиль",
        "База",
        "Ключевой состав / TTK",
        "Выход",
        "Вкус",
        "Сервис / кому предложить",
        "История для гостя",
    ],
    "wine": [
        "Страна",
        "Регион/аппелласьон",
        "Сорт(а)",
        "Стиль",
        "Тело/кислотность/танин",
        "Ароматика",
        "Pairing",
        "Продажная история",
    ],
    "spirits": [
        "Категория",
        "Страна/регион",
        "Сырье/база",
        "Стиль/выдержка",
        "Вкус",
        "Подача",
        "Кому предложить",
        "Готовая фраза продажи",
    ],
    "beer_soft": [
        "Стиль/состав",
        "Вкус",
        "Подача",
        "Кому предложить",
        "Фраза гостю",
    ],
    "prep": [
        "Где используется",
        "Ключевые ингредиенты",
        "Краткий метод",
        "Выход",
        "Что дает во вкусе",
        "Что знать официанту",
    ],
    "sales": [
        "Уточняющий вопрос",
        "Что предложить",
        "Почему подходит",
        "Мягкий заход",
        "Фраза апсейла",
    ],
    "dictionary": [
        "Блок",
        "Простое объяснение",
        "Что сказать гостю/стажеру",
        "Пример",
    ],
    "allergens": [
        "Где встречается",
        "Что спросить/сказать",
        "Альтернатива",
        "Источник",
    ],
}

SALE_FIELD_KEYS = (
    "Готовая фраза продажи",
    "Готовая фраза",
    "Фраза гостю",
    "Фраза о собственной заготовке",
    "Продажная история",
    "Фраза апсейла",
    "Мягкий заход",
)

WARN_FIELD_KEYS = (
    "Честное предупреждение",
    "Аллергены/важно",
    "Риски",
    "Риск/аллерген",
    "Когда не предлагать",
)

ALLERGEN_DISCLAIMER = (
    "⚠️ Важно: если у гостя есть аллергия или медицинские ограничения, "
    "не импровизировать. Уточнить у бармена или менеджера."
)

LIBRARY_HOME_TEXT = (
    "📚 Библиотека бара. Выберите раздел: коктейли, настойки, вино, "
    "крепкий алкоголь, пиво/безалко, заготовки, продажи, словарь или аллергены."
)

SEARCH_EMPTY_TEXT = (
    "Ничего не нашёл. Попробуйте написать короче: название, вкус, "
    "ингредиент или категорию. Например: «виски», «базилик», «сульфиты», «клубника»."
)


@dataclass
class LibraryStore:
    items_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    items_by_section: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    groups_by_section: dict[str, list[str]] = field(default_factory=dict)
    items_by_section_group: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    storytelling_blocks: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def group_index(self, section_code: str, group: str) -> int:
        groups = self.groups_by_section.get(section_code, [])
        try:
            return groups.index(group)
        except ValueError:
            return 0

    def group_name(self, section_code: str, group_idx: int) -> str:
        groups = self.groups_by_section.get(section_code, [])
        if 0 <= group_idx < len(groups):
            return groups[group_idx]
        return groups[0] if groups else ""

    def items_in_group(self, section_code: str, group_idx: int) -> list[dict[str, Any]]:
        group = self.group_name(section_code, group_idx)
        return self.items_by_section_group.get((section_code, group), [])


_store_cache: tuple[float | None, LibraryStore | None] = (None, None)


def _build_store(data: dict[str, Any]) -> LibraryStore:
    store = LibraryStore()
    store.meta = dict(data.get("meta") or {})
    items = list(data.get("library_items") or [])
    for item in items:
        item_id = str(item.get("id", ""))
        if not item_id:
            continue
        store.items_by_id[item_id] = item
        section = str(item.get("section_code", ""))
        store.items_by_section.setdefault(section, []).append(item)
        group = str(item.get("group") or "")
        key = (section, group)
        store.items_by_section_group.setdefault(key, []).append(item)
        groups = store.groups_by_section.setdefault(section, [])
        if group not in groups:
            groups.append(group)

    for section_items in store.items_by_section.values():
        section_items.sort(key=lambda x: str(x.get("title", "")).lower())
    for key in store.items_by_section_group:
        store.items_by_section_group[key].sort(key=lambda x: str(x.get("title", "")).lower())

    raw_rows = data.get("raw_rows") or {}
    story_rows = raw_rows.get("13_Сторителлинг") or []
    store.storytelling_blocks = _format_storytelling(story_rows)
    return store


def _format_storytelling(rows: list[list[Any]]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for row in rows:
        cells = [str(c).strip() for c in row if str(c).strip()]
        if not cells:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if len(cells) == 1 and not current:
            current.append(f"<b>{cells[0]}</b>")
            continue
        if len(cells) >= 2 and cells[1] in {
            "Что сказать",
            "Когда использовать",
            "Для чего",
            "Хороший ответ",
        }:
            if current:
                blocks.append("\n".join(current))
            header = " | ".join(cells)
            current = [f"<b>{header}</b>"]
            continue
        if len(cells) >= 3 and cells[1] in {"Хороший ответ"}:
            current.append(f"• <b>{cells[0]}</b>: {cells[1]} — {cells[2]}")
        elif len(cells) >= 2:
            line = f"• <b>{cells[0]}</b>"
            if cells[1]:
                line += f": {cells[1]}"
            if len(cells) > 2 and cells[2]:
                line += f" — {cells[2]}"
            current.append(line)
        else:
            current.append(cells[0])
    if current:
        blocks.append("\n".join(current))
    if not blocks:
        blocks = ["🎙 Сторителлинг пока пуст."]
    return blocks


def ensure_library_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LIBRARY_PATH.exists():
        return
    if LIBRARY_SEED_PATH.is_file():
        shutil.copy(LIBRARY_SEED_PATH, LIBRARY_PATH)
        logger.info("library_seed_copied path=%s", LIBRARY_PATH)
        return
    logger.warning("library file missing and no seed at %s", LIBRARY_SEED_PATH)


async def load_library_store(*, force: bool = False) -> LibraryStore:
    global _store_cache

    ensure_library_file()
    if not LIBRARY_PATH.exists():
        _store_cache = (None, LibraryStore())
        return LibraryStore()

    mtime = LIBRARY_PATH.stat().st_mtime
    if not force and _store_cache[1] is not None and _store_cache[0] == mtime:
        return _store_cache[1]

    async with aiofiles.open(LIBRARY_PATH, encoding="utf-8") as f:
        raw = await f.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("library.json повреждён")
        store = LibraryStore()
        _store_cache = (mtime, store)
        return store

    store = _build_store(data)
    _store_cache = (mtime, store)
    logger.info("library_loaded items=%s sections=%s", len(store.items_by_id), len(store.groups_by_section))
    return store


def invalidate_library_cache() -> None:
    global _store_cache
    _store_cache = (None, None)


async def import_library_from_path(source: Path) -> tuple[int, str]:
    async with aiofiles.open(source, encoding="utf-8") as f:
        raw = await f.read()
    data = json.loads(raw)
    items = data.get("library_items")
    if not isinstance(items, list):
        raise ValueError("В JSON нет массива library_items")

    ensure_library_file()
    tmp = LIBRARY_PATH.with_suffix(LIBRARY_PATH.suffix + ".tmp")
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(LIBRARY_PATH)
    invalidate_library_cache()
    await load_library_store(force=True)
    return len(items), LIBRARY_PATH.name
