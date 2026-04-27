from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import User

from bot.config import (
    ADMIN_GROUP_CHAT_ID,
    THREAD_CLOSING,
    THREAD_INVOICES,
    THREAD_LINE,
    THREAD_MOVE,
    THREAD_OPENING,
    THREAD_WRITE_OFF,
)

MSK = ZoneInfo("Europe/Moscow")
logger = logging.getLogger(__name__)


async def _telegram_call(action: str, call: Callable[[], Awaitable[object]]) -> object:
    delay = 1.0
    for attempt in range(1, 4):
        try:
            return await call()
        except TelegramRetryAfter as e:
            wait = float(e.retry_after) + 0.5
            logger.warning("%s rate limited, retry in %.1fs", action, wait)
            await asyncio.sleep(wait)
        except TelegramNetworkError:
            if attempt == 3:
                raise
            logger.warning("%s network error, retry %s/3 in %.1fs", action, attempt, delay)
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{action} failed after retries")


def _user_line(user: User) -> str:
    parts = []
    if user.username:
        parts.append(f"@{user.username}")
    parts.append(f"id:{user.id}")
    return " ".join(parts)


async def _send_admin_message(bot: Bot, text: str, thread_id: int) -> None:
    await _telegram_call(
        "send_admin_message",
        lambda: bot.send_message(
            ADMIN_GROUP_CHAT_ID,
            text,
            parse_mode="HTML",
            message_thread_id=thread_id,
        ),
    )


async def _send_admin_photo(bot: Bot, file_id: str, caption: str, thread_id: int) -> None:
    await _telegram_call(
        "send_admin_photo",
        lambda: bot.send_photo(
            ADMIN_GROUP_CHAT_ID,
            file_id,
            caption=caption[:1024],
            message_thread_id=thread_id,
        ),
    )


async def send_opening_report(
    bot: Bot,
    user: User,
    items: list[str],
    photos: list[dict],
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    header = (
        "📋 <b>Чек-лист ОТКРЫТИЯ</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n"
    )
    await _send_admin_message(bot, header, THREAD_OPENING)

    for i, (title, ph) in enumerate(zip(items, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if not fid:
            continue
        await _send_admin_photo(bot, fid, caption, THREAD_OPENING)


async def send_closing_report(
    bot: Bot,
    user: User,
    photo_items: list[str],
    photos: list[dict],
    text_prompts: list[str],
    texts: list[str],
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    header = (
        "📋 <b>Чек-лист ЗАКРЫТИЯ</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n"
    )
    await _send_admin_message(bot, header, THREAD_CLOSING)

    for i, (title, ph) in enumerate(zip(photo_items, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if fid:
            await _send_admin_photo(bot, fid, caption, THREAD_CLOSING)

    await _send_admin_message(bot, "📝 <b>Кратко о дне</b>", THREAD_CLOSING)
    for prompt, text in zip(text_prompts, texts):
        body = f"<b>{html.escape(prompt)}</b>\n{html.escape(text)}"
        await _send_admin_message(bot, body, THREAD_CLOSING)


async def send_line_report(
    bot: Bot,
    user: User,
    questions: list[str],
    photos: list[dict],
    rating_question: str,
    rating_value: int,
    rating_label: str,
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    header = (
        "📋 <b>Лайн-чек</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n"
    )
    await _send_admin_message(bot, header, THREAD_LINE)

    for i, (title, ph) in enumerate(zip(questions, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if fid:
            await _send_admin_photo(bot, fid, caption, THREAD_LINE)

    await _send_admin_message(
        bot,
        f"⭐ <b>{rating_question}</b>\nОценка: {rating_value} ({rating_label})",
        THREAD_LINE,
    )


async def send_invoices_report(
    bot: Bot,
    user: User,
    product: str,
    supplier: str,
    date_text: str,
    photo_file_ids: list[str],
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    header = (
        "🧾 <b>Накладные</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n\n"
        f"<b>Что приехало:</b> {html.escape(product)}\n"
        f"<b>Поставщик:</b> {html.escape(supplier)}\n"
        f"<b>Дата:</b> {html.escape(date_text)}\n"
    )
    await _send_admin_message(bot, header, THREAD_INVOICES)
    captions = ["1) Наименование", "2) Печать/подпись"]
    for fid, cap in zip(photo_file_ids, captions):
        await _send_admin_photo(bot, fid, cap, THREAD_INVOICES)


async def send_move_report(
    bot: Bot,
    user: User,
    what: str,
    why: str,
    date_text: str,
    from_to: str,
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    body = (
        "📦 <b>Перемещение</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n\n"
        f"<b>Что:</b> {html.escape(what)}\n"
        f"<b>Зачем:</b> {html.escape(why)}\n"
        f"<b>Дата:</b> {html.escape(date_text)}\n"
        f"<b>Откуда / Куда:</b> {html.escape(from_to)}\n"
    )
    await _send_admin_message(bot, body, THREAD_MOVE)


async def send_write_off_report(
    bot: Bot,
    user: User,
    what: str,
    why: str,
    date_text: str,
    receipt_photo_file_id: str,
) -> None:
    now = datetime.now(MSK).strftime("%Y-%m-%d %H:%M %Z")
    body = (
        "🗑️ <b>Списание</b>\n"
        f"👤 {_user_line(user)}\n"
        f"🕐 {now}\n\n"
        f"<b>Что:</b> {html.escape(what)}\n"
        f"<b>Зачем:</b> {html.escape(why)}\n"
        f"<b>Дата:</b> {html.escape(date_text)}\n"
    )
    await _send_admin_message(bot, body, THREAD_WRITE_OFF)
    await _send_admin_photo(bot, receipt_photo_file_id, "Чек списания", THREAD_WRITE_OFF)
