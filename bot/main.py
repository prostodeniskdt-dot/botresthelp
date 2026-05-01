<<<<<<< HEAD
=======
import asyncio
import contextlib
>>>>>>> local-merge
import logging
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL или WEBHOOK_BASE_URL не задан: webhook некуда регистрировать")

    try:
        me = await bot.get_me()
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

<<<<<<< HEAD
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=WEBHOOK_DROP_PENDING_UPDATES,
            secret_token=WEBHOOK_SECRET_TOKEN,
        )
        logger.info("Webhook зарегистрирован: %s", WEBHOOK_URL)
        yield
=======
        dp = Dispatcher()
        dp.update.middleware(AuthMiddleware())
        dp.update.middleware(SessionMiddleware())
        dp.include_router(setup_router())
        reminder_task = asyncio.create_task(reminder_loop(bot))
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                polling_timeout=int(POLLING_TIMEOUT_S),
            )
        finally:
            reminder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
    except TelegramConflictError:
        logger.exception("Polling conflict: уже запущен другой экземпляр бота с этим BOT_TOKEN")
        raise
>>>>>>> local-merge
    except TelegramNetworkError:
        logger.exception("Telegram API недоступен или отвечает с таймаутом")
        raise
    finally:
        try:
            await flush_sessions()
        except Exception:
            logger.exception("Не удалось сбросить sessions.json перед выходом")
        if DELETE_WEBHOOK_ON_SHUTDOWN:
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
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
