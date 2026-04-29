from __future__ import annotations

import asyncio
import json
import logging
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
    SESSIONS_FLUSH_DELAY_S,
)

logger = logging.getLogger(__name__)

_file_lock = asyncio.Lock()
_sessions_load_lock = asyncio.Lock()
_sessions_cache: dict[str, dict[str, Any]] | None = None
_session_locks: dict[str, asyncio.Lock] = {}
_allowed_users_cache: tuple[float | None, list[dict[str, Any]]] | None = None
_recipes_cache: tuple[float | None, list[dict[str, Any]]] | None = None
_sessions_dirty = False
_flush_task: asyncio.Task[None] | None = None
_flush_delay_s = float(SESSIONS_FLUSH_DELAY_S)


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
    global _allowed_users_cache

    ensure_data_dir()
    if not ALLOWED_USERS_PATH.exists():
        _allowed_users_cache = (None, [])
        return []
    mtime = ALLOWED_USERS_PATH.stat().st_mtime
    if _allowed_users_cache and _allowed_users_cache[0] == mtime:
        return _allowed_users_cache[1]
    async with aiofiles.open(ALLOWED_USERS_PATH, encoding="utf-8") as f:
        raw = await f.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("allowed_users.json повреждён, whitelist временно пуст")
        _allowed_users_cache = (mtime, [])
        return []
    users = list(data.get("users", []))
    _allowed_users_cache = (mtime, users)
    return users


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
    global _sessions_cache

    if _sessions_cache is not None:
        return _sessions_cache

    async with _sessions_load_lock:
        if _sessions_cache is not None:
            return _sessions_cache
        ensure_data_dir()
        if not SESSIONS_PATH.exists():
            _sessions_cache = {}
            return _sessions_cache
        async with aiofiles.open(SESSIONS_PATH, encoding="utf-8") as f:
            raw = await f.read()
        if not raw.strip():
            _sessions_cache = {}
            return _sessions_cache
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            backup = SESSIONS_PATH.with_suffix(SESSIONS_PATH.suffix + ".broken")
            logger.exception("sessions.json повреждён, сохраняю копию в %s", backup)
            SESSIONS_PATH.replace(backup)
            _sessions_cache = {}
            return _sessions_cache
        _sessions_cache = dict(data.get("sessions", {}))
        return _sessions_cache


async def save_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    global _sessions_cache

    ensure_data_dir()
    async with _file_lock:
        _sessions_cache = sessions
        payload = json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2)
        await _atomic_write(SESSIONS_PATH, payload)


def mark_sessions_dirty() -> None:
    global _sessions_dirty, _flush_task

    _sessions_dirty = True
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_sessions_later())


async def _flush_sessions_later() -> None:
    await asyncio.sleep(_flush_delay_s)
    await flush_sessions()


async def flush_sessions() -> None:
    global _sessions_dirty, _flush_task

    if not _sessions_dirty:
        return
    sessions = await load_sessions()
    async with _file_lock:
        if not _sessions_dirty:
            return
        ensure_data_dir()
        payload = json.dumps({"sessions": sessions}, ensure_ascii=False, indent=2)
        await _atomic_write(SESSIONS_PATH, payload)
        _sessions_dirty = False
    _flush_task = None


def session_lock(key: str) -> asyncio.Lock:
    lock = _session_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[key] = lock
    return lock


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
    global _recipes_cache

    ensure_data_dir()
    if not RECIPES_PATH.exists():
        _recipes_cache = (None, [])
        return []
    mtime = RECIPES_PATH.stat().st_mtime
    if _recipes_cache and _recipes_cache[0] == mtime:
        return _recipes_cache[1]
    async with aiofiles.open(RECIPES_PATH, encoding="utf-8") as f:
        raw = await f.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("recipes.json повреждён, поиск техкарт временно пуст")
        _recipes_cache = (mtime, [])
        return []
    recipes = list(data.get("recipes", []))
    _recipes_cache = (mtime, recipes)
    return recipes
