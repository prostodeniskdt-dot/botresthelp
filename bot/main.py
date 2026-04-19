import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN
from bot.handlers import setup_router
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.session import SessionMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.middleware(AuthMiddleware())
    dp.update.middleware(SessionMiddleware())
    dp.include_router(setup_router())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
