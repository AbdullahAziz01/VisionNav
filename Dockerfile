# VisionNav remote inference backend.
# Builds from a clean git checkout: does not COPY host yolov8n.pt or unused MiDaS ONNX.
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WEIGHTS_ROOT=/opt/visionnav-weights

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ ./pipeline/
COPY config/ ./config/
COPY tools/prepare_weights.py tools/seed_runtime_weights.py ./tools/
COPY main.py .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p \
        /opt/visionnav-weights/huggingface \
        /opt/visionnav-weights/torch \
        /opt/visionnav-weights/easyocr \
        /opt/visionnav-weights/yolo \
        /opt/visionnav-weights/config \
        /app/cache/huggingface \
        /app/cache/torch \
        /app/cache/easyocr \
        /app/config \
        /app/runs \
    && cp -a /app/config/. /opt/visionnav-weights/config/

# Bake the models this service actually loads. A later volume mount on /app/cache
# starts empty; docker-entrypoint.sh copies these files into the volume once.
RUN HF_HOME=/opt/visionnav-weights/huggingface \
    TORCH_HOME=/opt/visionnav-weights/torch \
    EASYOCR_MODULE_PATH=/opt/visionnav-weights/easyocr \
    WEIGHTS_ROOT=/opt/visionnav-weights \
    python tools/prepare_weights.py

ENV HF_HOME=/app/cache/huggingface \
    TORCH_HOME=/app/cache/torch \
    EASYOCR_MODULE_PATH=/app/cache/easyocr \
    WEIGHTS_ROOT=/opt/visionnav-weights

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ready || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
# One worker: tracker, calibration, and session state stay in a single process.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
