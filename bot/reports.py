from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import User

from bot.config import ADMIN_GROUP_CHAT_ID

MSK = ZoneInfo("Europe/Moscow")


def _user_line(user: User) -> str:
    parts = []
    if user.username:
        parts.append(f"@{user.username}")
    parts.append(f"id:{user.id}")
    return " ".join(parts)


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
    await bot.send_message(ADMIN_GROUP_CHAT_ID, header, parse_mode="HTML")

    for i, (title, ph) in enumerate(zip(items, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if not fid:
            continue
        await bot.send_photo(ADMIN_GROUP_CHAT_ID, fid, caption=caption[:1024])


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
    await bot.send_message(ADMIN_GROUP_CHAT_ID, header, parse_mode="HTML")

    for i, (title, ph) in enumerate(zip(photo_items, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if fid:
            await bot.send_photo(ADMIN_GROUP_CHAT_ID, fid, caption=caption[:1024])

    await bot.send_message(ADMIN_GROUP_CHAT_ID, "📝 <b>Кратко о дне</b>", parse_mode="HTML")
    for prompt, text in zip(text_prompts, texts):
        body = f"<b>{html.escape(prompt)}</b>\n{html.escape(text)}"
        await bot.send_message(ADMIN_GROUP_CHAT_ID, body, parse_mode="HTML")


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
    await bot.send_message(ADMIN_GROUP_CHAT_ID, header, parse_mode="HTML")

    for i, (title, ph) in enumerate(zip(questions, photos), start=1):
        caption = f"{i}. {title}"
        fid = ph.get("file_id")
        if fid:
            await bot.send_photo(ADMIN_GROUP_CHAT_ID, fid, caption=caption[:1024])

    await bot.send_message(
        ADMIN_GROUP_CHAT_ID,
        f"⭐ <b>{rating_question}</b>\nОценка: {rating_value} ({rating_label})",
        parse_mode="HTML",
    )
