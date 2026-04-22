# AI Reservation — Backend

FastAPI backend for the AI Receptionist SaaS.

## Requirements

- Python 3.12+
- A Supabase project (for PostgreSQL + pgvector)

## Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy env template and fill in real values
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL, DATABASE_URL_SYNC,
# JWT_SECRET_KEY, and PLATFORM_ENCRYPTION_KEY
```

### Generate required secret values

```bash
# JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(64))"

# PLATFORM_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Run

```bash
uvicorn app.main:app --reload
```

API is available at `http://localhost:8000`.
Interactive docs at `http://localhost:8000/docs` (dev mode only).
Health check: `http://localhost:8000/health`

## Database migrations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe change"
```

## Tests

```bash
pytest
```

## Lint + type check

```bash
ruff check app/
ruff format app/
mypy app/
```
