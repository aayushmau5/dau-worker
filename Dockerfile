FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY dau_worker ./dau_worker
COPY oban.toml README.md ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY --from=builder /app /app

CMD ["/app/.venv/bin/oban", "start"]
