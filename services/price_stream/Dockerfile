FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY services/shared/requirements.txt /app/shared/requirements.txt
COPY services/price_stream/requirements.txt /app/price_stream/requirements.txt
RUN pip install -r /app/price_stream/requirements.txt

COPY services/shared /app/shared
COPY services/price_stream /app/price_stream

ENV PYTHONPATH=/app TZ=Asia/Dubai
CMD ["python", "-m", "price_stream.main"]
