# Build context is the repository root: docker build -f parsers/time/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY parsers/time/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/contracts /srv/packages/contracts
RUN pip install --no-cache-dir /srv/packages/contracts

COPY parsers/time/app ./app

# Состояние (выбранные каналы) переживает пересборку — это том.
VOLUME ["/data"]
EXPOSE 8000

# Ручки выбора каналов + фоновый опрос в одном процессе. Режим без HTTP,
# только по TIME_CHANNELS, остаётся доступен как `python -m app.main`.
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
