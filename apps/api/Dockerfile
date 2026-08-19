FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# The build context is the repo root because haaland-api is a uv workspace
# member: the single source of truth for pinned versions is the root uv.lock.
# Manifests first, so a source-only change does not re-resolve dependencies.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/README.md apps/api/README.md
RUN uv sync --frozen --package haaland-api --no-install-project

COPY apps/api/ apps/api/
RUN uv sync --frozen --package haaland-api

# The dev group (pytest, mypy, import-linter) is installed on purpose: the
# Makefile's `test` and `lint` targets run those tools inside this container.
ENV PATH="/app/.venv/bin:$PATH"

# alembic.ini, pyproject.toml (pytest/ruff/mypy config), scripts/, prompts/
# and templates/ are all resolved relative to the package root.
WORKDIR /app/apps/api

EXPOSE 8000

CMD ["uvicorn", "haaland.main:app", "--host", "0.0.0.0", "--port", "8000"]
