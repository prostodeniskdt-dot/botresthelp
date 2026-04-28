import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError

from bot.config import ADMIN_GROUP_CHAT_ID, BOT_TOKEN
from bot.handlers import setup_router
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.session import SessionMiddleware
from bot.storage import flush_sessions

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        logger.info(
            "Бот запущен: @%s (id=%s), long polling...",
            me.username,
            me.id,
        )
        try:
            chat = await bot.get_chat(ADMIN_GROUP_CHAT_ID)
            chat_name = chat.title or getattr(chat, "full_name", None) or str(chat.id)
            logger.info("Админ-группа доступна: %s (%s)", chat_name, chat.id)
        except Exception:
            logger.exception("Не удалось проверить ADMIN_GROUP_CHAT_ID=%s", ADMIN_GROUP_CHAT_ID)

        dp = Dispatcher()
        dp.update.middleware(AuthMiddleware())
        dp.update.middleware(SessionMiddleware())
        dp.include_router(setup_router())
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramConflictError:
        logger.exception("Polling conflict: уже запущен другой экземпляр бота с этим BOT_TOKEN")
        raise
    except TelegramNetworkError:
        logger.exception("Telegram API недоступен или отвечает с таймаутом")
        raise
    finally:
        try:
            await flush_sessions()
        except Exception:
            logger.exception("Не удалось сбросить sessions.json перед выходом")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
