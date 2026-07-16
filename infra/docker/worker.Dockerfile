FROM python:3.14.6-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock /app/
COPY services/api /app/services/api
COPY services/worker /app/services/worker
RUN uv sync --project services/worker --frozen --no-dev

FROM python:3.14.6-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get upgrade --yes \
    && python -m pip install --no-cache-dir --upgrade pip==26.1.2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 graphview \
    && useradd --system --uid 10001 --gid graphview --home-dir /nonexistent --shell /usr/sbin/nologin graphview
WORKDIR /app
COPY --from=build --chown=graphview:graphview /app/.venv /app/.venv
COPY --from=build --chown=graphview:graphview /app/services/api/src /app/services/api/src
COPY --from=build --chown=graphview:graphview /app/services/worker/src /app/services/worker/src
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/services/api/src:/app/services/worker/src PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 10001:10001
CMD ["python", "-m", "graphview_worker"]
