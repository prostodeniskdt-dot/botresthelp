import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _parse_int(name: str, *, default: int | None = None) -> int:
    """Читает целое из env. Если переменной нет — использует default (для деплоя без лишних секретов)."""
    raw = os.getenv(name, "").strip()
    if not raw:
        if default is None:
            raise RuntimeError(f"Переменная окружения {name} не задана")
        return default
    return int(raw)


def _parse_admin_group_chat_id() -> int:
    """ID группы/супергруппы для Bot API — всегда отрицательный. Частая ошибка: вставить число без минуса."""
    raw = os.getenv("ADMIN_GROUP_CHAT_ID", "").strip()
    if not raw:
        raise RuntimeError("Переменная окружения ADMIN_GROUP_CHAT_ID не задана")
    val = int(raw)
    if val > 0:
        val = -val
    return val


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")

ADMIN_GROUP_CHAT_ID = _parse_admin_group_chat_id()

# Темы (message_thread_id) внутри супергруппы ADMIN_GROUP_CHAT_ID.
# Значения по умолчанию — согласованные с темами в группе; можно переопределить в env.
THREAD_OPENING = _parse_int("THREAD_OPENING", default=20)
THREAD_CLOSING = _parse_int("THREAD_CLOSING", default=22)
THREAD_LINE = _parse_int("THREAD_LINE", default=63)
THREAD_INVOICES = _parse_int("THREAD_INVOICES", default=24)
THREAD_MOVE = _parse_int("THREAD_MOVE", default=26)
THREAD_WRITE_OFF = _parse_int("THREAD_WRITE_OFF", default=28)

_data_dir = os.getenv("DATA_DIR", "").strip()
if _data_dir:
    DATA_DIR = Path(_data_dir).resolve()
else:
    DATA_DIR = (ROOT / "data").resolve()

ALLOWED_USERS_PATH = DATA_DIR / "allowed_users.json"
SESSIONS_PATH = DATA_DIR / "sessions.json"

_recipes = os.getenv("RECIPES_PATH", "").strip()
if _recipes:
    RECIPES_PATH = Path(_recipes).resolve()
else:
    RECIPES_PATH = (ROOT / "data" / "recipes.json").resolve()

ALLOWED_USERS_EXAMPLE_SOURCE = (ROOT / "data" / "allowed_users.example.json").resolve()
