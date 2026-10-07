# syntax=docker/dockerfile:1

# Build stage: install the package with the api extra, and build the data snapshots
# (one per release of the current engine revision, extracted from the git tags).
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 /uv /bin/uv
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra api --no-install-project
COPY . .
RUN uv sync --locked --no-dev --extra api --no-editable \
    && git config --global --add safe.directory /src \
    && python scripts/build_snapshots.py --repo /src --output /opt/data

# Runtime stage: the virtual environment and the snapshots, run by an unprivileged user.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
RUN useradd --create-home --uid 10001 fakeverse
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/data /opt/data
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FAKEVERSE_DATA_DIR=/opt/data
USER fakeverse
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4)"]
# One worker: the rate limit state is local to the process. Client IPs come from
# FAKEVERSE_TRUSTED_PROXIES, so Uvicorn must not rewrite them; our JSON log replaces its own.
CMD ["uvicorn", "fakeverse.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
