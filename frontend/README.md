# Frontend — Banking CRM Chat Client (Next.js)

A minimal single-page Next.js chat client — a thin client over the backend's chat
API. It renders the agent's Markdown replies and, under each reply, the **agent path**:
the tools the agent called, with their inputs and results. Over the streaming endpoint
that trace appears **live** as the agent works. All logic lives in the backend.

Commands run from this `frontend/` directory.

## Prerequisites

- **Node.js 18+** and npm
- The **backend running** (see [../backend/README.md](../backend/README.md)) — the UI
  is useless on its own.

## 1. Install dependencies

```bash
npm install
```

## 2. Configure the backend URL

```bash
cp .env.example .env.local
```

`.env.local` sets where the client sends chat requests (no trailing slash):

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Keep this origin in sync with the backend's `FRONTEND_ORIGIN` (CORS) — the defaults
already match for local dev.

## 3. Run the dev server

```bash
npm run dev
```

Open <http://localhost:3000> and chat. Ensure the backend is up on `:8000` first
(`docker compose up --build` from the repo root, or the host setup in the backend
README); otherwise requests fail with a connection error.

## What you'll see

- Ask a question (or click a suggested prompt). The reply renders as Markdown.
- Below the reply, an **agent path** panel shows the tools the agent ran — each with
  its arguments and a short result summary; repeated tools are grouped (`×N`).
- While the agent works, the client streams from `POST /chat/stream`: "Agent is
  processing…" appears, the trace fills in tool by tool, then the full reply replaces
  the processing note. The client also speaks `POST /chat` (non-streaming) for the
  same result.
- Conversation memory is per browser tab (a `session_id` is persisted), so follow-up
  questions keep context.

## How it talks to the backend

- `POST ${NEXT_PUBLIC_API_BASE_URL}/chat/stream` — Server-Sent Events; the client
  reads the stream and renders the trace + reply incrementally.
- `POST ${NEXT_PUBLIC_API_BASE_URL}/chat` — JSON request/response.

## Lint & format

```bash
npm run lint           # ESLint (next lint)
npm run format         # Prettier — write
npm run format:check   # Prettier — check only
```

## Production build (optional)

```bash
npm run build
npm run start
```
