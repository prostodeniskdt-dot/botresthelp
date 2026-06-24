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

TELEGRAM_CALL_RETRIES = 6
TELEGRAM_RETRY_DELAY_S = 5.0
BOOTSTRAP_RETRY_DELAY_S = 15.0

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

_bot_ready = False
_webhook_registered = False
_last_webhook_received_at: str | None = None
_last_webhook_info: dict[str, Any] | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


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
    global _last_webhook_info

    info = await bot.get_webhook_info()
    _last_webhook_info = {
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_message": info.last_error_message,
        "last_error_date": _json_safe(info.last_error_date),
        "ip_address": info.ip_address,
    }
    logger.info(
        "Webhook info: url=%r pending=%s ip=%s last_error=%s",
        info.url,
        info.pending_update_count,
        info.ip_address or "(нет)",
        info.last_error_message or "(нет)",
    )
    if info.last_error_message:
        logger.error(
            "Telegram не доставляет обновления: %s (pending=%s, url=%s)",
            info.last_error_message,
            info.pending_update_count,
            WEBHOOK_URL,
        )


async def _register_webhook() -> None:
    global _webhook_registered

    allowed_updates = dp.resolve_used_update_types()
    # Сброс webhook перед регистрацией помогает Telegram начать доставку заново.
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=allowed_updates,
        drop_pending_updates=WEBHOOK_DROP_PENDING_UPDATES,
        secret_token=WEBHOOK_SECRET_TOKEN,
        max_connections=WEBHOOK_MAX_CONNECTIONS,
    )
    _webhook_registered = True
    logger.info(
        "Webhook зарегистрирован: %s (allowed_updates=%s)",
        WEBHOOK_URL,
        allowed_updates,
    )
    await _log_webhook_info()


async def bootstrap_bot(reminder_task_holder: dict[str, asyncio.Task[None] | None]) -> None:
    """Telegram init в фоне: HTTP /health отвечает сразу, Timeweb не убивает контейнер."""
    global _bot_ready

    while True:
        try:
            if not WEBHOOK_URL:
                logger.error(
                    "WEBHOOK_BASE_URL не задан — задайте в Timeweb, "
                    "например WEBHOOK_BASE_URL=https://your-app.twc1.net"
                )
                await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)
                continue

            me = await _telegram_with_retry("get_me", bot.get_me)
            _bot_ready = True
            logger.info("Бот запущен: @%s (id=%s)", me.username, me.id)

            try:
                chat = await bot.get_chat(ADMIN_GROUP_CHAT_ID)
                chat_name = chat.title or getattr(chat, "full_name", None) or str(chat.id)
                logger.info("Админ-группа доступна: %s (%s)", chat_name, chat.id)
            except Exception:
                logger.exception("Не удалось проверить ADMIN_GROUP_CHAT_ID=%s", ADMIN_GROUP_CHAT_ID)

            await _telegram_with_retry("set_webhook", _register_webhook)

            if reminder_task_holder.get("task") is None:
                reminder_task_holder["task"] = asyncio.create_task(reminder_loop(bot))
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "bootstrap_bot не завершился — повтор через %s с",
                BOOTSTRAP_RETRY_DELAY_S,
            )
            await asyncio.sleep(BOOTSTRAP_RETRY_DELAY_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reminder_holder: dict[str, asyncio.Task[None] | None] = {"task": None}
    bootstrap_task = asyncio.create_task(bootstrap_bot(reminder_holder))
    if WEBHOOK_URL:
        logger.info("HTTP-сервер готов, регистрация webhook в фоне: %s", WEBHOOK_URL)
    else:
        logger.warning("HTTP-сервер готов, но WEBHOOK_BASE_URL не задан")
    try:
        yield
    finally:
        bootstrap_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bootstrap_task
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


@app.middleware("http")
async def log_incoming_requests(request: Request, call_next: Any) -> Any:
    if request.method == "POST" and request.url.path == WEBHOOK_PATH:
        logger.info("Входящий POST %s от %s", WEBHOOK_PATH, _client_ip(request))
    response = await call_next(request)
    if request.method == "POST" and request.url.path == WEBHOOK_PATH:
        logger.info("Ответ POST %s: %s", WEBHOOK_PATH, response.status_code)
    return response


def _status_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": _bot_ready and _webhook_registered,
        "bot_ready": _bot_ready,
        "webhook_registered": _webhook_registered,
        "webhook_url_configured": bool(WEBHOOK_URL),
        "expected_webhook_url": WEBHOOK_URL or None,
        "last_webhook_received_at": _last_webhook_received_at,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if _last_webhook_info:
        payload["telegram_delivery"] = {
            "pending_update_count": _last_webhook_info.get("pending_update_count"),
            "last_error_message": _last_webhook_info.get("last_error_message"),
            "last_error_date": _last_webhook_info.get("last_error_date"),
            "ip_address": _last_webhook_info.get("ip_address"),
            "updates_reaching_server": _last_webhook_received_at is not None
            or not bool(_last_webhook_info.get("last_error_message")),
        }
    return payload


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict[str, bool]:
    # Timeweb healthcheck: всегда ok, иначе платформа перезапускает контейнер.
    return {"ok": True}


@app.api_route("/", methods=["GET", "HEAD"])
async def root_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/health/status")
async def health_status() -> dict[str, Any]:
    return _status_payload()


@app.get("/health/webhook")
async def health_webhook() -> JSONResponse:
    payload = _status_payload()
    if not WEBHOOK_URL:
        payload["ok"] = False
        payload["reason"] = "webhook_url_not_configured"
        return JSONResponse(payload, status_code=503)

    if not _bot_ready:
        payload["ok"] = False
        payload["reason"] = "connecting_to_telegram_api"
        return JSONResponse(payload, status_code=200)

    try:
        info = await bot.get_webhook_info()
        last_error_date = _json_safe(info.last_error_date)
        delivery_ok = info.url == WEBHOOK_URL and (
            _last_webhook_received_at is not None or not info.last_error_message
        )
        payload.update(
            {
                "ok": delivery_ok,
                "url": info.url,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
                "last_error_date": last_error_date,
                "ip_address": info.ip_address,
                "telegram_delivery": {
                    "pending_update_count": info.pending_update_count,
                    "last_error_message": info.last_error_message,
                    "last_error_date": last_error_date,
                    "ip_address": info.ip_address,
                    "updates_reaching_server": delivery_ok,
                },
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
    global _last_webhook_received_at

    if WEBHOOK_SECRET_TOKEN:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if received != WEBHOOK_SECRET_TOKEN:
            logger.warning(
                "Webhook отклонён: неверный secret token (from %s)",
                _client_ip(request),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
    except Exception:
        logger.exception("Webhook: некорректное тело запроса от %s", _client_ip(request))
        return {"ok": True}

    _last_webhook_received_at = datetime.now(UTC).isoformat()
    logger.info(
        "Webhook update id=%s kinds=%s from=%s",
        update.update_id,
        _update_kinds(update),
        _client_ip(request),
    )
    try:
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception(
            "Ошибка обработки update id=%s kinds=%s",
            update.update_id,
            _update_kinds(update),
        )
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
