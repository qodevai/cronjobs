FROM python:3.12-alpine AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml .
COPY uv.lock .
COPY README.md .
COPY src/ src/

# Test stage - includes dev dependencies and tests
FROM base AS test
COPY tests/ tests/
RUN uv sync --frozen --all-extras

# Production stage - no dev dependencies
FROM base AS production
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "cronjob-scheduler"]
