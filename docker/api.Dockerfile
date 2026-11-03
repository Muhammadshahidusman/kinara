# Kinara API image, built with uv. Build from the Kinara folder:
#   docker compose build api
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
# dependencies first (cached layer), then the code
COPY pyproject.toml uv.lock* ./
RUN uv sync --extra api --no-dev --no-install-project
COPY src ./src
COPY config ./config
RUN uv sync --extra api --no-dev
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "kinara.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
