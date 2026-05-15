FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/scheduler/requirements.txt /app/scheduler/requirements.txt
RUN pip install -r /app/scheduler/requirements.txt

COPY services/shared /app/shared
COPY services/scheduler /app/scheduler
# Alert engine + rules + channels are reused by the scheduler. We copy the
# minimum surface area rather than the whole api package to keep the image
# lean and avoid pulling in fastapi at scheduler startup.
COPY services/api/__init__.py /app/api/__init__.py
COPY services/api/alerts /app/api/alerts

ENV PYTHONPATH=/app TZ=Asia/Dubai
CMD ["python", "-m", "scheduler.main"]
