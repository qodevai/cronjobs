FROM python:3.12-alpine AS base

# The floating base tag lags Alpine's security fixes between upstream rebuilds; upgrade them
# here. Release builds run without the layer cache (docker-publish.yml), so this layer is
# never reused from an older build.
RUN apk upgrade --no-cache

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY src/ src/

# Test stage - includes dev dependencies and tests
# Use slim image for test stage to support pyright (Node.js)
FROM python:3.12-slim AS test

WORKDIR /app

# Install libatomic1 for Node.js (required by pyright)
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files from base
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY src/ src/
COPY tests/ tests/

RUN uv sync --frozen --all-extras

# Production stage - no dev dependencies
FROM base AS production
RUN uv sync --frozen --no-dev

# Health check to verify scheduler is running
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD pgrep -f "cronjob_scheduler" > /dev/null || exit 1

CMD ["uv", "run", "python", "src/cronjob_scheduler/main.py"]
