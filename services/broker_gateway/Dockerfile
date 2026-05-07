FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/broker_gateway/requirements.txt /app/broker_gateway/requirements.txt
RUN pip install -r /app/broker_gateway/requirements.txt

COPY services/shared /app/shared
COPY services/brokers /app/brokers
COPY services/broker_gateway /app/broker_gateway

ENV PYTHONPATH=/app
EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8004/healthz || exit 1
CMD ["uvicorn", "broker_gateway.main:app", "--host", "0.0.0.0", "--port", "8004"]
