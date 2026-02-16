FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app/src

WORKDIR /app

# System deps for psycopg/geo libs; keep minimal
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     curl     libpq-dev     && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.4

# Copy only dependency files first (better caching)
COPY pyproject.toml poetry.lock* /app/

RUN poetry config virtualenvs.create false     && poetry install --no-interaction --no-ansi --no-root

COPY src /app/src
COPY infra/db /app/infra/db
COPY scripts /app/scripts
COPY tests /app/tests
COPY alembic.ini /app/alembic.ini
COPY infra/db/migrations /app/infra/db/migrations

EXPOSE 8000

CMD ["uvicorn", "floodmvp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
