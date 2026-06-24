"""Импорт ТТК из JSON в data/ttk.json с архивацией старых позиций."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import TTK_PATH, TTK_SEED_PATH
from bot.ttk_data import import_ttk_from_path


async def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else TTK_SEED_PATH
    if not source.is_file():
        raise SystemExit(f"Файл не найден: {source}")
    stats, name = await import_ttk_from_path(source)
    active = stats.items_created + stats.items_updated
    print(
        f"Imported -> {TTK_PATH} ({name}); "
        f"created={stats.items_created} updated={stats.items_updated} "
        f"archived={stats.items_archived} empty_ingredients={len(stats.empty_ingredients)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
