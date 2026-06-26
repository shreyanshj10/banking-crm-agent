# Implementation Plan

Ordered, small, independently verifiable steps. **Run each step's verification gate and
show it passing before moving to the next.** Build order:
DB + migrations + generator → logic → tools → agent graph → FastAPI `/chat` (verified via
curl/docs) → Next.js → docker-compose → README.

---

## Step 0 — Project scaffold + config
- Create `backend/` with `pyproject.toml`. Deps: fastapi, uvicorn, `sqlalchemy[asyncio]`,
  asyncpg, alembic, langgraph, langchain-anthropic, pydantic-settings, pytest,
  pytest-asyncio.
- `app/config.py` — pydantic-settings reading from env:
  - `DATABASE_URL` (async form: `postgresql+asyncpg://...`)
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_MODEL` (default `claude-opus-4-8`)
  - `ANTHROPIC_MESSAGE_MODEL` (default `claude-opus-4-8`)
- `.env.example` documenting every var. No secrets committed.
- **Model rule (applies wherever `ChatAnthropic` is constructed):** the model string is
  the bare dateless ID `claude-opus-4-8` (no date suffix). **Never pass `temperature`,
  `top_p`, `top_k`, or `budget_tokens`** — they return a 400 on Opus 4.8. Key from env.
- **Verify:** create a local Postgres DB; `python -c "from app.config import settings;
  print(settings.database_url, settings.anthropic_model)"` loads from a real `.env` with
  no hardcoded values.

## Step 1 — SQLAlchemy models + async engine
- `app/db/connection.py` — async engine + `async_sessionmaker` built from `DATABASE_URL`
  (asyncpg). No sync engine anywhere.
- `app/db/models.py` — `customers`, `products`, `holdings`, `transactions` (FKs, types,
  key fields per the data model).
- **Verify:** `python -c "from app.db.models import Base; print(Base.metadata.tables.keys())"`
  lists all four tables; import succeeds.

## Step 2 — Alembic (async) + initial migration
- Bootstrap with the **async template**: `alembic init -t async migrations` — do not
  hand-convert the sync template.
- Edit the generated `env.py`:
  - Set `target_metadata = Base.metadata` (import our models' `Base`). Default is `None`
    → autogenerate produces empty migrations.
  - Feed the URL from settings, not `alembic.ini`: before building the engine,
    `config.set_main_option("sqlalchemy.url", settings.database_url)`. Keep
    `sqlalchemy.url` out of `alembic.ini` (no hardcoded secret).
  - Keep the template's async machinery intact: `do_run_migrations(connection)` stays
    **synchronous** (`context.configure(...)` + `context.run_migrations()`);
    `run_async_migrations()` uses `async_engine_from_config(..., poolclass=pool.NullPool)`
    then `await connection.run_sync(do_run_migrations)`; online mode wraps it in
    `asyncio.run(run_async_migrations())`.
- Autogenerate the initial migration from the models (creates all four tables). **No raw
  `schema.sql`.**
- **Gotchas:** the URL must use the `postgresql+asyncpg://` driver (a bare `postgresql://`
  URL fails in async `env.py`). Run migrations only as a CLI / entrypoint step — never
  from inside the running FastAPI event loop (`asyncio.run` inside a live loop errors).
- **Verify:** `alembic upgrade head` against the local DB; `\dt` in psql shows four tables
  with correct columns/FKs; `alembic downgrade base` then `upgrade head` round-trips.

## Step 3 — Synthetic data generator + seed
- `data/generate_seed.py` — async, inserts via the async session. Realistic distributions
  across income/balance/credit/segment; products catalog with eligibility; holdings
  referencing products; transactions across channels/categories.
- **Dates anchored to `now()` at seed time:** transactions/holdings spread over recent
  months *relative to run time*, with a guaranteed slice inside the current calendar
  month so "this month" filtering always returns rows whenever the evaluator runs it.
- Runs **after** migrations.
- **Verify:** run generator; in psql confirm row counts > 0 for all tables, and
  `SELECT count(*) FROM transactions WHERE date >= date_trunc('month', now())` returns > 0.

## Step 4 — Deterministic scoring logic + required smoke tests
- `app/logic/scoring.py` — **pure, deterministic, no LLM, no DB**: takes customer /
  transaction / holding / product data structures in, returns `{score, band, reasons[]}`.
  Reasons human-readable.
- `app/logic/recommendation.py` — pure product-fit logic.
- `tests/test_scoring.py` — **required** smoke tests: known input → expected score band +
  presence of expected reason strings; eligibility edge cases; idempotency.
- **Verify:** `pytest tests/test_scoring.py` passes; functions importable with zero
  DB/network dependency.

## Step 5 — Parameterized SQL queries layer
- `app/db/queries.py` — async functions backing each data tool, all **parameterized** (no
  string concatenation): customer filtering, transactions-by-range, products,
  holdings-by-customer.
- **Verify:** a scratch async script calls each query against the seeded DB and prints
  rows; confirm `query_customers(min_income=...)` filters in SQL and
  `get_transactions(date_range=this_month)` returns current-month rows.

## Step 6 — LLM-facing tools (all async)
- `app/tools/data_tools.py` — `query_customers`, `get_transactions`, `get_products`,
  `get_holdings` (wrap Step 5).
- `app/tools/scoring_tool.py` — `score_customer` (fetches data, calls `logic/scoring`).
- `app/tools/recommend_tool.py` — `recommend_product`.
- `app/tools/messaging_tools.py` — `generate_message` (LLM-driven, personalized to fetched
  data, uses `ANTHROPIC_MESSAGE_MODEL`), `send_whatsapp` (mocked, clearly labeled in
  output).
- All tools are **async** with explicit input/output schemas (the approved schemas).
- **Verify:** scratch async script `await`s each tool with sample args against the seeded
  DB; `score_customer` returns score + reasons; `generate_message` returns text
  referencing real customer attributes.

## Step 7 — LangGraph agent (async tool execution)
- `app/agent/state.py` — `AgentState` with `messages` + `add_messages`.
- `app/agent/prompts.py` — RM-assistant system prompt: tool catalog, when to use each, no
  fabrication, minimal tool use per query.
- `app/agent/graph.py` — build an **explicit `StateGraph`** (agent node + `ToolNode`,
  conditional edge for the tool loop). **Do not use the deprecating `create_react_agent`
  prebuilt** — the explicit graph is clearer for the demo and avoids depending on an API
  mid-deprecation.
  - Agent node: `ChatAnthropic(model=settings.anthropic_model)` (no sampling params; key
    from env) with tools bound via `.bind_tools([...], strict=True)`.
  - `ToolNode`: set `handle_tool_errors` **explicitly** so a failing/slow tool surfaces
    predictably (relevant to the timeout test below).
  - In-memory `MemorySaver` keyed by `thread_id`.
- **Async wiring (load-bearing):** drive the graph with `ainvoke` / `astream` only.
  ToolNode then dispatches each async tool via its async path. **No sync entry point to
  the graph** — async-only LangChain tools raise
  `NotImplementedError("StructuredTool does not support sync invocation.")` if the graph
  is ever invoked synchronously (`.invoke()`). Every call site uses `ainvoke`.
- **Verify:** scratch async runner invokes the graph with the canonical query → observe it
  call several tools and return a shortlist + messages; invoke "Why did customer X rank
  high?" → observe it call **only** the scorer-related tools (proves dynamic,
  non-pipeline tool selection).

## Step 8 — FastAPI `/chat`, verified via curl/docs
- `app/main.py` — async app factory, DB lifespan (engine init/dispose).
- `app/api/routes/chat.py` — async `POST /chat {session_id, message}` → maps `session_id`
  to graph `thread_id`, runs agent via `ainvoke`, returns reply (+ structured artifacts
  like shortlist/messages). A streaming `POST /chat/stream` (Server-Sent Events) variant
  drives the same agent via `astream`, emitting tool calls/results live for the client's
  agent-path trace.
- **Verify (end-to-end backend gate — before any frontend):** `uvicorn` up; via `/docs`
  and `curl`, run all demo use cases (full find+message; "why did X rank high"; cross-sell
  recommend; top-N list). Same `session_id` across two calls shows memory continuity.

## Step 9 — Minimal Next.js chat client
- Single-page chat UI: message list + input, talks to `/chat/stream` with a generated
  `session_id`, renders replies and the live agent-path trace. Thin client only — no
  business logic. API base URL from env, not hardcoded.
- **Verify:** run dev server, type the canonical query, see the shortlist + messages
  render; follow-up "why did the top one rank high?" works in the same session.

## Step 10 — docker-compose (PostgreSQL + backend)
- `docker-compose.yml` at the repo root running the local stack:
  - `db`: **PostgreSQL** (`postgres:16`), `POSTGRES_USER=crm` / `POSTGRES_PASSWORD=crm`
    / `POSTGRES_DB=banking_crm`, a named volume for persistence, `pg_isready` healthcheck.
  - `backend`: FastAPI app built from `backend/Dockerfile`; waits for a healthy `db`,
    runs `alembic upgrade head` then the seed, then `uvicorn` on `:8000`. `DATABASE_URL`
    targets the `db` service and `ANTHROPIC_API_KEY` is passed from the environment.
- The Next.js frontend runs on the host (documented separately).
- **Verify:** from a clean checkout with `.env` filled, `docker compose up` brings up a
  healthy Postgres and a migrated + seeded backend; `/chat` answers the canonical query
  end-to-end.

## Step 11 — README + final pass
- README: architecture diagram, execution flow, tool design/usage, key decisions,
  trade-offs/limitations (heuristic-not-ML, in-memory memory, mocked WhatsApp), setup/run
  instructions.
- **Verify:** a fresh reader can follow setup → run → reproduce the demo use cases. No
  secrets committed, `.env.example` complete, `pytest` green.

---

## Key checkpoints
- **Step 2** — async Alembic `env.py` (the fiddliest part; async driver URL + `run_sync`
  bridge + `target_metadata`).
- **Step 7** — async `ainvoke` tool wiring and **no sync entry point** (where async
  correctness most easily breaks).
- **Step 8** — backend must be fully proven before Next.js.
