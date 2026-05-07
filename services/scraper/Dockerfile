FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install shared deps first (layer cache)
COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/scraper/requirements.txt /app/scraper/requirements.txt
RUN pip install -r /app/scraper/requirements.txt

# Copy code
COPY services/shared /app/shared
COPY services/scraper /app/scraper

ENV PYTHONPATH=/app
WORKDIR /app

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8001/healthz || exit 1

CMD ["uvicorn", "scraper.main:app", "--host", "0.0.0.0", "--port", "8001"]
