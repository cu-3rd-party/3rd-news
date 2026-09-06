FROM ghcr.io/astral-sh/uv:0.12.10@sha256:2bb3ebca0a796a155094a27773d290c4b074572e6107f171d88d086682fd2500 AS uv
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY packages/python/contracts packages/python/contracts
COPY services/main/pyproject.toml services/main/uv.lock services/main/
COPY services/main/lib services/main/lib
RUN --mount=type=cache,target=/root/.cache/uv uv sync --project services/main --locked --no-dev --no-editable --reinstall-package thirdnews --reinstall-package thirdnews-contracts

FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 thirdnews && useradd --uid 10001 --gid thirdnews --no-create-home thirdnews
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app/services/main
COPY services/main/main.py ./main.py
COPY services/main/alembic.ini ./alembic.ini
COPY services/main/alembic ./alembic
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "main.py"]
