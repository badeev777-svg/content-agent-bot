FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY README.md ./
RUN pip install --upgrade pip && \
    pip install -e .

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

CMD ["python", "-m", "app.main"]
