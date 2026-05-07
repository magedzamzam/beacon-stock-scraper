FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/sentiment/requirements.txt /app/sentiment/requirements.txt
RUN pip install -r /app/sentiment/requirements.txt

COPY services/shared /app/shared
COPY services/sentiment /app/sentiment

# Pre-download the FinBERT weights at build time so first request isn't a 60s
# cold-start. Skip in offline builds by setting SENTIMENT_PREFETCH=0.
ARG SENTIMENT_PREFETCH=1
ARG SENTIMENT_MODEL=ProsusAI/finbert
RUN if [ "$SENTIMENT_PREFETCH" = "1" ]; then \
      python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
                 AutoTokenizer.from_pretrained('${SENTIMENT_MODEL}'); \
                 AutoModelForSequenceClassification.from_pretrained('${SENTIMENT_MODEL}')" ; \
    fi

ENV PYTHONPATH=/app
EXPOSE 8003
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8003/healthz || exit 1

CMD ["uvicorn", "sentiment.main:app", "--host", "0.0.0.0", "--port", "8003"]
