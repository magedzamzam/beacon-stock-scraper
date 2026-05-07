FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/recommender/requirements.txt /app/recommender/requirements.txt
RUN pip install -r /app/recommender/requirements.txt

COPY services/shared /app/shared
COPY services/recommender /app/recommender

ENV PYTHONPATH=/app
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8002/healthz || exit 1

CMD ["uvicorn", "recommender.main:app", "--host", "0.0.0.0", "--port", "8002"]
