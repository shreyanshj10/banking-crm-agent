# Backend — Banking CRM Agent (FastAPI + LangGraph)

Async FastAPI server exposing a LangGraph tool-calling agent over two endpoints —
`POST /chat` (JSON request → reply) and `POST /chat/stream` (Server-Sent Events:
the agent's tool trace live, then the reply) — backed by PostgreSQL (async
SQLAlchemy + asyncpg).

The recommended way to run everything is **Docker** (Postgres + backend in one
command). A manual host/venv setup is also documented — it's what you use to run the
**test suite** and for local iteration. The Next.js frontend always runs on the host
(see [../frontend/README.md](../frontend/README.md)).

## Endpoints

- `GET  /health` — liveness probe.
- `POST /chat` — `{session_id, message}` → `{session_id, reply, tool_calls[], generated_messages[]}`, where each `tool_calls[]` entry is `{name, args, result}` (the agent path).
- `POST /chat/stream` — same input; streams SSE events as the agent runs:
  `tool_call` / `tool_result` (the live trace), then `final` (the reply).

OpenAPI docs: <http://localhost:8000/docs>.

---

## A. Run with Docker (recommended)

**Prerequisites:** Docker + Docker Compose, and an **Anthropic API key**.

From the **repo root**:

```bash
cp backend/.env.example backend/.env     # then edit backend/.env and set ANTHROPIC_API_KEY
docker compose up --build
```

This starts two services:

- `db` — PostgreSQL 16 (auto-creates the `crm` role and `banking_crm` database, so no
  manual DB setup is needed).
- `backend` — built from `backend/Dockerfile`; waits for a healthy `db`, runs
  `alembic upgrade head`, seeds synthetic data, then serves the API on
  <http://localhost:8000> (docs at `/docs`).

Compose reads `backend/.env`; `DATABASE_URL` is overridden to reach Postgres at the
`db` service automatically, so you only need to fill `ANTHROPIC_API_KEY`.

```bash
docker compose down        # stop (data persists in the named volume)
docker compose down -v     # stop and wipe the data volume
```

If `5432`/`8000` are already taken on your host:

```bash
POSTGRES_HOST_PORT=5433 BACKEND_HOST_PORT=8001 docker compose up --build
```

### Run the tests in Docker

A dedicated, profile-gated `test` service runs the suite inside the image against the
Dockerized Postgres (it migrates + seeds, then runs `pytest`):

```bash
docker compose run --rm test
```

---

## B. Run on the host (manual — and the path for tests)

**Prerequisites:** Python 3.11+, a local PostgreSQL 12+ on `localhost:5432`, and an
Anthropic API key. Commands run from this `backend/` directory.

### 1. Create the database role and database

The app connects with `DATABASE_URL` from `.env`, which defaults to:

```
postgresql+asyncpg://crm:crm@localhost:5432/banking_crm
```

So you need a login role **`crm`** (password `crm`) and a database **`banking_crm`**
owned by it. Creating roles/databases needs PostgreSQL superuser access; on a
Debian/Ubuntu install the `postgres` admin account is reached via `sudo`:

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE crm WITH LOGIN PASSWORD 'crm';
CREATE DATABASE banking_crm OWNER crm;
GRANT ALL PRIVILEGES ON DATABASE banking_crm TO crm;
SQL
```

> Equivalent without sudo: `psql -U postgres -h localhost`, then run the three
> statements. Verify with:
> `PGPASSWORD=crm psql -h localhost -U crm -d banking_crm -c '\conninfo'`

(With Docker this whole step is unnecessary — the `db` service creates the role and
database for you.)

### 2. Create the virtualenv and install

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your real `ANTHROPIC_API_KEY`. Leave `DATABASE_URL` as the default
unless you changed the credentials in step 1. Never commit `.env`.

### 4. Migrate, seed, run

```bash
./.venv/bin/alembic upgrade head            # create the four tables
./.venv/bin/python data/generate_seed.py    # seed synthetic data (idempotent)
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

The seeder resets the four tables then inserts a fresh dataset; dates are anchored to
"now" and a few customers are deliberately strong personal-loan prospects, so the
canonical RM query returns a real shortlist.

### 5. Run the tests

```bash
./.venv/bin/python -m pytest
```

`tests/logic/` are pure deterministic unit tests (no DB). `tests/tools/` are DB-backed
and skip cleanly with an actionable message if the database isn't reachable or seeded —
so run steps 1 and 4 first for full coverage.

---

## Smoke-test the agent

Requires a valid `ANTHROPIC_API_KEY`. Non-streaming:

```bash
curl -s http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"List my top 3 customers by balance."}'
```

Streaming (watch the tool trace arrive live, then the reply):

```bash
curl -sN http://localhost:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"Find a top personal-loan prospect and draft a WhatsApp message."}'
```

## Lint & format

Ruff handles both (config in `pyproject.toml`):

```bash
./.venv/bin/ruff check .     # lint
./.venv/bin/ruff format .    # auto-format
```

Optional — enable the repo's pre-commit hooks (ruff on the backend, ESLint/Prettier on
the frontend) so they run on every commit:

```bash
pip install pre-commit && pre-commit install   # run once, from the repo root
```

## Configuration reference

All settings come from the environment / `.env` (see `.env.example`). Under Docker the
backend loads this same file and only `DATABASE_URL` is overridden (to the `db`
service host).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://crm:crm@localhost:5432/banking_crm` | Async PostgreSQL DSN (must use the `+asyncpg` driver). |
| `ANTHROPIC_API_KEY` | — (required) | Anthropic API key; env only, never hardcoded. |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | Agent model. |
| `ANTHROPIC_MESSAGE_MODEL` | `claude-opus-4-8` | Message-generation model (swap hook). |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS origin allowed for the Next.js client. |

> Do **not** add `temperature` / `top_p` / `top_k` / `budget_tokens` — they return a
> 400 on `claude-opus-4-8`.

The tool implementations live in `app/tools/`; see the [root README](../README.md)
for the tool design, the agent-path trace, and the overall architecture.
