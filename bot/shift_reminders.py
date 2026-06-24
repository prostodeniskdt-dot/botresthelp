from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiofiles
from aiogram import Bot

from bot.config import (
    ADMIN_GROUP_CHAT_ID,
    REMINDER_LOOP_INTERVAL_S,
    REMINDER_TIMEZONE,
    SHIFT_REMINDERS_PATH,
    THREAD_GOLIST,
    THREAD_LINE,
    THREAD_OPENING,
)
from bot.reminder_copy import (
    MSG_GOLIST,
    MSG_LINE_MINUS_30,
    MSG_LINE_MINUS_5,
    MSG_LINE_START,
    MSG_OPENING_MINUS_10,
    MSG_OPENING_MINUS_30,
    MSG_OPENING_START,
    line_escalation_html,
)

logger = logging.getLogger(__name__)

TZ = ZoneInfo(REMINDER_TIMEZONE)

_lock = asyncio.Lock()

# Слоты (час, минута) MSK и ключ в state["fired"]
_OPENING_START = (11, 0)
_OPENING_M30 = (12, 30)
_OPENING_M10 = (12, 50)
_LINE_START = (15, 0)
_LINE_M30 = (15, 30)
_LINE_M5 = (15, 55)
_GOLIST_14 = (14, 0)
_GOLIST_19 = (19, 0)
_ESCALATION = (16, 0)


def _today_str(d: date) -> str:
    return d.isoformat()


def _fresh_state(day: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "day": day,
        "opening_done": False,
        "line_done": False,
        "line_responsible_user_id": None,
        "line_responsible_username": None,
        "fired": {},
    }


async def _atomic_write(path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(data)
    tmp.replace(path)


async def load_shift_state() -> dict[str, Any]:
    from bot.storage import ensure_data_dir

    ensure_data_dir()
    today = _today_str(datetime.now(TZ).date())
    if not SHIFT_REMINDERS_PATH.exists():
        return _fresh_state(today)
    async with aiofiles.open(SHIFT_REMINDERS_PATH, encoding="utf-8") as f:
        raw = await f.read()
    try:
        root = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("shift_reminders.json повреждён, сбрасываю состояние")
        return _fresh_state(today)
    st = root.get("state") or {}
    if st.get("day") != today:
        return _fresh_state(today)
    out = _fresh_state(today)
    out.update({k: st.get(k, out[k]) for k in out if k != "fired"})
    out["fired"] = dict(st.get("fired") or {})
    return out


async def save_shift_state(state: dict[str, Any]) -> None:
    from bot.storage import ensure_data_dir

    ensure_data_dir()
    async with _lock:
        payload = json.dumps({"state": state}, ensure_ascii=False, indent=2)
        await _atomic_write(SHIFT_REMINDERS_PATH, payload)


def _mention_html(user_id: int, username: str | None) -> str:
    label = f"@{username}" if username else f"id:{user_id}"
    safe = html.escape(label)
    return f'<a href="tg://user?id={int(user_id)}">{safe}</a>'


async def record_opening_completed(user_id: int, username: str | None) -> None:
    st = await load_shift_state()
    st["opening_done"] = True
    st["line_responsible_user_id"] = int(user_id)
    st["line_responsible_username"] = username
    await save_shift_state(st)
    logger.info(
        "shift_opening_done user_id=%s line_responsible_set=1",
        user_id,
    )


async def record_line_completed() -> None:
    st = await load_shift_state()
    st["line_done"] = True
    await save_shift_state(st)
    logger.info("shift_line_done")


async def _send_thread(bot: Bot, thread_id: int, text: str) -> None:
    await bot.send_message(
        ADMIN_GROUP_CHAT_ID,
        text,
        parse_mode="HTML",
        message_thread_id=thread_id,
    )


def _should_fire(fired: dict[str, Any], key: str) -> bool:
    return not fired.get(key)


async def _mark_fired(state: dict[str, Any], key: str) -> None:
    state.setdefault("fired", {})[key] = True
    await save_shift_state(state)


async def run_reminder_tick(bot: Bot) -> None:
    now = datetime.now(TZ)
    day = _today_str(now.date())
    t = now.time()

    def slot_match(slot: tuple[int, int]) -> bool:
        return t.hour == slot[0] and t.minute == slot[1]

    try:
        state = await load_shift_state()
        if state.get("day") != day:
            state = _fresh_state(day)
            await save_shift_state(state)
            state = await load_shift_state()

        fired = state.setdefault("fired", {})

        if slot_match(_OPENING_START) and _should_fire(fired, "opening_start"):
            if not state.get("opening_done"):
                await _send_thread(bot, THREAD_OPENING, MSG_OPENING_START)
            await _mark_fired(state, "opening_start")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_OPENING_M30) and _should_fire(fired, "opening_m30"):
            if not state.get("opening_done"):
                await _send_thread(bot, THREAD_OPENING, MSG_OPENING_MINUS_30)
            await _mark_fired(state, "opening_m30")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_OPENING_M10) and _should_fire(fired, "opening_m10"):
            if not state.get("opening_done"):
                await _send_thread(bot, THREAD_OPENING, MSG_OPENING_MINUS_10)
            await _mark_fired(state, "opening_m10")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_LINE_START) and _should_fire(fired, "line_start"):
            if not state.get("line_done"):
                await _send_thread(bot, THREAD_LINE, MSG_LINE_START)
            await _mark_fired(state, "line_start")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})
        uid = state.get("line_responsible_user_id")
        uname = state.get("line_responsible_username")

        if slot_match(_LINE_M30) and _should_fire(fired, "line_m30"):
            if not state.get("line_done"):
                body = MSG_LINE_MINUS_30
                if uid is not None:
                    body = (
                        f"{_mention_html(int(uid), uname if isinstance(uname, str) else None)}\n\n"
                        f"{body}"
                    )
                await _send_thread(bot, THREAD_LINE, body)
            await _mark_fired(state, "line_m30")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})
        uid = state.get("line_responsible_user_id")
        uname = state.get("line_responsible_username")

        if slot_match(_LINE_M5) and _should_fire(fired, "line_m5"):
            if not state.get("line_done"):
                body = MSG_LINE_MINUS_5
                if uid is not None:
                    body = (
                        f"{_mention_html(int(uid), uname if isinstance(uname, str) else None)}\n\n"
                        f"{body}"
                    )
                await _send_thread(bot, THREAD_LINE, body)
            await _mark_fired(state, "line_m5")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_GOLIST_14) and _should_fire(fired, "golist_14"):
            await _send_thread(bot, THREAD_GOLIST, MSG_GOLIST)
            await _mark_fired(state, "golist_14")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_GOLIST_19) and _should_fire(fired, "golist_19"):
            await _send_thread(bot, THREAD_GOLIST, MSG_GOLIST)
            await _mark_fired(state, "golist_19")

        state = await load_shift_state()
        fired = state.setdefault("fired", {})

        if slot_match(_ESCALATION) and _should_fire(fired, "line_escalation"):
            opening_done_now = bool(state.get("opening_done"))
            line_done_now = bool(state.get("line_done"))
            rid = state.get("line_responsible_user_id")
            if opening_done_now and not line_done_now and rid is not None:
                men = _mention_html(
                    int(rid),
                    state.get("line_responsible_username")
                    if isinstance(state.get("line_responsible_username"), str)
                    else None,
                )
                await _send_thread(bot, THREAD_LINE, line_escalation_html(men))
                logger.info("reminder_escalation line_not_done responsible_id=%s", rid)
            await _mark_fired(state, "line_escalation")
    except Exception:
        logger.exception("run_reminder_tick send failed")


async def reminder_loop(bot: Bot) -> None:
    while True:
        try:
            await asyncio.sleep(REMINDER_LOOP_INTERVAL_S)
            await run_reminder_tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reminder_loop tick failed")
