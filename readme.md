# KiRa

## Overview
The `KiRa` service bundles authentication, retrieval-augmented chat, document ingestion, and
an administrative surface into a single FastAPI application.  Async SQLAlchemy models back the API, and
vector retrieval is handled through PostgreSQL with `pgvector`, alongside the optional GraphRAG
adapter that was ported from the legacy project.

## How can it be run?
Development is done in a WSL on Windows. Simply connect to a WSL:Ubuntu instance within VSCode and open the repo.

## Prerequisites
- Python 3.11+
- Docker for quick local development. Install it on the host system (Windows) and make sure Settings → Resources → WSL Integration is enabled
- Ollama or vLLM backend for LLM completions (installed to /usr/local/bin/ollama => /usr/local/bin/ollama pull ***)
- Apptainer/Singularity if you plan to build the runtime container
- PostgreSQL 13+ reachable from the application
- (Optional) DBeaver for looking at the user DB
- `pip-tools` for deterministic dependency management
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo apt install apptainer
curl -fsSL https://ollama.com/install.sh | sh
```

## 1. Clone and create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install pip-tools
```

## 2. Install dependencies via pip-tools
Dependencies are defined in layered `.in` files. Install the package you need. It is recommended to always be using the dev libraries while developing.

```bash
pip-compile requirements/base.in --verbose
pip-compile requirements/dev.in --verbose
```
Is then followed by the lockfile installation

```bash
pip-sync requirements/base.txt
pip-sync requirements/dev.txt
```

If you add new packages, update the relevant `.in` file, delete the corresponding `.txt` file and regenerate them using the `pip-compile` command



## 3. Configure environment variables
Copy the template and adjust credentials as needed:

```bash
cp .env.example .env
```

Key settings such as FastAPI secrets, PostgreSQL credentials and GraphRAG defaults are
documented in the template.  See [`.env.example`](.env.example) for the authoritative reference.

For generating a FastAPI Key, you can paste the following script into a python terminal
```bash
python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
```

### PostgreSQL configuration
For local development you can still spin up PostgreSQL with Docker if desired:

```bash
docker run \
  --name rag-postgres \
  -e POSTGRES_DB=rag_platform \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=rag_password \
  -p 5433:5432 \
  -d ankane/pgvector:latest
```

Populate the matching values in `.env` (host, port, user, password, database).  The application will
automatically build the async SQLAlchemy DSN using these fields. <br>
You can check the state of the container with `docker ps` as well as `docker logs rag-postgres`. <br>Look out for <br>`database system is ready to accept connections`

After the initial container setup, you can simply start and stop it again using 
```
docker start rag-postgres
docker stop rag-postgres
```

To reset the DB, simply use these commands
```bash
docker stop rag-postgres
docker rm rag-postgres
docker run \
  --name rag-postgres \
  -e POSTGRES_DB=rag_platform \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=rag_password \
  -p 5433:5432 \
  -d ankane/pgvector:latest
```
<br> <br>


>IMPORTANT NOTE: <br>For active development on an HPC, apptainer containers have to be built. These are currently not covered by this guide.

<br>

## 4. Run database migrations
Apply the latest schema using Alembic:

```bash
alembic upgrade head
```

The Alembic environment reads the same settings module as the API, so make sure the `.env` file is in place before running migrations.
<br>
When doing changes to the schema (which you should avoid doing), the above command has to be run again to account for these changes. Using DBeaver to inspect the changes is recommended.


## 5. Start the services
### API
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000/docs> for the interactive OpenAPI explorer. The entrypoint (`/`)
leads to the frontend `/frontend/login`. 
In the login page, you will have to authenticate yourself with a user. This triggers FastAPI-Auth-routes and generates JWT-Tokens, for which only one can be active per UID. Only after authentication, you can access the following routes.

### Seed sample data
When setting up the DB, you will have to run the seeding script to create a default admin. Otherwise, you won't be able to create other accounts, even through the openAPI endpoint:

```bash
python scripts/seed_database.py
```

To see the credentials, simply look under the `bootstrap` section in `.env` or or `src/config.py`. 


### Background worker
The ingestion worker polls the database for new jobs and should be launched alongside the API when you
need document processing:

```bash
python -m src.worker_main
```

## 6. Use the ingestion pipeline
The ingestion pipeline parses single files or entire directories (multi-document ingestion) with
[Docling](https://github.com/docling-ai/docling) when available, chunks page content, enriches it with
metadata (page number, chunk index, source path, collection name, original Docling metadata, …), embeds
each chunk via the configured Ollama model (`qwen3-embedding:0.6b` or `embeddinggemma`), and stores the resulting
vectors in PostgreSQL using `pgvector`.

1. **Configure embeddings** – ensure Ollama is running and expose it via environment variables (see
   `.env.example`). The defaults target a local daemon at `http://localhost:11434` and select
   `qwen3-embedding:0.6b`. Override with:

   ```bash
   export LLM__PROVIDER=ollama
   export LLM__OLLAMA_HOST=http://localhost:11434
   export LLM__EMBEDDING_MODEL=embeddinggemma  # optional alternative
   ```

   If Ollama is unavailable, the service falls back to the deterministic local embedder.

2. **Prepare your sources** – place `.pdf`, `.md`, `.txt`, or `.json` files in a directory that is
   reachable from both the API and the worker. Nested directories are traversed recursively.

3. **Create an ingestion job** – authenticate against the API and submit a job specifying the source
   path and collection name:

   ```bash
   curl -X POST "http://localhost:8000/ingestion/jobs" \
     -H "Authorization: Bearer <JWT>" \
     -H "Content-Type: application/json" \
     -d '{
       "source": "/abs/path/to/documents",
       "collection_name": "product-manuals"
     }'
   ```

   The job status starts as `pending`. Each file is parsed (via Docling when possible) and chunked.

4. **Monitor progress** – query the job status at any time:

   ```bash
   curl -H "Authorization: Bearer <JWT>" \
     "http://localhost:8000/ingestion/jobs/<job_id>"
   ```

   A `success` status indicates that all chunks have been written with metadata such as
   `page_number`, `page_chunk_index`, `chunk_index`, `char_start`, `char_end`, and optional Docling
   metadata copied into the `metadata_json` column.

5. **Query collections** – list known collections to drive retrieval prompts or UI dropdowns:

   ```bash
   curl -H "Authorization: Bearer <JWT>" "http://localhost:8000/ingestion/collections"
   ```

Each ingestion job records the originating user, associates generated documents and chunks with that
job, and commits the embeddings to PostgreSQL. Retrieval flows automatically surface the stored
metadata in the context they return.

## 7. Run the test suite
```bash
pytest tests -q
```

The test harness provisions an async SQLite database in-memory, so PostgreSQL is not required when
running the automated checks.



## Optional services
- **GraphRAG workspace**: Ensure the paths defined in `.env` (e.g., `GRAPHRAG__ROOT_DIR`) point to the
  expected GraphRAG configuration directory.
- **LLM backends**: Configure `LLM__PROVIDER` (`ollama` or `vllm`) and the corresponding host/model
  names.  Without an LLM service the chat routes will return stubbed responses.

## Project structure
The FastAPI routers live under `src/`, and supporting infrastructure (database, repositories, vector
stores, LLM clients) is namespaced under `src/infrastructure`. Tests can be found in `tests/`.
The UI is defined under `src/frontend`.
