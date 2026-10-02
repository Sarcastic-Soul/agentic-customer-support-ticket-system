# Repository layout

Directory-by-directory map. Referenced from CLAUDE.md.

`backend/app/` — one directory per layer, matching the architecture paragraph
above:

- `agent/` — the LangGraph state machine; `agent/nodes/` is one file per graph
  node (`prepare`, `classify`, `hard_route`, `supervisor`, `retrieve`,
  `specialist`, `reconcile`, `commit`, `answer`, `verify`, `respond`/`escalate`),
  `agent/specialists.py` which specialist owns which intents and tools,
  `agent/prompts/` the prompt files, `agent/checkpoint.py` the psycopg
  checkpointer (import-order-sensitive, see its docstring),
  `agent/progress.py` the live progress events sent to web chat.
- `api/` — FastAPI routers (REST + WebSocket).
- `channels/` — web, WhatsApp, email, voice adapters; no LLM calls live here.
- `core/` — identity resolution, thread continuity, the ticket state machine,
  PII redaction (`core/pii.py`: regex + Presidio).
- `db/` — SQLAlchemy engine/session setup (the asyncpg pool).
- `hil/` — human-in-the-loop: escalation queue, handoff packet, console-facing
  logic.
- `ingress/` — webhook/dedupe/persist-then-enqueue entrypoints.
- `llm/` — `registry.py` (model ids from `.env` only), the per-model RPM
  pacer, and `cache.py` (Redis LLM response cache, off for live traffic).
- `models/` — SQLAlchemy ORM models.
- `policy/` — `authorize()`, the conflict rule table (`conflicts.py`) and the
  other guardrails; runs in code, not prompts.
- `rag/` — ingestion (`rag/ingest.py`, run via `make ingest`) and hybrid
  retrieval (pgvector + Postgres full-text), with a flashrank reranker
  (`rag/rerank.py`).
- `schemas/` — Pydantic request/response and tool-argument models.
- `seed/` — synthetic data (`seed/data.py`, `seed/run.py`, run via `make seed`).
- `tools/` — typed tool functions plus `tools/registry.py`.
- `voice/` — STT integration (Groq Whisper) shared by the web widget and
  WhatsApp voice notes.
- `workers/` — `arq` worker settings and cron jobs (e.g. `email_poll.py`).
- `observability.py` — optional Langfuse tracing (`make langfuse`).

`frontend/src/` — `routes/` (TanStack Router file-based routes: chat, login,
admin dashboard), `hooks/` (e.g. `useVoiceRecorder`), `lib/` (API client,
query setup). `frontend/e2e/` — Playwright tests against a mocked API
(`make e2e`).

`eval/` — `run_eval.py` and `dataset/tickets.jsonl` (`make eval`);
`eval/promptfoo/` — prompt regression checks (`make promptfoo`).

`backend/tests/` mirrors the module layout above (`test_authorize.py`,
`test_tickets.py`, `test_whatsapp.py`, etc.) rather than a `tests/unit` /
`tests/integration` split — see `docs/07-build-stages.md#testing-policy` for
which ~40 paths are actually required.

