from aiogram import Router

from bot.handlers.dialog import router as dialog_router


def setup_router() -> Router:
    r = Router()
    r.include_router(dialog_router)
    return r
