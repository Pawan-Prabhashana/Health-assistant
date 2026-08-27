# syntax=docker/dockerfile:1

# ---- Build stage: resolve and install dependencies into a venv with uv ----
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install third-party dependencies first for maximum layer caching. The project
# source is copied afterwards so editing code does not invalidate the deps layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- Runtime stage: slim image with only the venv and source ----
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/huggingface/fastembed \
    TIKTOKEN_CACHE_DIR=/app/.cache/huggingface/tiktoken

# Create an unprivileged user to run the service and pre-create the model cache
# directories so the reserved hf_cache volume (mounted at /app/.cache/huggingface
# for the local MiniLM embedder and the tokenizer) inherits writable ownership on
# first mount.
RUN groupadd --system --gid 1001 sahana \
    && useradd --system --uid 1001 --gid sahana --no-create-home sahana \
    && mkdir -p /app/.cache/huggingface/fastembed /app/.cache/huggingface/tiktoken \
    && chown -R sahana:sahana /app/.cache

WORKDIR /app

COPY --from=builder --chown=sahana:sahana /app/.venv /app/.venv
COPY --chown=sahana:sahana src ./src

USER sahana

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else sys.exit(1)"]

CMD ["uvicorn", "sahana_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
