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
    "чаи, лимонады, настойки и заготовки."
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
    items_by_index: dict[int, dict[str, Any]] = field(default_factory=dict)
    item_index_by_id: dict[str, int] = field(default_factory=dict)
    category_index_by_id: dict[str, int] = field(default_factory=dict)
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

    def category_id_at(self, index: int) -> str:
        if 0 <= index < len(self.categories):
            return str(self.categories[index].get("id") or "")
        return ""

    def category_idx(self, category_id: str) -> int:
        return self.category_index_by_id.get(category_id, 0)

    def items_in_category(self, category_id: str) -> list[dict[str, Any]]:
        return self.items_by_category.get(category_id, [])

    def item_at(self, index: int) -> dict[str, Any] | None:
        return self.items_by_index.get(index)

    def item_idx(self, item_id: str) -> int | None:
        idx = self.item_index_by_id.get(item_id)
        return idx if idx is not None else None


_store_cache: tuple[float | None, TtkStore | None] = (None, None)


def _is_active(item: dict[str, Any]) -> bool:
    return not item.get("archived")


def _category_is_visible(cat: dict[str, Any]) -> bool:
    if cat.get("active") is False:
        return False
    status = str(cat.get("status") or "").strip().lower()
    if status in {"empty", "empty_source_sheet", "hidden"}:
        return False
    count = cat.get("items_count")
    if count is None:
        count = cat.get("item_count")
    if count is not None and int(count) <= 0:
        return False
    return True


def normalize_ttk_categories(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Приводит категории schema 2.x к полям, которые ожидает бот."""
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(categories):
        cat = dict(raw)
        name = str(cat.get("name") or "").strip()
        emoji = str(cat.get("emoji") or "").strip()
        title = str(cat.get("title") or "").strip()
        if not title and name:
            title = f"{emoji} {name}".strip() if emoji else name
        cat["title"] = title or str(cat.get("id") or f"category_{idx}")
        if "items_count" not in cat and "item_count" in cat:
            cat["items_count"] = int(cat.get("item_count") or 0)
        if "sort_order" not in cat:
            cat["sort_order"] = idx + 1
        normalized.append(cat)
    return normalized


def normalize_ttk_seed(seed: dict[str, Any]) -> dict[str, Any]:
    data = dict(seed)
    data["categories"] = normalize_ttk_categories(list(seed.get("categories") or []))
    return data


def _build_store(data: dict[str, Any]) -> TtkStore:
    store = TtkStore()
    store.meta = dict(data.get("meta") or {})
    if data.get("source"):
        store.meta["source"] = data.get("source")
    if data.get("statistics"):
        store.meta["statistics"] = data.get("statistics")
    categories = normalize_ttk_categories(list(data.get("categories") or []))
    store.categories = sorted(
        [cat for cat in categories if _category_is_visible(cat)],
        key=lambda c: int(c.get("sort_order") or 999),
    )
    store.meta["all_categories"] = categories
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
    store.category_index_by_id = {
        str(cat.get("id") or ""): idx for idx, cat in enumerate(store.categories)
    }
    ordered_items = sorted(
        store.active_items,
        key=lambda x: (str(x.get("category_id") or ""), str(x.get("title") or "").lower()),
    )
    store.items_by_index = {}
    store.item_index_by_id = {}
    for idx, item in enumerate(ordered_items):
        item_id = str(item.get("id") or "")
        store.items_by_index[idx] = item
        store.item_index_by_id[item_id] = idx
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
    seed = normalize_ttk_seed(seed)
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
        "statistics": seed.get("statistics") or existing.get("statistics") or {},
        "meta": {
            **dict(existing.get("meta") or {}),
            **dict(seed.get("meta") or {}),
            "updated_at": datetime.now(UTC).isoformat(),
            "import_source": (seed.get("source") or {}).get("file")
            or (seed.get("source") or {}).get("file_name")
            or seed.get("generated_at"),
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
