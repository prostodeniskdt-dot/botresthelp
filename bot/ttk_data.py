from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles

from bot.config import DATA_DIR, RECIPES_PATH, TTK_PATH, TTK_SEED_PATH

logger = logging.getLogger(__name__)

TTK_HOME_TEXT = (
    "📋 ТТК бара. Выберите раздел: авторские и классические коктейли, "
    "чаи, лимонады, сезон, настойки, заготовки, чай и кофе."
)

SEARCH_EMPTY_TEXT = (
    "Ничего не нашёл. Попробуйте короче: название, ингредиент, метод, "
    "бокал или категорию. Например: «негрони», «базилик», «кордиал», «джин»."
)


@dataclass
class ImportStats:
    categories_created: int = 0
    categories_updated: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_archived: int = 0
    empty_ingredients: list[str] = field(default_factory=list)


@dataclass
class TtkStore:
    categories: list[dict[str, Any]] = field(default_factory=list)
    items_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    items_by_category: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def active_items(self) -> list[dict[str, Any]]:
        return [item for item in self.items_by_id.values() if not item.get("archived")]

    @property
    def archived_count(self) -> int:
        return sum(1 for item in self.items_by_id.values() if item.get("archived"))

    def category_title(self, category_id: str) -> str:
        for cat in self.categories:
            if str(cat.get("id")) == category_id:
                return str(cat.get("title") or category_id)
        return category_id

    def items_in_category(self, category_id: str) -> list[dict[str, Any]]:
        return self.items_by_category.get(category_id, [])


_store_cache: tuple[float | None, TtkStore | None] = (None, None)


def _is_active(item: dict[str, Any]) -> bool:
    return not item.get("archived")


def _build_store(data: dict[str, Any]) -> TtkStore:
    store = TtkStore()
    store.meta = dict(data.get("meta") or {})
    store.categories = sorted(
        list(data.get("categories") or []),
        key=lambda c: int(c.get("sort_order") or 999),
    )
    for item in data.get("items") or []:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        store.items_by_id[item_id] = item
        if not _is_active(item):
            continue
        cat_id = str(item.get("category_id") or "")
        store.items_by_category.setdefault(cat_id, []).append(item)
    for cat_items in store.items_by_category.values():
        cat_items.sort(key=lambda x: str(x.get("title") or "").lower())
    return store


def ensure_ttk_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TTK_PATH.exists():
        return
    if TTK_SEED_PATH.is_file():
        shutil.copy(TTK_SEED_PATH, TTK_PATH)
        logger.info("ttk_seed_copied path=%s", TTK_PATH)
        return
    logger.warning("ttk file missing and no seed at %s", TTK_SEED_PATH)


def _backup_path() -> Path:
    backups = DATA_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return backups / f"ttk_{stamp}.json"


async def _read_json(path: Path) -> dict[str, Any]:
    async with aiofiles.open(path, encoding="utf-8") as f:
        raw = await f.read()
    return json.loads(raw)


async def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def _validate_item(item: dict[str, Any]) -> None:
    for key in ("id", "category_id", "category", "title", "ingredients"):
        if key not in item:
            raise ValueError(f"У позиции {item.get('id')!r} нет поля {key}")


def merge_ttk_data(existing: dict[str, Any] | None, seed: dict[str, Any]) -> tuple[dict[str, Any], ImportStats]:
    stats = ImportStats()
    existing = existing or {}
    existing_items = {
        str(item.get("id")): dict(item)
        for item in (existing.get("items") or [])
        if item.get("id")
    }
    seed_ids = set()
    merged_items: dict[str, dict[str, Any]] = {}

    for raw_item in seed.get("items") or []:
        item = dict(raw_item)
        _validate_item(item)
        item_id = str(item["id"])
        seed_ids.add(item_id)
        item["archived"] = False
        if item_id in existing_items:
            stats.items_updated += 1
        else:
            stats.items_created += 1
        if not item.get("ingredients"):
            stats.empty_ingredients.append(item_id)
        merged_items[item_id] = item

    for item_id, old_item in existing_items.items():
        if item_id in seed_ids:
            continue
        archived = dict(old_item)
        if not archived.get("archived"):
            archived["archived"] = True
            stats.items_archived += 1
        merged_items[item_id] = archived

    existing_categories = {
        str(cat.get("id")): dict(cat) for cat in (existing.get("categories") or []) if cat.get("id")
    }
    merged_categories: list[dict[str, Any]] = []
    for cat in seed.get("categories") or []:
        cat_id = str(cat.get("id") or "")
        if not cat_id:
            continue
        if cat_id in existing_categories:
            stats.categories_updated += 1
        else:
            stats.categories_created += 1
        merged_categories.append(dict(cat))

    payload = {
        "schema_version": seed.get("schema_version") or existing.get("schema_version") or "1.0",
        "source": seed.get("source") or existing.get("source") or {},
        "meta": {
            **dict(existing.get("meta") or {}),
            **dict(seed.get("meta") or {}),
            "updated_at": datetime.now(UTC).isoformat(),
            "import_stats": {
                "categories_created": stats.categories_created,
                "categories_updated": stats.categories_updated,
                "items_created": stats.items_created,
                "items_updated": stats.items_updated,
                "items_archived": stats.items_archived,
                "empty_ingredients": stats.empty_ingredients,
            },
        },
        "categories": merged_categories,
        "items": list(merged_items.values()),
    }
    return payload, stats


async def load_ttk_store(*, force: bool = False) -> TtkStore:
    global _store_cache

    ensure_ttk_file()
    if not TTK_PATH.exists():
        store = TtkStore()
        _store_cache = (None, store)
        return store

    mtime = TTK_PATH.stat().st_mtime
    if not force and _store_cache[1] is not None and _store_cache[0] == mtime:
        return _store_cache[1]

    try:
        data = await _read_json(TTK_PATH)
    except json.JSONDecodeError:
        logger.exception("ttk.json повреждён")
        store = TtkStore()
        _store_cache = (mtime, store)
        return store

    store = _build_store(data)
    _store_cache = (mtime, store)
    logger.info(
        "ttk_loaded categories=%s active_items=%s archived=%s",
        len(store.categories),
        len(store.active_items),
        store.archived_count,
    )
    return store


def invalidate_ttk_cache() -> None:
    global _store_cache
    _store_cache = (None, None)


async def import_ttk_from_path(source: Path, *, backup: bool = True) -> tuple[ImportStats, str]:
    seed = await _read_json(source)
    if not isinstance(seed.get("items"), list):
        raise ValueError("В JSON нет массива items")

    ensure_ttk_file()
    existing: dict[str, Any] | None = None
    if TTK_PATH.exists():
        existing = await _read_json(TTK_PATH)
        if backup:
            backup_file = _backup_path()
            await _write_json(backup_file, existing)
            logger.info("ttk_backup_saved path=%s", backup_file)
            if RECIPES_PATH.exists():
                recipes_backup = DATA_DIR / "backups" / f"recipes_legacy_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy(RECIPES_PATH, recipes_backup)
                logger.info("recipes_legacy_backup_saved path=%s", recipes_backup)

    payload, stats = merge_ttk_data(existing, seed)
    await _write_json(TTK_PATH, payload)
    invalidate_ttk_cache()
    await load_ttk_store(force=True)

    logger.info(
        "ttk_import_done created=%s updated=%s archived=%s empty_ingredients=%s",
        stats.items_created,
        stats.items_updated,
        stats.items_archived,
        len(stats.empty_ingredients),
    )
    return stats, TTK_PATH.name
