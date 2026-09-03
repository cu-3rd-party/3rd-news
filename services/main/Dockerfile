# Build context is the repository root, so the shared contracts package can be
# installed from source: docker build -f services/main/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/main/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/contracts /srv/packages/contracts
RUN pip install --no-cache-dir /srv/packages/contracts

COPY services/main/app ./app
COPY services/main/migrations ./migrations
COPY services/main/alembic.ini ./alembic.ini
COPY services/main/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["api"]
