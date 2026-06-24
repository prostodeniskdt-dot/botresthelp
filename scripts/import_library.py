"""Импорт библиотеки из JSON в data/library.json."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import LIBRARY_PATH, LIBRARY_SEED_PATH
from bot.library_data import import_library_from_path


async def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else LIBRARY_SEED_PATH
    if not source.is_file():
        raise SystemExit(f"Файл не найден: {source}")
    count, name = await import_library_from_path(source)
    print(f"Imported {count} items -> {LIBRARY_PATH} ({name})")


if __name__ == "__main__":
    asyncio.run(main())
