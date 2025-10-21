# rag-platform

## Overview
The `rag-platform` service bundles authentication, retrieval-augmented chat, document ingestion, and
an administrative surface into a single FastAPI application.  Async SQLAlchemy models back the API, and
vector retrieval can be delegated either to a standard Milvus-powered RAG flow or to the GraphRAG
adapter that was ported from the legacy project.

## Can I run it now?
Yes – the current codebase boots end-to-end with PostgreSQL, and optional integrations (Milvus,
GraphRAG workspace, Ollama/vLLM) can be enabled gradually.  Follow the quick-start steps below to
launch the API and worker locally.

## Prerequisites
- Python 3.11+
- PostgreSQL 13+ reachable from the application
- (Optional) Milvus for vector storage
- (Optional) Ollama or vLLM backend for LLM completions
- (Optional) GraphRAG workspace on disk if you plan to use the GraphRAG strategy
- `pip-tools` for deterministic dependency management

## 1. Clone and create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pip-tools
```

## 2. Install dependencies via pip-tools
Dependencies are defined in layered `.in` files and compiled into lockfiles (`requirements/*.txt`).
Use `pip-sync` to install from the desired lockfile:

```bash
# for local development
pip-sync requirements/dev.txt

# minimal production/runtime footprint
# pip-sync requirements/prod.txt
```

If you add new packages, update the relevant `.in` file and regenerate the lockfiles:

```bash
pip-compile requirements/base.in
pip-compile requirements/prod.in
pip-compile requirements/dev.in
```

## 3. Configure environment variables
Copy the template and adjust credentials as needed:

```bash
cp .env.example .env
```

Key settings such as FastAPI secrets, PostgreSQL credentials, Milvus host, and GraphRAG defaults are
documented in the template.  See [`.env.example`](.env.example) for the authoritative reference.

### PostgreSQL configuration example
You can spin up a disposable PostgreSQL instance with Docker:

```bash
docker run \
  --name rag-postgres \
  -e POSTGRES_DB=rag_platform \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=rag_password \
  -p 5432:5432 \
  -d postgres:15
```

Populate the matching values in `.env` (host, port, user, password, database).  The application will
automatically build the async SQLAlchemy DSN using these fields.

## 4. Run database migrations
Apply the latest schema using Alembic:

```bash
alembic upgrade head
```

The Alembic environment reads the same settings module as the API, so make sure your `.env` file is
in place before running migrations.

## 5. Start the services
### API
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000/docs> for the interactive OpenAPI explorer.  The frontend router also serves
a login and dashboard flow at `/frontend`.

### Background worker
The ingestion worker polls the database for new jobs and should be launched alongside the API when you
need document processing:

```bash
python -m src.worker_main
```

## 6. Run the test suite
```bash
pytest tests -q
```

The test harness provisions an async SQLite database in-memory, so PostgreSQL is not required when
running the automated checks.

## Optional services
- **Milvus**: Update `MILVUS__HOST`, `MILVUS__PORT`, and related settings to point to your vector
  database.  Until Milvus is available, the RAG strategy will operate in a placeholder mode.
- **GraphRAG workspace**: Ensure the paths defined in `.env` (e.g., `GRAPHRAG__ROOT_DIR`) point to the
  expected GraphRAG configuration directory.
- **LLM backends**: Configure `LLM__PROVIDER` (`ollama` or `vllm`) and the corresponding host/model
  names.  Without an LLM service the chat routes will return stubbed responses.

## Project structure
The FastAPI routers live under `src/`, and supporting infrastructure (database, repositories, vector
stores, LLM clients) is namespaced under `src/infrastructure`.  Tests are available in `tests/`, while
`templates/index.html` powers the login + dashboard UI served by the frontend router.

## Troubleshooting
- Verify the API can reach PostgreSQL using the DSN printed in the startup logs.
- Ensure Alembic migrations ran successfully before creating users or ingestion jobs.
- When optional dependencies (Milvus, GraphRAG, Ollama) are unavailable, the code falls back to safe
  placeholders; enable them incrementally and update `.env` accordingly.
