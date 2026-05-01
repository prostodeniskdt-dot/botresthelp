import logging

from aiogram import Router
from aiogram.types import ErrorEvent

router = Router()
logger = logging.getLogger(__name__)


@router.errors()
async def on_error(event: ErrorEvent) -> None:
    logger.error("Необработанная ошибка update", exc_info=event.exception)
