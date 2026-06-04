FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

RUN useradd --create-home --shell /usr/sbin/nologin graphview
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY services/api /app/services/api
COPY services/worker /app/services/worker
RUN uv sync --project services/api --frozen --no-dev
ENV PYTHONPATH=/app/services/api/src
ENV PATH=/app/.venv/bin:$PATH
USER graphview

CMD ["python", "-m", "uvicorn", "graphview_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
