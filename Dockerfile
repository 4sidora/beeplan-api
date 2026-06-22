FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY beeplan ./beeplan

ENV PYTHONPATH=/app
EXPOSE 8000

CMD alembic upgrade head && uvicorn beeplan.main:app --host 0.0.0.0 --port 8000 --workers 4
