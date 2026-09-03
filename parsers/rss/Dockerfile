# Build context is the repository root: docker build -f parsers/rss/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY parsers/rss/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/contracts /srv/packages/contracts
RUN pip install --no-cache-dir /srv/packages/contracts

COPY parsers/rss/app ./app

CMD ["python", "-m", "app.main"]
