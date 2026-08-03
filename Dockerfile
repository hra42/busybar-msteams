# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.13-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install --no-install-recommends --yes gosu tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 busybar \
    && useradd --uid 10001 --gid busybar --no-create-home --shell /usr/sbin/nologin busybar \
    && mkdir --parents /app /data /config \
    && chown --recursive busybar:busybar /app /data /config

COPY --from=builder --chown=busybar:busybar /app/.venv /app/.venv
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MS_TOKEN_CACHE=/data/msal-token-cache.json

WORKDIR /app

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["busybar-msteams"]
