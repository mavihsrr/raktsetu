FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/raktsetu.db

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY static ./static
RUN pip install . && useradd --uid 10001 --no-create-home raktsetu \
    && mkdir -p /data && chown raktsetu /data

USER 10001
EXPOSE 8000
# One worker on purpose: request state, call drivers and webhook waiters live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
