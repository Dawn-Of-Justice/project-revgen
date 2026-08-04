# Build context is the repo ROOT, not backend/ -- the service reads
# config/commands.json, which lives outside the backend directory because the
# emitter firmware needs the same file.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tools ./tools
COPY config /app/config

# Layout matters: app/config.py resolves REPO_ROOT as parents[2], so
# /app/backend/app/config.py -> /app, and catalog_path -> /app/config/... .

# The mounted volume. Overridden by DATA_DIR in fly.toml; this default keeps
# `docker run` working without a volume.
ENV DATA_DIR=/data
RUN mkdir -p /data && useradd -r -u 10001 revgen && chown -R revgen /data /app
USER revgen

EXPOSE 8080

# Single worker on purpose. The power debounce lives in process memory, so a
# second worker would keep its own timer and the safety rule would silently
# stop working. See config.py.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
