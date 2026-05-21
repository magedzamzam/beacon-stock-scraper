FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/telegram_listener/requirements.txt /app/telegram_listener/requirements.txt
RUN pip install -r /app/telegram_listener/requirements.txt

COPY services/shared /app/shared
COPY services/telegram_listener /app/telegram_listener

ENV PYTHONPATH=/app TZ=Asia/Dubai
CMD ["python", "-m", "telegram_listener.main"]
