FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY docker ./docker
COPY scripts ./scripts

RUN useradd --create-home --shell /bin/bash iris \
    && mkdir -p /app/backups \
    && chown -R iris:iris /app
USER iris

ENV MALLOC_ARENA_MAX=2 \
    PORT=8080
EXPOSE 8080

ENTRYPOINT ["sh", "docker/entrypoint.sh"]
