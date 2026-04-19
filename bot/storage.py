from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from bot.config import (
    ALLOWED_USERS_EXAMPLE_SOURCE,
    ALLOWED_USERS_PATH,
    DATA_DIR,
    RECIPES_PATH,
    SESSIONS_PATH,
)

_file_lock = asyncio.Lock()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ALLOWED_USERS_PATH.exists() and ALLOWED_USERS_EXAMPLE_SOURCE.is_file():
        shutil.copy(ALLOWED_USERS_EXAMPLE_SOURCE, ALLOWED_USERS_PATH)


async def _atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(data)
    tmp.replace(path)


async def load_allowed_users() -> list[dict[str, Any]]:
    ensure_data_dir()
    if not ALLOWED_USERS_PATH.exists():
        return []
    async with aiofiles.open(ALLOWED_USERS_PATH, encoding="utf-8") as f:
        raw = await f.read()
    data = json.loads(raw)
    return list(data.get("users", []))


def user_allowed(user_id: int, username: str | None, rules: list[dict[str, Any]]) -> bool:
    for entry in rules:
        uid = entry.get("user_id")
        if uid is not None and int(uid) == int(user_id):
            return True
        un = entry.get("username")
        if un and username:
            a = str(un).lstrip("@").lower()
            b = username.lstrip("@").lower()
            if a == b:
                return True
    return False


async def load_sessions() -> dict[str, dict[str, Any]]:
    ensure_data_dir()
    if not SESSIONS_PATH.exists():
        return {}
    async with aiofiles.open(SESSIONS_PATH, encoding="utf-8") as f:
        raw = await f.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return dict(data.get("sessions", {}))


async def save_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    ensure_data_dir()
    payload = json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2)
    async with _file_lock:
        await _atomic_write(SESSIONS_PATH, payload)


def default_session() -> dict[str, Any]:
    return {
        "flow": "idle",
        "step": 0,
        "pending_switch": None,
        "opening": [],
        "closing_photos": [],
        "closing_texts": [],
        "line_photos": [],
        "line_rating": None,
        "tech_matches": [],
        "invoices": {},
        "invoice_photos": [],
        "move": {},
        "write_off": {},
        "write_off_photo": None,
    }


async def load_recipes() -> list[dict[str, Any]]:
    ensure_data_dir()
    if not RECIPES_PATH.exists():
        return []
    async with aiofiles.open(RECIPES_PATH, encoding="utf-8") as f:
        raw = await f.read()
    data = json.loads(raw)
    return list(data.get("recipes", []))
