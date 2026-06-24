import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, status

from bot.config import (
    ADMIN_GROUP_CHAT_ID,
    APP_HOST,
    APP_PORT,
    BOT_TOKEN,
    DELETE_WEBHOOK_ON_SHUTDOWN,
    TELEGRAM_CONNECT_TIMEOUT_S,
    TELEGRAM_POOL_LIMIT,
    TELEGRAM_REQUEST_TIMEOUT_S,
    WEBHOOK_DROP_PENDING_UPDATES,
    WEBHOOK_PATH,
    WEBHOOK_SECRET_TOKEN,
    WEBHOOK_URL,
)
from bot.handlers import setup_router
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.session import SessionMiddleware
from bot.shift_reminders import reminder_loop
from bot.storage import flush_sessions

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Явный список: reply-кнопки меню (message) и inline-кнопки (callback_query).
ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]

STARTUP_TELEGRAM_RETRIES = 5
STARTUP_RETRY_DELAY_S = 3.0
WEBHOOK_WATCHDOG_INTERVAL_S = 300.0

session = AiohttpSession(
    timeout=ClientTimeout(
        total=float(TELEGRAM_REQUEST_TIMEOUT_S),
        connect=float(TELEGRAM_CONNECT_TIMEOUT_S),
    ),
    limit=int(TELEGRAM_POOL_LIMIT),
)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=session,
)
dp = Dispatcher()
dp.update.middleware(AuthMiddleware())
dp.update.middleware(SessionMiddleware())
dp.include_router(setup_router())


def _update_kinds(update: Update) -> list[str]:
    kinds: list[str] = []
    if update.message is not None:
        kinds.append("message")
    if update.edited_message is not None:
        kinds.append("edited_message")
    if update.callback_query is not None:
        kinds.append("callback_query")
    return kinds or ["unknown"]


async def _telegram_with_retry(description: str, coro_factory: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, STARTUP_TELEGRAM_RETRIES + 1):
        try:
            return await coro_factory()
        except TelegramNetworkError as exc:
            last_error = exc
            logger.warning(
                "Telegram %s: попытка %s/%s не удалась (%s)",
                description,
                attempt,
                STARTUP_TELEGRAM_RETRIES,
                exc,
            )
            if attempt < STARTUP_TELEGRAM_RETRIES:
                await asyncio.sleep(STARTUP_RETRY_DELAY_S)
    assert last_error is not None
    raise last_error


async def _register_webhook() -> None:
    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=ALLOWED_UPDATES,
        drop_pending_updates=WEBHOOK_DROP_PENDING_UPDATES,
        secret_token=WEBHOOK_SECRET_TOKEN,
    )
    logger.info("Webhook зарегистрирован: %s (allowed_updates=%s)", WEBHOOK_URL, ALLOWED_UPDATES)


async def _process_update(update: Update) -> None:
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Ошибка обработки update id=%s kinds=%s", update.update_id, _update_kinds(update))


async def webhook_watchdog() -> None:
    while True:
        try:
            await asyncio.sleep(WEBHOOK_WATCHDOG_INTERVAL_S)
            info = await bot.get_webhook_info()
            if info.url != WEBHOOK_URL:
                logger.warning(
                    "Webhook URL не совпадает: telegram=%r expected=%r — перерегистрирую",
                    info.url,
                    WEBHOOK_URL,
                )
                await _register_webhook()
            elif info.last_error_message:
                logger.warning(
                    "Webhook last_error_date=%s message=%s pending=%s",
                    info.last_error_date,
                    info.last_error_message,
                    info.pending_update_count,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("webhook_watchdog tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL или WEBHOOK_BASE_URL не задан: webhook некуда регистрировать")

    reminder_task: asyncio.Task[None] | None = None
    watchdog_task: asyncio.Task[None] | None = None
    startup_complete = False
    try:
        me = await _telegram_with_retry("get_me", bot.get_me)
        logger.info(
            "Бот запущен: @%s (id=%s), FastAPI webhook...",
            me.username,
            me.id,
        )
        try:
            chat = await bot.get_chat(ADMIN_GROUP_CHAT_ID)
            chat_name = chat.title or getattr(chat, "full_name", None) or str(chat.id)
            logger.info("Админ-группа доступна: %s (%s)", chat_name, chat.id)
        except Exception:
            logger.exception("Не удалось проверить ADMIN_GROUP_CHAT_ID=%s", ADMIN_GROUP_CHAT_ID)

        await _telegram_with_retry("set_webhook", _register_webhook)
        reminder_task = asyncio.create_task(reminder_loop(bot))
        watchdog_task = asyncio.create_task(webhook_watchdog())
        startup_complete = True
        yield
    except TelegramNetworkError:
        logger.exception("Telegram API недоступен или отвечает с таймаутом после всех попыток")
        raise
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog_task
        if reminder_task is not None:
            reminder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
        try:
            await flush_sessions()
        except Exception:
            logger.exception("Не удалось сбросить sessions.json перед выходом")
        if DELETE_WEBHOOK_ON_SHUTDOWN and startup_complete:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info("Webhook удалён при остановке приложения")
            except Exception:
                logger.exception("Не удалось удалить webhook при остановке")
        await bot.session.close()


app = FastAPI(title="Mucara Telegram Bot", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> dict[str, bool]:
    if WEBHOOK_SECRET_TOKEN:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if received != WEBHOOK_SECRET_TOKEN:
            logger.warning("Webhook отклонён: неверный secret token")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    logger.info("Webhook update id=%s kinds=%s", update.update_id, _update_kinds(update))
    asyncio.create_task(_process_update(update))
    return {"ok": True}


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=APP_HOST,
        port=int(APP_PORT),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
