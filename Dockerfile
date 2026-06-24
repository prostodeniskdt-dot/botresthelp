# Совместимо с aiogram 3.24 (Python >=3.10). На Timeweb при Python 3.14 используйте обновлённый requirements.txt.
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY data ./data

EXPOSE 8000

CMD ["python", "-m", "bot.main"]
