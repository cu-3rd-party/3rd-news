FROM ghcr.io/astral-sh/uv:0.12.10@sha256:2bb3ebca0a796a155094a27773d290c4b074572e6107f171d88d086682fd2500 AS uv
FROM python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv
COPY --from=uv /uv /usr/local/bin/uv
COPY packages/python/contracts packages/python/contracts
COPY services/classifier-ai/pyproject.toml services/classifier-ai/uv.lock services/classifier-ai/
COPY services/classifier-ai/lib services/classifier-ai/lib
WORKDIR /srv/services/classifier-ai
RUN uv sync --frozen --no-dev --no-editable
COPY services/classifier-ai/main.py main.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "main.py"]
