FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml requirements.txt requirements-prefect.txt ./
COPY docs ./docs
COPY config ./config
COPY sql ./sql
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements-prefect.txt

CMD ["quant-ripper", "health"]
