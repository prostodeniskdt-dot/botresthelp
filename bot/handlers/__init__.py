from aiogram import Router

from bot.handlers.admin import router as admin_router
from bot.handlers.callbacks import router as callbacks_router
from bot.handlers.errors import router as errors_router
from bot.handlers.menu import router as menu_router
from bot.handlers.photos import router as photos_router
from bot.handlers.text_flows import router as text_router


def setup_router() -> Router:
    r = Router()
    r.include_router(errors_router)
    r.include_router(admin_router)
    r.include_router(menu_router)
    r.include_router(callbacks_router)
    r.include_router(photos_router)
    r.include_router(text_router)
    return r
