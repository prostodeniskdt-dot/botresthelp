import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientTimeout
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
    TELEGRAM_CONNECT_TIMEOUT_S,
    TELEGRAM_POOL_LIMIT,
    TELEGRAM_PROXY,
    TELEGRAM_REQUEST_TIMEOUT_S,
    WEBHOOK_DROP_PENDING_UPDATES,
    WEBHOOK_MAX_CONNECTIONS,
    WEBHOOK_PATH,
    WEBHOOK_SECRET_TOKEN,
    WEBHOOK_URL,
    WEBHOOK_WATCHDOG_INTERVAL_S,
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

ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]

TELEGRAM_CALL_RETRIES = 8
TELEGRAM_RETRY_DELAY_S = 5.0
BOOTSTRAP_RETRY_DELAY_S = 20.0

session = AiohttpSession(
    timeout=ClientTimeout(
        total=float(TELEGRAM_REQUEST_TIMEOUT_S),
        connect=float(TELEGRAM_CONNECT_TIMEOUT_S),
        sock_connect=float(TELEGRAM_CONNECT_TIMEOUT_S),
    ),
    limit=int(TELEGRAM_POOL_LIMIT),
    proxy=TELEGRAM_PROXY,
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
_update_tasks: set[asyncio.Task[None]] = set()
_bootstrap_phase = "starting"
_bootstrap_last_error: str | None = None


def _set_bootstrap_phase(phase: str, error: str | None = None) -> None:
    global _bootstrap_phase, _bootstrap_last_error
    _bootstrap_phase = phase
    if error is not None:
        _bootstrap_last_error = error


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
            _set_bootstrap_phase("telegram_api", str(exc))
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
        _set_bootstrap_phase("webhook")
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=WEBHOOK_DROP_PENDING_UPDATES,
            secret_token=WEBHOOK_SECRET_TOKEN,
            max_connections=WEBHOOK_MAX_CONNECTIONS,
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
    needs_reregister = info.url != WEBHOOK_URL or bool(info.last_error_message)
    if needs_reregister:
        if info.url != WEBHOOK_URL:
            logger.warning(
                "Webhook URL не совпадает: telegram=%r expected=%r — перерегистрирую",
                info.url,
                WEBHOOK_URL,
            )
        if info.last_error_message:
            logger.warning(
                "Webhook last_error_date=%s message=%s pending=%s — перерегистрирую",
                info.last_error_date,
                info.last_error_message,
                info.pending_update_count,
            )
        await _register_webhook()
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
        logger.exception(
            "Ошибка обработки update id=%s kinds=%s",
            update.update_id,
            _update_kinds(update),
        )


def _schedule_update(update: Update) -> None:
    task = asyncio.create_task(_process_update(update))
    _update_tasks.add(task)
    task.add_done_callback(_update_tasks.discard)


async def bootstrap_bot(reminder_task_holder: dict[str, asyncio.Task[None] | None]) -> None:
    """Регистрация webhook в фоне — HTTP /health доступен сразу."""
    global _bot_ready

    while True:
        try:
            if not WEBHOOK_URL:
                _set_bootstrap_phase("missing_webhook_url")
                logger.error(
                    "WEBHOOK_BASE_URL не задан — добавьте в Timeweb, "
                    "например WEBHOOK_BASE_URL=https://your-app.twc1.net"
                )
                await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)
                continue

            _set_bootstrap_phase("telegram_api")
            me = await _telegram_with_retry("get_me", bot.get_me)
            _bot_ready = True
            logger.info("Бот запущен: @%s (id=%s), webhook...", me.username, me.id)
            try:
                chat = await bot.get_chat(ADMIN_GROUP_CHAT_ID)
                chat_name = chat.title or getattr(chat, "full_name", None) or str(chat.id)
                logger.info("Админ-группа доступна: %s (%s)", chat_name, chat.id)
            except Exception:
                logger.exception("Не удалось проверить ADMIN_GROUP_CHAT_ID=%s", ADMIN_GROUP_CHAT_ID)

            await _telegram_with_retry("set_webhook", _register_webhook)
            _set_bootstrap_phase("ready")
            _bootstrap_last_error = None
            if reminder_task_holder.get("task") is None:
                reminder_task_holder["task"] = asyncio.create_task(reminder_loop(bot))
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _set_bootstrap_phase("telegram_api", str(exc))
            logger.exception(
                "bootstrap_bot не завершился — повтор через %s с",
                BOOTSTRAP_RETRY_DELAY_S,
            )
            await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)


async def webhook_watchdog() -> None:
    while True:
        await asyncio.sleep(WEBHOOK_WATCHDOG_INTERVAL_S)
        try:
            if _bot_ready and WEBHOOK_URL:
                await _ensure_webhook()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("webhook_watchdog tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    reminder_holder: dict[str, asyncio.Task[None] | None] = {"task": None}
    bootstrap_task = asyncio.create_task(bootstrap_bot(reminder_holder))
    watchdog_task = asyncio.create_task(webhook_watchdog())
    if WEBHOOK_URL:
        logger.info("HTTP-сервер готов, регистрация webhook в фоне: %s", WEBHOOK_URL)
        if TELEGRAM_PROXY:
            logger.info("Telegram API через прокси: %s", TELEGRAM_PROXY)
    else:
        logger.warning("HTTP-сервер готов, но WEBHOOK_BASE_URL не задан")
    try:
        yield
    finally:
        bootstrap_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bootstrap_task
        watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task
        reminder_task = reminder_holder.get("task")
        if reminder_task is not None:
            reminder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
        if _update_tasks:
            await asyncio.gather(*list(_update_tasks), return_exceptions=True)
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


def _health_payload() -> dict[str, Any]:
    return {
        "ok": _bootstrap_phase in {"ready", "webhook", "telegram_api", "starting"},
        "bot_ready": _bot_ready,
        "webhook_registered": _webhook_registered,
        "webhook_url_configured": bool(WEBHOOK_URL),
        "expected_webhook_url": WEBHOOK_URL or None,
        "bootstrap_phase": _bootstrap_phase,
        "bootstrap_last_error": _bootstrap_last_error,
        "checked_at": datetime.now(UTC).isoformat(),
    }


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict[str, Any]:
    return _health_payload()


@app.api_route("/", methods=["GET", "HEAD"])
async def root_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/health/webhook")
async def health_webhook() -> JSONResponse:
    payload: dict[str, Any] = _health_payload()
    if not WEBHOOK_URL:
        payload["ok"] = False
        payload["reason"] = "webhook_url_not_configured"
        return JSONResponse(payload, status_code=503)

    if not _bot_ready:
        payload["ok"] = False
        payload["reason"] = "connecting_to_telegram_api"
        payload["hint"] = (
            "Сервер жив, URL задан. Ждём ответа api.telegram.org — на Timeweb это может "
            "занять 1–3 минуты. Если не меняется — проверьте TELEGRAM_PROXY или поддержку хостинга."
        )
        return JSONResponse(payload, status_code=200)

    try:
        info = await bot.get_webhook_info()
        payload.update(
            {
                "ok": info.url == WEBHOOK_URL and not info.last_error_message,
                "url": info.url,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
                "last_error_date": info.last_error_date,
            }
        )
        return JSONResponse(payload, status_code=200)
    except Exception as exc:
        logger.exception("health_webhook failed")
        payload["ok"] = False
        payload["reason"] = str(exc)
        return JSONResponse(payload, status_code=200)


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
    _schedule_update(update)
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
