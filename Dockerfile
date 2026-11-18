# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY scripts/disable-picomatch-extglobs.cjs /build/scripts/disable-picomatch-extglobs.cjs
RUN npm ci --ignore-scripts --no-audit --no-fund \
    && node ../scripts/disable-picomatch-extglobs.cjs
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY frontend/public ./public
COPY shared /build/shared

# Firebase web configuration is public. Private backend credentials are runtime-only.
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
RUN node -e "for (const key of ['VITE_FIREBASE_API_KEY','VITE_FIREBASE_AUTH_DOMAIN','VITE_FIREBASE_PROJECT_ID','VITE_FIREBASE_APP_ID']) if (!process.env[key]) throw new Error(key + ' is required');" \
    && npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/model-cache \
    HF_HUB_OFFLINE=1 \
    STT_MODEL=base \
    SERVE_FRONTEND=true \
    APP_ENV=production
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Cache the current speech model during the build, rather than at server startup.
RUN HF_HUB_OFFLINE=0 python -c "from faster_whisper.utils import download_model; download_model('base')"
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*
COPY backend ./backend
COPY data/sources.json data/common-care-guidance.json data/reference-expansion.json data/health-reference-expansion.json data/pdf-health-reference-expansion.json data/everyday-care-reference-expansion.json data/activity-safety-reference-expansion.json data/practical-care-reference-expansion.json ./data/
COPY shared/kenya-contacts.json ./shared/kenya-contacts.json
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /opt/model-cache
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=90s --retries=3 \
    CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), timeout=2).close()"]
# Forward stop signals and normalize the expected SIGTERM exit.
ENTRYPOINT ["/usr/bin/tini", "-e", "143", "--"]
# One worker owns one speech model. Access logs otherwise include profile IDs in query strings.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--no-access-log"]
