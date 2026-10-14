FROM node:24-bookworm-slim AS frontend-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DEBUG=false \
    OCR_ENGINE=tesseract \
    OCR_LANG=eng+hin \
    TESSERACT_PATH=/usr/bin/tesseract \
    WORKER_POOL_SIZE=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY --from=frontend-build /app/web/dist ./web/dist

RUN mkdir -p /var/data/uploads /var/data/outputs /var/data/cache /var/data/queue /app/logs
ENV UPLOAD_DIR=/var/data/uploads \
    OUTPUT_DIR=/var/data/outputs \
    CACHE_DIR=/var/data/cache \
    TASK_QUEUE_DIR=/var/data/queue

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
