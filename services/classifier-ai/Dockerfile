# Build context is the repository root: docker build -f services/classifier-ai/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY services/classifier-ai/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/contracts /srv/packages/contracts
RUN pip install --no-cache-dir "/srv/packages/contracts[server]"

COPY services/classifier-ai/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
