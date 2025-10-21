# Alembic Migrations

This directory stores migration scripts for the rag-platform database schema.

## Usage

1. Ensure your environment variables are set (see `.env.example` for a template).
2. Install dependencies with `pip-compile` and `pip-sync` as documented in `requirements/`.
3. Generate a new migration after modelling changes:

   ```bash
   alembic revision --autogenerate -m "describe change"
   ```

4. Apply migrations to the configured database:

   ```bash
   alembic upgrade head
   ```

The Alembic environment automatically loads the database URL from `src.config.Settings`,
so the CLI uses the same configuration as the FastAPI application.
