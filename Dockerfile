# --- build the React voice console (frontend/) ---
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- API + built UI ---
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/raktsetu.db

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY static ./static
# Sarvam SDK for the browser voice relay (/api/voice/ws). Not the [all] extra: that pulls PyAudio,
# which needs PortAudio and is only used by the laptop script.
RUN pip install . "sarvam-conv-ai-sdk>=1.1" && useradd --uid 10001 --no-create-home raktsetu \
    && mkdir -p /data && chown raktsetu /data
# FastAPI serves this at / (app/main.py DIST); the old dashboard stays at /legacy.
COPY --from=web /web/dist ./frontend/dist

USER 10001
EXPOSE 8000
# One worker on purpose: request state, call drivers and webhook waiters live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
