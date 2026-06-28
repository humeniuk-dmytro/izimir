FROM python:3.12-slim

# uv (pinned binary from the official image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 1) Dependencies only — cached layer, rebuilt only when the lockfile changes.
#    --no-install-project: project code isn't here yet, install just the deps.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Project code, then install the package itself.
COPY src/ src/
RUN uv sync --frozen --no-dev

# Run without a runtime sync (everything is already installed at build time).
CMD ["uv", "run", "--no-sync", "python", "-m", "izimir"]
