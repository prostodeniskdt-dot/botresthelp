import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from bot.config import (
    ADMIN_GROUP_CHAT_ID,
    APP_HOST,
    APP_PORT,
    BOT_TOKEN,
    DELETE_WEBHOOK_ON_SHUTDOWN,
    POLLING_TIMEOUT_S,
    TELEGRAM_POOL_LIMIT,
    TELEGRAM_REQUEST_TIMEOUT_S,
    USE_POLLING,
    USE_WEBHOOK,
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

TELEGRAM_CALL_RETRIES = 5
TELEGRAM_RETRY_DELAY_S = 3.0
BOOTSTRAP_RETRY_DELAY_S = 15.0
WEBHOOK_WATCHDOG_INTERVAL_S = 120.0

# aiogram start_polling считает bot.session.timeout + polling_timeout.
# Нужен числовой timeout (сек), иначе TypeError: ClientTimeout + int.
session = AiohttpSession(
    timeout=float(TELEGRAM_REQUEST_TIMEOUT_S),
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

_webhook_lock = asyncio.Lock()
_bot_ready = False
_webhook_registered = False
_polling_active = False


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
    for attempt in range(1, TELEGRAM_CALL_RETRIES + 1):
        try:
            return await coro_factory()
        except TelegramNetworkError as exc:
            last_error = exc
            logger.warning(
                "Telegram %s: попытка %s/%s не удалась (%s)",
                description,
                attempt,
                TELEGRAM_CALL_RETRIES,
                exc,
            )
            if attempt < TELEGRAM_CALL_RETRIES:
                await asyncio.sleep(TELEGRAM_RETRY_DELAY_S)
    assert last_error is not None
    raise last_error


async def _log_webhook_info() -> None:
    info = await bot.get_webhook_info()
    logger.info(
        "Webhook info: url=%r pending=%s last_error_date=%s last_error=%s",
        info.url,
        info.pending_update_count,
        info.last_error_date,
        info.last_error_message or "(нет)",
    )


async def _register_webhook() -> None:
    global _webhook_registered

    async with _webhook_lock:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=WEBHOOK_DROP_PENDING_UPDATES,
            secret_token=WEBHOOK_SECRET_TOKEN,
        )
        _webhook_registered = True
        logger.info(
            "Webhook зарегистрирован: %s (allowed_updates=%s)",
            WEBHOOK_URL,
            ALLOWED_UPDATES,
        )
        await _log_webhook_info()


async def _ensure_webhook() -> None:
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
    else:
        logger.info(
            "Webhook OK: pending=%s url=%r",
            info.pending_update_count,
            info.url,
        )


async def _process_update(update: Update) -> None:
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("Ошибка обработки update id=%s kinds=%s", update.update_id, _update_kinds(update))


async def _start_reminders_if_needed(reminder_task_holder: dict[str, asyncio.Task[None] | None]) -> None:
    if reminder_task_holder.get("task") is None:
        reminder_task_holder["task"] = asyncio.create_task(reminder_loop(bot))


async def bootstrap_bot(reminder_task_holder: dict[str, asyncio.Task[None] | None]) -> None:
    """Инициализация webhook в фоне — HTTP-сервер стартует сразу для healthcheck."""
    global _bot_ready

    while True:
        try:
            me = await _telegram_with_retry("get_me", bot.get_me)
            _bot_ready = True
            logger.info(
                "Бот запущен: @%s (id=%s), режим webhook...",
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
            await _start_reminders_if_needed(reminder_task_holder)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "bootstrap_bot не завершился — повтор через %s с",
                BOOTSTRAP_RETRY_DELAY_S,
            )
            await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)


async def bootstrap_polling(reminder_task_holder: dict[str, asyncio.Task[None] | None]) -> None:
    """Long polling: бот сам забирает обновления — не нужен входящий webhook от Telegram."""
    global _bot_ready, _polling_active

    while True:
        try:
            me = await _telegram_with_retry("get_me", bot.get_me)
            _bot_ready = True
            logger.info(
                "Бот запущен: @%s (id=%s), режим long polling...",
                me.username,
                me.id,
            )
            try:
                chat = await bot.get_chat(ADMIN_GROUP_CHAT_ID)
                chat_name = chat.title or getattr(chat, "full_name", None) or str(chat.id)
                logger.info("Админ-группа доступна: %s (%s)", chat_name, chat.id)
            except Exception:
                logger.exception("Не удалось проверить ADMIN_GROUP_CHAT_ID=%s", ADMIN_GROUP_CHAT_ID)

            await _telegram_with_retry(
                "delete_webhook",
                lambda: bot.delete_webhook(drop_pending_updates=False),
            )
            logger.info("Webhook снят — Telegram будет отдавать обновления через getUpdates")
            await _start_reminders_if_needed(reminder_task_holder)
            _polling_active = True
            await dp.start_polling(
                bot,
                allowed_updates=ALLOWED_UPDATES,
                polling_timeout=int(POLLING_TIMEOUT_S),
                handle_signals=False,
                close_bot_session=False,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            _polling_active = False
            logger.exception(
                "bootstrap_polling упал — повтор через %s с",
                BOOTSTRAP_RETRY_DELAY_S,
            )
            await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)


async def webhook_watchdog() -> None:
    while True:
        try:
            if _bot_ready:
                await _ensure_webhook()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("webhook_watchdog tick failed")
        await asyncio.sleep(WEBHOOK_WATCHDOG_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if USE_WEBHOOK and not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL или WEBHOOK_BASE_URL не задан: webhook некуда регистрировать")

    reminder_holder: dict[str, asyncio.Task[None] | None] = {"task": None}
    watchdog_task: asyncio.Task[None] | None = None

    if USE_POLLING:
        logger.info("BOT_UPDATE_MODE=polling — входящий webhook от Telegram не используется")
        bootstrap_task = asyncio.create_task(bootstrap_polling(reminder_holder))
    else:
        logger.info("BOT_UPDATE_MODE=webhook")
        bootstrap_task = asyncio.create_task(bootstrap_bot(reminder_holder))
        watchdog_task = asyncio.create_task(webhook_watchdog())

    logger.info("HTTP-сервер готов, инициализация Telegram в фоне...")
    try:
        yield
    finally:
        bootstrap_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bootstrap_task
        if _polling_active:
            with contextlib.suppress(Exception):
                await dp.stop_polling()
        if watchdog_task is not None:
            watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog_task
        reminder_task = reminder_holder.get("task")
        if reminder_task is not None:
            reminder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
        try:
            await flush_sessions()
        except Exception:
            logger.exception("Не удалось сбросить sessions.json перед выходом")
        if DELETE_WEBHOOK_ON_SHUTDOWN and _webhook_registered:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info("Webhook удалён при остановке приложения")
            except Exception:
                logger.exception("Не удалось удалить webhook при остановке")
        await bot.session.close()


app = FastAPI(title="Mucara Telegram Bot", lifespan=lifespan)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict[str, Any]:
    return {"ok": True, "mode": "polling" if USE_POLLING else "webhook", "bot_ready": _bot_ready}


@app.api_route("/", methods=["GET", "HEAD"])
async def root_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/health/webhook")
async def health_webhook() -> JSONResponse:
    if USE_POLLING:
        return JSONResponse(
            {
                "ok": _bot_ready and _polling_active,
                "mode": "polling",
                "bot_ready": _bot_ready,
                "polling_active": _polling_active,
            }
        )
    if not _bot_ready:
        return JSONResponse({"ok": False, "reason": "bot_not_ready"}, status_code=503)
    try:
        info = await bot.get_webhook_info()
        return JSONResponse(
            {
                "ok": info.url == WEBHOOK_URL and not info.last_error_message,
                "mode": "webhook",
                "url": info.url,
                "expected_url": WEBHOOK_URL,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
                "last_error_date": info.last_error_date,
            }
        )
    except Exception as exc:
        logger.exception("health_webhook failed")
        return JSONResponse({"ok": False, "reason": str(exc)}, status_code=503)


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> dict[str, bool]:
    if USE_POLLING:
        return {"ok": True}

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
