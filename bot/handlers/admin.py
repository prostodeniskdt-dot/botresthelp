from __future__ import annotations

import html
import json
import logging
from typing import Any

import aiofiles
from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from bot.config import ALLOWED_USERS_PATH
from bot.storage import ensure_data_dir, invalidate_allowed_users_cache

router = Router()
logger = logging.getLogger(__name__)


class IsBotAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        from bot.config import ADMIN_USER_IDS

        u = message.from_user
        return u is not None and u.id in ADMIN_USER_IDS


async def _load_users_raw() -> dict[str, Any]:
    ensure_data_dir()
    if not ALLOWED_USERS_PATH.exists():
        return {"users": []}
    async with aiofiles.open(ALLOWED_USERS_PATH, encoding="utf-8") as f:
        raw = await f.read()
    return json.loads(raw)


async def save_allowed_users(users: list[dict[str, Any]]) -> None:
    path = ALLOWED_USERS_PATH
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps({"users": users}, ensure_ascii=False, indent=2)
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(payload)
    tmp.replace(path)
    invalidate_allowed_users_cache()
    logger.info("allowed_users_saved count=%s", len(users))


def _uname_key(s: str) -> str:
    return s.lstrip("@").strip().lower()


@router.message(Command("staff_list"), IsBotAdmin())
async def staff_list(message: Message) -> None:
    try:
        data = await _load_users_raw()
    except Exception:
        logger.exception("staff_list read failed")
        await message.answer("Не удалось прочитать allowed_users.json 😕")
        return
    users = data.get("users") or []
    if not users:
        await message.answer("Список пуст 📋")
        return
    lines = []
    for e in users:
        uid = e.get("user_id")
        un = e.get("username")
        nm = e.get("name") or ""
        parts = []
        if uid is not None:
            parts.append(f"id:<code>{uid}</code>")
        if un:
            parts.append(f"@{html.escape(str(un).lstrip('@'))}")
        if nm:
            parts.append(html.escape(str(nm)))
        lines.append(" — ".join(parts) if parts else html.escape(json.dumps(e, ensure_ascii=False)))
    await message.answer("👥 <b>Whitelist</b>\n" + "\n".join(lines), parse_mode="HTML")


@router.message(Command("staff_add"), IsBotAdmin())
async def staff_add(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        await message.answer(
            "Использование: <code>/staff_add 123456789</code> или "
            "<code>/staff_add @username</code> или оба через пробел 📌",
            parse_mode="HTML",
        )
        return
    tokens = arg.split()
    new_uid: int | None = None
    new_username: str | None = None
    for t in tokens:
        tn = t.strip()
        if tn.startswith("@"):
            new_username = tn[1:]
        elif tn.lstrip("-").isdigit():
            new_uid = int(tn)
        elif not tn.lstrip("-").isdigit():
            new_username = tn
    if new_uid is None and not new_username:
        await message.answer("Укажите числовой user_id или @username ⚠️")
        return
    try:
        data = await _load_users_raw()
    except Exception:
        logger.exception("staff_add read failed")
        await message.answer("Не удалось прочитать файл 😕")
        return
    users: list[dict[str, Any]] = list(data.get("users") or [])
    entry: dict[str, Any] = {}
    if new_uid is not None:
        entry["user_id"] = new_uid
    if new_username:
        entry["username"] = new_username

    def _match(existing: dict[str, Any]) -> bool:
        ex_uid = existing.get("user_id")
        ex_un = existing.get("username")
        if new_uid is not None and ex_uid is not None and int(ex_uid) == int(new_uid):
            return True
        if new_username and ex_un:
            return _uname_key(str(ex_un)) == _uname_key(new_username)
        return False

    if any(_match(x) for x in users):
        await message.answer("Такая запись уже есть ✅")
        return
    users.append(entry)
    try:
        await save_allowed_users(users)
    except Exception:
        logger.exception("staff_add save failed")
        await message.answer("Не удалось записать файл 😕")
        return
    await message.answer(f"Добавлено: <code>{html.escape(json.dumps(entry, ensure_ascii=False))}</code>", parse_mode="HTML")


@router.message(Command("staff_remove"), IsBotAdmin())
async def staff_remove(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        await message.answer("Использование: <code>/staff_remove 123456789</code> или <code>/staff_remove @nick</code> 🗑️", parse_mode="HTML")
        return
    targ = arg.split()[0]
    try:
        data = await _load_users_raw()
    except Exception:
        logger.exception("staff_remove read failed")
        await message.answer("Не удалось прочитать файл 😕")
        return
    users = list(data.get("users") or [])
    if targ.startswith("@"):
        key = _uname_key(targ)
        users_new = [
            x
            for x in users
            if not (
                x.get("username") and _uname_key(str(x.get("username"))) == key
            )
        ]
    elif targ.removeprefix("-").isdigit():
        rid = int(targ)
        users_new = [x for x in users if not (x.get("user_id") is not None and int(x["user_id"]) == rid)]
    else:
        await message.answer("Нужен @username или числовой id ⚠️")
        return
    if len(users_new) == len(users):
        await message.answer("Такого в списке не нашлось 🤷")
        return
    try:
        await save_allowed_users(users_new)
    except Exception:
        logger.exception("staff_remove save failed")
        await message.answer("Не удалось записать файл 😕")
        return
    await message.answer("Запись удалена ✅")
