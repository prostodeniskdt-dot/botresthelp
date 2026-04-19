import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _parse_int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"Переменная окружения {name} не задана")
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

# Темы (message_thread_id) внутри супергруппы ADMIN_GROUP_CHAT_ID
THREAD_OPENING = _parse_int("THREAD_OPENING")
THREAD_CLOSING = _parse_int("THREAD_CLOSING")
THREAD_LINE = _parse_int("THREAD_LINE")
THREAD_INVOICES = _parse_int("THREAD_INVOICES")
THREAD_MOVE = _parse_int("THREAD_MOVE")
THREAD_WRITE_OFF = _parse_int("THREAD_WRITE_OFF")

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
