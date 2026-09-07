# Tech Stack

Verified against upstream sources on **8 September 2026**. Every version below was
checked; see `docs/decisions/` for the reasoning behind contested choices.

Constraint: **no paid services**. Everything runs locally via Docker; the only
external calls are to free LLM API tiers, and there is a local stub so the whole
pipeline runs with no key at all.

---

## Corrections from the first draft

The first draft of this document named several things that are deprecated, shut
down, or a poor fit. Recorded here so the same mistakes are not repeated:

| First draft said | Reality (Sept 2026) | Now using |
|---|---|---|
| `gemini-2.5-flash` primary | Legacy generation; `gemini-2.0-flash` is fully shut down | `gemini-3.8-flash` |
| Groq `llama-3.3-70b-versatile` fallback | **Deprecated 16 Aug 2026** | `openai/gpt-oss-120b` |
| PostgreSQL 16 | 18 is current stable (19 in beta) | PostgreSQL 18 |
| Next.js 15 dashboard | See below — SSR is dead weight here | Vite + React + TanStack Router |
| `faster-whisper base.en` for voice | Parakeet TDT beats Whisper large-v3 at a quarter the size | Parakeet primary, faster-whisper fallback |

Also worth knowing: several blogs claim **PostgreSQL 18 ships native vector
search in core**. It does not — the PG18 release notes contain no reference to
vector types, HNSW or IVFFlat. `pgvector` is still required. That claim is SEO
noise and it appeared high in search results, so do not repeat it in the report.

---

## Backend

| Concern | Choice | Version (Sept 2026) | Why |
|---|---|---|---|
| Language | Python | **3.13** | 3.14 is out and both FastAPI and SQLAlchemy support it, but ONNX Runtime / CTranslate2 (embeddings, STT) still lag. 3.13 is the boring choice; revisit at Stage 10. Do **not** use the free-threaded `3.14t` build — nothing in this stack benefits and half the wheels are missing. |
| Web framework | FastAPI + Uvicorn | **0.141.1** | Async, Pydantic-native, auto OpenAPI. |
| Agent runtime | LangGraph | **1.2.11** | Explicit state graph, durable checkpoints, `interrupt()` / `Command(resume=...)`. |
| Checkpointer | `langgraph-checkpoint-postgres` | **3.1.2** | See the psycopg note below. |
| LLM adapters | `langchain-google-genai`, `langchain-groq` | current | Uniform message/tool interface so the provider is a config value. |
| ORM | SQLAlchemy (async) | **2.0.52** | No Alembic — `schema.sql` + `make reset`. Synthetic data, one developer. |
| DB drivers | `asyncpg` **and** `psycopg[binary,pool]` 3.2+ | | Both, deliberately — see below. |
| Validation / config | Pydantic v2 + `pydantic-settings` | | |
| Background work | `asyncio.create_task` | stdlib | No Redis, no queue, no worker process. See `01-architecture.md`. |
| Auth | `python-jose` JWT + `argon2-cffi` | | Local, free, enough for an admin console. |
| Testing | `pytest`, `pytest-asyncio` | | ~15 smoke tests, not a test pyramid. The eval harness is the real regression net. |
| Lint | `ruff` | | No mypy — it costs more time than it saves at this size. |

### LangChain 1.x vs LangGraph — use LangGraph directly

Since LangChain 1.0, `create_agent()` runs *on* LangGraph. It is the faster path
for a plain tool-calling agent, and it is the wrong abstraction here: this project
needs to intercept state mid-execution, pause for human approval, and resume days
later. That is precisely the line where the LangChain docs themselves tell you to
drop to LangGraph. Use `create_agent` for nothing; build the `StateGraph`.

### Two Postgres drivers is not an accident

`langgraph-checkpoint-postgres` 3.1.2 requires **psycopg 3.2+**, while SQLAlchemy
async is conventionally run on **asyncpg**. Rather than fight it, run both: the
application owns an asyncpg engine, and the checkpointer owns its own psycopg
pool against the same database. Two pools, one database. Size them together or
Stage 12's load test will find you.

Manual psycopg connections for the checkpointer need `autocommit=True` and
`row_factory=dict_row`, and `.setup()` must be called once to create the
checkpoint tables. Also set `LANGGRAPH_STRICT_MSGPACK=true`, which restricts
checkpoint deserialization to safe types.

### No queue, and no Redis

The first draft used Redis + `arq`. Dropped: at prototype scale the queue buys
durability and horizontal scale, neither of which this project needs, in exchange
for two extra processes and a Docker service. Message handling is
`asyncio.create_task(handle_message(message_id))` after the message row is
committed — the webhook still acks in milliseconds, which was the actual
requirement. Retry lives in `llm/registry.py`, where the thing that actually fails
is. Per-conversation concurrency is a `dict[int, asyncio.Lock]`.

Cost of this choice: work in flight is lost if the process restarts. Accepted.

`handle_message(message_id)` is deliberately shaped like a job function, so adding
`arq` or `taskiq` later is an afternoon, not a rewrite. (For reference if you ever
do: `arq` 0.28.0 is maintenance-only; `taskiq` is the actively developed option.)

---

## Data

| Concern | Choice | Version | Notes |
|---|---|---|---|
| Primary DB | PostgreSQL | **18** (18.6) | Current stable. PG19 is in Beta 3 — do not use it. |
| Vector search | `pgvector` | **0.8.6** | Still required; not in PG core. Minimum **0.8.2** regardless: earlier versions have CVE-2026-3172, a buffer overflow in parallel HNSW builds that can leak data from other relations. 0.8.x also brings iterative scans for filtered queries, parallel HNSW builds and `halfvec`. |
| Keyword search | Postgres `tsvector` + GIN | | Second half of hybrid retrieval. Order numbers and error codes are exactly what dense embeddings miss. |


Docker image: `pgvector/pgvector:pg18`. That plus the schema file is the entire
`docker-compose.yml`.

---

## Models

Two providers, automatic fallback, plus an offline stub. Both free tiers are real
but small — design for the rate limit, not around it.

### Text models

| Role | Primary (Gemini) | Fallback (Groq) | Notes |
|---|---|---|---|
| Classification / routing | `gemini-3.5-flash-lite` | `openai/gpt-oss-20b` | Called on every message. Free tier on both. Paid reference: $0.30/$2.50 per 1M. |
| Main reasoning + tool calling | `gemini-3.8-flash` | `openai/gpt-oss-120b` | Newest Flash, free tier, 1M context. Paid reference: $0.75/$3.75 per 1M through Dec 2026 (doubles Jan 2027). |
| Verify / groundedness | `gemini-3.5-flash-lite` | `openai/gpt-oss-20b` | Strict JSON verdict. |
| Summarize (handoff packet) | `gemini-3.8-flash` | `openai/gpt-oss-120b` | Once per escalation. |
| Judge (evaluation only) | — | `openai/gpt-oss-120b` | Deliberately a *different* provider from the system under test, to blunt self-preference bias. |

Do **not** use: `gemini-2.0-flash` / `gemini-2.0-flash-lite` (shut down),
`llama-3.3-70b-versatile` / `llama-3.1-8b-instant` (Groq deprecated them
16 Aug 2026), `meta-llama/llama-4-maverick-*` (deprecated March 2026).
`gemini-2.5-flash` still exists but is a generation behind — no reason to pick it.
`gemini-3.1-pro-preview` is paid-only; avoid.

**Known free-tier ceiling.** Groq free tier for `openai/gpt-oss-120b`:
30 requests/min, 1000 requests/day, 8k tokens/min, 200k tokens/day — and limits
are per organization, not per key, so extra keys buy nothing. Gemini free-tier
limits are account-specific and visible in AI Studio; check yours before the demo.
A single support conversation costs 3-5 LLM calls, so 1000 RPD is roughly
200-300 conversations. That is enough for development and a demo, and *not*
enough for the Stage 12 load test — run that against `LLM_PROVIDER=stub`.

### Embeddings — local, no API

| Choice | Dim | Size | Notes |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` via `fastembed` (ONNX) | 384 | 67 MB | Default. CPU-only, offline after first download, no rate limit. Re-embedding the whole KB must never depend on someone's quota. |
| `BAAI/bge-m3` | 1024 | ~2 GB | Swap to this **if** Hinglish / multilingual retrieval turns out to matter — the eval set has Hinglish cases, so test before deciding. Costs a migration: `vector(384)` to `vector(1024)` plus a full re-embed. |

EmbeddingGemma-300M is the interesting 2026 small model, but the Python
`fastembed` supported-model list does not carry it (the Rust crate does). Not
worth adding a `sentence-transformers` + PyTorch dependency tree for it. Revisit
only if retrieval recall stalls below target in Stage 3.

Reranking: skipped. Hybrid search is adequate and a cross-encoder adds a
dependency and latency for a small win.

### Speech (Stage 10, deferred)

| Role | Choice | Notes |
|---|---|---|
| STT primary | **NVIDIA Parakeet TDT 0.6B v3** | Beats Whisper large-v3 on the Open ASR Leaderboard (6.32% vs 7.44% WER) at a quarter the size, runs far faster on plain CPU, and does not hallucinate on silence — which matters, because customer voice notes are mostly silence and background noise. |
| STT fallback | `faster-whisper` (`distil-large-v3`) | For languages Parakeet does not cover. Route by detected language. |
| STT API fallback | Groq `whisper-large-v3` | If local inference is too slow on the demo machine. |
| TTS | `piper` | Local, free, good enough for a spoken reply. |

### Provider abstraction

One module, no exceptions:

```python
# app/llm/registry.py
def get_llm(role: LLMRole, *, structured: type[BaseModel] | None = None) -> BaseChatModel
```

It reads `settings.llm_profiles[role]`, wraps retry-with-jitter, falls back to the
secondary provider on 429/5xx, records tokens/latency/cost into `agent_steps`, and
honours `LLM_PROVIDER=stub` for offline runs. Model ids appear in `.env` and
nowhere else. Providers deprecate models with about two months' notice — this
project has already been bitten once on paper, and the abstraction is why that
cost a config line instead of a refactor.

---

## Frontend — changed: **Vite + React + TanStack Router**, not Next.js

The draft said Next.js. On review that is the wrong tool for *this* application.

**What we are actually building:** an auth-gated agent console and admin
dashboard. Every screen is behind a login. There is no SEO, no public content, no
first-paint requirement, no marketing page. The data is live — WebSocket ticket
updates, a queue that reorders itself, filters that change constantly.

**Why not Next.js.** Next.js's value is its server: SSR, server components,
server actions, route handlers, caching. Our server is FastAPI, in Python. Adopting
Next.js means running a Node process whose only job is to render a shell and
proxy to Python, plus reasoning about which half of every component tree runs
where, plus two deployment targets instead of one. That is real cost for a
capability the app never uses.

**Why not TanStack Start either.** Start v1 is stable and good, but it is also a
*full-stack* framework — the same server-side capability we just said we do not
need. Choosing it would repeat the mistake with a newer logo.

**What we use.** A plain SPA:

| Concern | Choice |
|---|---|
| Build | Vite + React 19 + TypeScript |
| Routing | **TanStack Router** — end-to-end typed routes and, more importantly, typed *search params* |
| Server state | TanStack Query |
| Styling | Tailwind + shadcn/ui |
| Charts | Recharts |
| Live | Native WebSocket to FastAPI |

Typed search params are not a nicety here: the ticket queue and dashboard are
mostly filter state (`?status=escalated&priority=P1&channel=whatsapp&since=...`),
and TanStack Router validates and types that state instead of leaving it as
stringly-typed `URLSearchParams`. Shareable filtered views come free, which the
agent console genuinely wants ("here's the queue view I'm looking at").

The build output is static files. FastAPI serves them in production; Vite's dev
server proxies `/api` in development. One process, one language on the server.

**When this would be wrong:** if the project needed a public marketing site, SEO,
or server-rendered customer pages. It does not — the customer-facing surface is a
WhatsApp thread, an email, and a small embeddable chat widget.

The customer chat widget is a second tiny Vite entry point (`/chat`), so Stage 2
has a working channel with no external dependency.

---

## External channel providers

| Channel | Provider | Real cost | Gotchas |
|---|---|---|---|
| WhatsApp | Twilio **Sandbox** | Free to use, but trial accounts include only ~100 WhatsApp messages of credit; after the trial credit is gone, messages bill at standard rates | Shared sandbox number; every tester must send the join code first; 24-hour service window applies |
| WhatsApp (alt) | Meta WhatsApp Cloud API | Customer-initiated *service* conversations have been free since Nov 2024 — **but from 1 October 2026 utility and service messages inside the service window become chargeable** | Requires a Meta Business account and app review. Higher setup cost, and the free window is closing three weeks from now |
| Public tunnel | `cloudflared` quick tunnel | Free | URL changes on restart — keep it in config, never in code |
| Email | Gmail IMAP + SMTP, app password | Free | Needs 2FA on the account. Use a dedicated throwaway address, never a personal one. Poll every 30-60s |
| Voice | none — local files | Free | Asynchronous voice notes, not telephony |

Given the 1 October 2026 change, **stay on the Twilio sandbox** and treat WhatsApp
as a demo channel, not a production one. Note the pricing change in the report; it
is a legitimate finding about the platform, not a gap in the project.

**Every external channel must have a simulator.** `POST /dev/simulate/{channel}`
injects a synthetic `InboundMessage` so the whole pipeline runs with the network
unplugged. Build the simulator *before* the real adapter, every time.

---

## Observability

| Concern | Choice |
|---|---|
| Traces | One table, `agent_runs`, with the trace in a `steps` JSONB array. Powers the dashboard and the eval harness. Required. |
| Trace UI | None. Langfuse was in the first draft; `agent_runs.steps` rendered on the ticket page covers it. |
| Logs | Standard `logging`, with `ticket_id` in the message. `structlog` is not worth the setup here. |

---

## Repository layout

```
ai-customer-support/
├─ docker-compose.yml              # postgres 18 + pgvector. That's it.
├─ Makefile                        # reset, dev, seed, demo
├─ .env.example
├─ docs/
│  └─ decisions/                   # one short file per non-obvious choice
├─ backend/
│  ├─ pyproject.toml
│  ├─ schema.sql                   # the whole schema; no migrations
│  └─ app/
│     ├─ main.py                   # FastAPI app factory
│     ├─ config.py                 # Settings
│     ├─ db/                       # asyncpg engine, session, base
│     ├─ models/                   # SQLAlchemy models
│     ├─ schemas/                  # Pydantic API + domain schemas
│     ├─ channels/
│     │  ├─ base.py                # ChannelAdapter protocol, InboundMessage
│     │  ├─ web.py  whatsapp.py  email.py  voice.py
│     │  └─ simulator.py
│     ├─ ingress/                  # webhook routes, dedupe, raw event store
│     ├─ core/                     # identity.py, conversation.py, tickets.py
│     ├─ agent/
│     │  ├─ graph.py  state.py
│     │  ├─ nodes/                 # classify, retrieve, act, verify, respond, escalate
│     │  ├─ checkpoint.py          # psycopg pool for langgraph-checkpoint-postgres
│     │  └─ prompts/               # versioned templates
│     ├─ tools/                    # registry.py, kb.py, orders.py, transactions.py, tickets.py
│     ├─ policy/                   # authorize(), pii.py, thresholds.py
│     ├─ rag/                      # ingest, chunk, embed, hybrid_search, rerank
│     ├─ llm/                      # registry, fallback, stub, cost accounting
│     ├─ hil/                      # escalation queue, handoff packet, console API
│     ├─ api/                      # dashboard + console REST/WS routes
│     ├─ tasks.py                  # handle_message(), IMAP poll loop
│     └─ seed/
├─ frontend/                       # Vite + React + TanStack Router
│  └─ src/routes/                  # /chat, /console, /admin
├─ eval/
└─ scripts/
```

---

## Deliberately excluded

- **Redis, job queues, worker processes.** One process, `asyncio` tasks.
- **Alembic.** `schema.sql` + `make reset`.
- **A test pyramid, CI, mypy, coverage gates, load testing.** ~15 smoke tests on
  ticket transitions, dedupe, identity resolution and `authorize()`; the eval
  harness catches the rest.
- **Kubernetes, cloud, managed vector DBs.** pgvector is enough at this scale.
- **CrewAI / AutoGen.** Role-play frameworks hide control flow; you need to show
  the loop in a report and debug it at 2am.
- **Fine-tuning.** Prompting plus retrieval is sufficient, and it is not free.
- **Microservices.** One backend, three process types.
- **Next.js / TanStack Start.** Reasoned above.
- **Free-threaded Python 3.14t.** Nothing here is CPU-bound in a way that helps.
- **Managed auth.** Local JWT is fine for an admin console.

---

## Version pinning policy

Pin exact versions in `pyproject.toml` and `package.json`. Record the resolved
versions and the model ids in every eval report header — an eval number without
its model id is not reproducible, and this stack has already had one model
deprecated out from under it in the drafting phase alone.
