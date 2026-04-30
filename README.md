# Mucara — бот чек-листов для бара (Telegram)

Бот на [aiogram 3](https://docs.aiogram.dev/) + FastAPI webhook: белый список сотрудников, чек-листы открытия/закрытия, лайн-чек с оценкой менеджера, поиск техкарт. Отчёты и фото уходят в указанную Telegram-группу. Состояние и whitelist хранятся в **файлах** (без БД), как в вашей текущей схеме.

## Что нужно до запуска

1. Создать бота в [@BotFather](https://t.me/BotFather), получить токен.
2. Создать группу для отчётов, добавить туда бота, выдать право отправлять сообщения и медиа.
3. Узнать `chat_id` группы (через бота [@userinfobot](https://t.me/userinfobot) в группе, через `getUpdates`, или временный скрипт) — для супергрупп обычно отрицательное число вида `-100...`.
4. Иметь публичный HTTPS-адрес приложения для Telegram webhook.

## Переменные окружения

Скопируйте `.env.example` в `.env` (локально) или задайте переменные в панели Timeweb Cloud:

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота |
| `ADMIN_GROUP_CHAT_ID` | ID группы (в @GetIDsBot для супергруппы вида **−100…**). Если случайно указали число **без минуса**, приложение само добавит минус. |
| `DATA_DIR` | Каталог для `allowed_users.json` и `sessions.json` (на проде — **постоянный диск** Timeweb, см. ниже). Если не задан — `./data` от корня проекта |
| `RECIPES_PATH` | Необязательно: путь к `recipes.json`. По умолчанию `data/recipes.json` из образа/репозитория (техкарты не обязаны жить на том же диске, что и сессии) |
| `WEBHOOK_BASE_URL` | Публичный HTTPS-адрес приложения без слеша на конце, например `https://example.com`. Из него будет собран webhook URL |
| `WEBHOOK_URL` | Необязательно: полный URL webhook. Если задан, используется вместо `WEBHOOK_BASE_URL + WEBHOOK_PATH` |
| `WEBHOOK_PATH` | Путь webhook endpoint. По умолчанию `/telegram/webhook` |
| `WEBHOOK_SECRET_TOKEN` | Необязательно: секрет для проверки заголовка `X-Telegram-Bot-Api-Secret-Token` |
| `PORT` | Порт FastAPI-приложения. Обычно задаётся хостингом, локально по умолчанию `8000` |

## Сотрудники (whitelist)

Файл `data/allowed_users.json` в репозитории содержит whitelist сотрудников. При деплое копируется в `DATA_DIR`, если там ещё нет своего файла. Локальные правки на сервере только в `DATA_DIR/allowed_users.json` на диске.

При первом запуске создаётся файл из этого примера — изначально `"users": []`, никто не проходит whitelist, пока вы не добавите записи на диске (или не отредактируете файл после копирования).

Формат:

```json
{
  "users": [
    { "user_id": 123456789 },
    { "username": "barista_nick" }
  ]
}
```

Достаточно **либо** `user_id`, **либо** `username` (без `@`).

После правки whitelist на сервере перезапустите приложение (или дождитесь деплоя — см. ниже).

## Техкарты

Файл `data/recipes.json` генерируется из `data/ttk_source.txt` (текст, совпадающий с содержимым PDF «ТТК Мычара»). Поля: `name`, `text`; опционально `aliases`. Поиск в боте: точное совпадение, подстрока, совпадение по всем словам запроса.

**Обновить техкарты после смены PDF:** положите актуальный текст в `data/ttk_source.txt` (или скопируйте текст из PDF вручную), затем выполните:

```bash
node scripts/build_recipes.mjs
```

или `python scripts/build_recipes.py`. Будет перезаписан `data/recipes.json`.

## Python 3.14 на Timeweb

Если в окружении **Python 3.14**, используйте актуальные зависимости из `requirements.txt` (aiogram 3.24 + pydantic 2.11+). Старые версии тянули `pydantic-core`, который при установке из исходников падал на PyO3. Альтернатива: в панели Timeweb выбрать **Python 3.12 или 3.13** для приложения.

## Деплой через GitHub → Timeweb Cloud

1. Подключите репозиторий к Timeweb, укажите ветку (например `main`).
2. В панели выберите окружение **Python**, framework **FastAPI**.
3. Сборка: `pip install --upgrade -r requirements.txt`.
4. Старт: `python -m bot.main` из корня репозитория. Эта команда поднимает Uvicorn/FastAPI и регистрирует webhook в Telegram.
5. Healthcheck path: `/health`.
6. Задайте `WEBHOOK_BASE_URL` равным публичному HTTPS-адресу приложения в Timeweb, например `https://your-app.example`. Если используете свой путь, задайте ещё `WEBHOOK_PATH`.
7. **Обязательно** подключите **постоянный диск** и задайте `DATA_DIR` на точку монтирования, чтобы при новом деплое не терялись `allowed_users.json` и `sessions.json`.
8. Секреты (`BOT_TOKEN`, `ADMIN_GROUP_CHAT_ID`, `WEBHOOK_SECRET_TOKEN`) задавайте только в панели Timeweb, не в Git.

В `.gitignore` только `data/sessions.json` (сессии не коммитим).

## Локальный запуск

Для локального webhook нужен публичный HTTPS-туннель (например, ngrok/Cloudflare Tunnel) и `WEBHOOK_BASE_URL` с адресом туннеля.

```bash
cd путь/к/Mucara
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# заполните .env
python -m bot.main
```

Linux/macOS: `cp .env.example .env` и `source .venv/bin/activate`.

## Поведение

- Не из whitelist — ответ: «Извините, вы не сотрудник».
- Чек-листы строго по пунктам; без фото пункт не засчитывается (где требуется фото).
- Незавершённый сценарий сохраняется в `sessions.json`; после `/start` бот напомнит и покажет текущий шаг.
- Переключение на другой раздел при незавершённом чек-листе — подтверждение кнопками.

## Git: связать папку на компьютере с GitHub

**Вариант А (удобнее всего):** склонировать репозиторий и работать только в этой папке.

```bash
cd %USERPROFILE%\Desktop
git clone https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПО.git
cd ВАШ_РЕПО
```

**Вариант Б:** папка уже есть (например `Mucara`), в ней лежит проект, репозиторий на GitHub пустой или уже с файлами.

```bash
cd путь\к\Mucara
git init
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПО.git
git add .
git commit -m "Update"
git push -u origin main
```

Если на GitHub уже есть коммиты, перед первым push сделайте `git pull origin main --allow-unrelated-histories`, разрешите конфликты при необходимости, затем `git push`.

Проверка:

```bash
git remote -v
```

Для SSH: `git remote add origin git@github.com:ЛОГИН/РЕПО.git` (ключи в [настройках GitHub](https://github.com/settings/keys)).

## Структура проекта

- `bot/` — код бота
- `data/` — пример whitelist и шаблон техкарт (реальные секретные файлы в Git не попадают)
