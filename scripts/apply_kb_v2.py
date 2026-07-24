"""Импорт ttk_seed_data_v2.json и library_seed_data_v2.json без внешних зависимостей."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Импортируем только чистые helper'ы: ttk_data тянет aiofiles, поэтому дублируем merge здесь
# через уже вынесенные sync-функции после лёгкого monkeypatch.

DATA_DIR = ROOT / "data"
TTK_PATH = DATA_DIR / "ttk.json"
LIBRARY_PATH = DATA_DIR / "library.json"
TTK_SEED = ROOT / "ttk_seed_data_v2.json"
LIBRARY_SEED = ROOT / "library_seed_data_v2.json"


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _backup(path: Path, prefix: str) -> Path | None:
    if not path.exists():
        return None
    backups = DATA_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dest = backups / f"{prefix}_{stamp}.json"
    shutil.copy(path, dest)
    return dest


def normalize_ttk_categories(categories: list[dict]) -> list[dict]:
    normalized = []
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


def merge_ttk(existing: dict | None, seed: dict) -> tuple[dict, dict]:
    existing = existing or {}
    seed_cats = normalize_ttk_categories(list(seed.get("categories") or []))
    existing_items = {
        str(item.get("id")): dict(item)
        for item in (existing.get("items") or [])
        if item.get("id")
    }
    seed_ids: set[str] = set()
    merged_items: dict[str, dict] = {}
    created = updated = archived = 0
    empty_ingredients: list[str] = []

    for raw_item in seed.get("items") or []:
        item = dict(raw_item)
        for key in ("id", "category_id", "category", "title", "ingredients"):
            if key not in item:
                raise ValueError(f"У позиции {item.get('id')!r} нет поля {key}")
        item_id = str(item["id"])
        seed_ids.add(item_id)
        item["archived"] = False
        if item_id in existing_items:
            updated += 1
        else:
            created += 1
        if not item.get("ingredients"):
            empty_ingredients.append(item_id)
        merged_items[item_id] = item

    for item_id, old_item in existing_items.items():
        if item_id in seed_ids:
            continue
        archived_item = dict(old_item)
        if not archived_item.get("archived"):
            archived_item["archived"] = True
            archived += 1
        merged_items[item_id] = archived_item

    existing_categories = {
        str(cat.get("id")): dict(cat) for cat in (existing.get("categories") or []) if cat.get("id")
    }
    merged_categories = []
    cats_created = cats_updated = 0
    for cat in seed_cats:
        cat_id = str(cat.get("id") or "")
        if not cat_id:
            continue
        if cat_id in existing_categories:
            cats_updated += 1
        else:
            cats_created += 1
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
                "categories_created": cats_created,
                "categories_updated": cats_updated,
                "items_created": created,
                "items_updated": updated,
                "items_archived": archived,
                "empty_ingredients": empty_ingredients,
            },
        },
        "categories": merged_categories,
        "items": list(merged_items.values()),
    }
    stats = {
        "created": created,
        "updated": updated,
        "archived": archived,
        "empty_ingredients": len(empty_ingredients),
        "active": created + updated,
    }
    return payload, stats


def _composition_to_text(value) -> str:
    if isinstance(value, list):
        lines = []
        for entry in value:
            if isinstance(entry, dict):
                amount = str(entry.get("amount") or "").strip()
                unit = str(entry.get("unit") or "").strip()
                name = str(entry.get("name") or "").strip()
                qty = " ".join(part for part in (amount, unit) if part).strip()
                line = f"{qty} — {name}".strip(" —") if qty or name else ""
                if line:
                    lines.append(line)
            else:
                text = str(entry).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)
    if value is None:
        return ""
    return str(value).strip()


def _set_field(fields: dict, key: str, value) -> None:
    if value is None:
        return
    text = _composition_to_text(value) if isinstance(value, list) else str(value).strip()
    if text and key not in fields:
        fields[key] = text


def normalize_library_item(raw: dict) -> dict:
    item = dict(raw)
    fields = dict(item.get("fields") or {})
    section = str(item.get("section_code") or "")

    if "Состав" in fields:
        fields["Состав"] = _composition_to_text(fields.get("Состав"))
    if isinstance(fields.get("Примечания"), list):
        fields["Примечания"] = "; ".join(str(x).strip() for x in fields["Примечания"] if str(x).strip())

    _set_field(fields, "Готовая фраза продажи", item.get("sales_phrase"))
    _set_field(fields, "Красивое описание для гостя", item.get("guest_description"))
    _set_field(fields, "Честное предупреждение", item.get("warning"))
    _set_field(fields, "Вопрос", item.get("question"))
    _set_field(fields, "Ответ", item.get("answer"))
    _set_field(fields, "Зацепка для аттестации", item.get("training_hook"))
    _set_field(fields, "Источник", item.get("source_url") or item.get("source_menu") or item.get("source"))

    if section == "wine":
        _set_field(fields, "Страна", item.get("country"))
        _set_field(fields, "Регион/аппелласьон", item.get("region"))
        _set_field(fields, "Город/местность", item.get("locality"))
        _set_field(fields, "Сорт(а)", item.get("grapes"))
        _set_field(fields, "Стиль", item.get("style"))
        _set_field(fields, "Тело/кислотность/танин", item.get("structure"))
        _set_field(fields, "Ароматика", item.get("aroma"))
        _set_field(fields, "Pairing", item.get("pairing"))
        _set_field(fields, "История и происхождение", item.get("origin_story"))
        _set_field(fields, "Когда предлагать", item.get("when_to_offer"))
        if not item.get("format_or_serving"):
            item["format_or_serving"] = str(item.get("format") or "").strip()
    elif section == "spirits":
        _set_field(fields, "Страна/регион", item.get("country_region"))
        _set_field(fields, "Сырье/база", item.get("base"))
        _set_field(fields, "Стиль/выдержка", item.get("style_aging"))
        _set_field(fields, "Вкус", item.get("taste"))
        _set_field(fields, "Подача", item.get("best_service") or item.get("serving_style"))
        _set_field(fields, "История и технология", item.get("origin_story"))
        _set_field(fields, "Кому предложить", item.get("who_to_offer"))
        if not item.get("format_or_serving"):
            item["format_or_serving"] = str(item.get("serving") or "").strip()
    else:
        if fields.get("Состав") and "Ключевой состав" not in fields:
            fields["Ключевой состав"] = fields["Состав"]
        if fields.get("Состав") and section == "infusions" and "Ключевой состав / TTK" not in fields:
            fields["Ключевой состав / TTK"] = fields["Состав"]
        if fields.get("Состав") and section == "prep" and "Ключевые ингредиенты" not in fields:
            fields["Ключевые ингредиенты"] = fields["Состав"]
        ice = str(fields.get("Лёд") or "").strip()
        garnish = str(fields.get("Украшение") or "").strip()
        if (ice or garnish) and "Лед/гарнир" not in fields:
            fields["Лед/гарнир"] = " / ".join(part for part in (ice, garnish) if part)

    item["fields"] = fields
    if not item.get("price"):
        price = str(fields.get("Цена") or "").strip()
        if price:
            item["price"] = price
    if not item.get("format_or_serving"):
        fmt = str(fields.get("Объем") or fields.get("Порция") or "").strip()
        if fmt:
            item["format_or_serving"] = fmt
    return item


def normalize_library(data: dict) -> dict:
    raw_items = data.get("library_items")
    if not isinstance(raw_items, list):
        raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("В library seed нет library_items/items")
    items = [normalize_library_item(item) for item in raw_items if isinstance(item, dict)]
    payload = dict(data)
    payload["library_items"] = items
    payload["meta"] = {
        **dict(data.get("meta") or {}),
        "schema_version": data.get("schema_version"),
        "generated_at": data.get("generated_at"),
        "statistics": data.get("statistics") or {},
        "sources": data.get("sources") or [],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    return payload


def main() -> None:
    if not TTK_SEED.is_file():
        raise SystemExit(f"Не найден {TTK_SEED}")
    if not LIBRARY_SEED.is_file():
        raise SystemExit(f"Не найден {LIBRARY_SEED}")

    ttk_backup = _backup(TTK_PATH, "ttk")
    lib_backup = _backup(LIBRARY_PATH, "library")
    print(f"backup ttk={ttk_backup}")
    print(f"backup library={lib_backup}")

    existing = _read(TTK_PATH) if TTK_PATH.exists() else None
    seed = _read(TTK_SEED)
    ttk_payload, ttk_stats = merge_ttk(existing, seed)
    _write(TTK_PATH, ttk_payload)
    print(
        "TTK:",
        f"active={ttk_stats['active']}",
        f"created={ttk_stats['created']}",
        f"updated={ttk_stats['updated']}",
        f"archived={ttk_stats['archived']}",
        f"empty={ttk_stats['empty_ingredients']}",
    )

    lib_seed = _read(LIBRARY_SEED)
    lib_payload = normalize_library(lib_seed)
    _write(LIBRARY_PATH, lib_payload)
    print(f"Library: items={len(lib_payload['library_items'])}")

    # Быстрая проверка ожидаемых чисел
    active = [i for i in ttk_payload["items"] if not i.get("archived")]
    assert len(active) == 78, len(active)
    assert len(lib_payload["library_items"]) == 250, len(lib_payload["library_items"])
    print("OK: 78 TTK + 250 library")


if __name__ == "__main__":
    main()
