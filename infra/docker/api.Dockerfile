FROM python:3.14.6-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock /app/
COPY services/api /app/services/api
COPY services/worker /app/services/worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --project services/api --frozen --no-dev

FROM python:3.14.6-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get upgrade --yes \
    && python -m pip install --no-cache-dir --upgrade pip==26.1.2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 graphview \
    && useradd --system --uid 10001 --gid graphview --home-dir /nonexistent --shell /usr/sbin/nologin graphview
WORKDIR /app
COPY --from=build --chown=graphview:graphview /app/.venv /app/.venv
COPY --from=build --chown=graphview:graphview /app/services/api /app/services/api
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/services/api/src PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["python", "-m", "uvicorn", "graphview_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
