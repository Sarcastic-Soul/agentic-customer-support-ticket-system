# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An agentic AI customer support ticket system. A customer writes in on some
channel; an LLM agent tries to actually resolve the issue against real order,
payment and knowledge-base data; when it cannot or should not, it hands the
ticket to a human with a full context packet, and can take it back afterwards.

The build is done. `docs/` holds four reader docs (`README.md` at the root,
`docs/REPORT.md`, `docs/agent-orchestration.md`, `docs/architecture-overview.md`)
and `docs/decisions/` - one short file per non-obvious choice. Check the
decisions before "fixing" something that looks odd.

## What's built

- **Channels:** web chat (live progress steps while the agent works), WhatsApp
  via Twilio, Gmail email (IMAP poll + SMTP), voice notes (Groq Whisper STT).
  Each has a simulator at `/dev/simulate/*` so nothing needs a real phone or
  mailbox. Real WhatsApp/email setup is a manual step.
- **Intake:** every provider payload lands in `raw_events` first, dedupe on
  `(channel, external_message_id)`, identity resolution to a customer, PII
  redaction (Presidio + regex) into `messages.body_redacted`, then an `arq` job.
- **Agent:** one LangGraph graph (below). Three specialists - orders,
  logistics, payments - propose writes; `reconcile` settles conflicts in code;
  `commit` runs them through `authorize()`; `verify` checks groundedness before
  any reply goes out. Hybrid retrieval (pgvector + full-text, RRF, flashrank
  rerank) over the KB.
- **Fewer handoffs:** refunds over the ceiling go to an approval queue instead
  of a full handoff; the agent asks up to 2 clarifying questions before giving
  up; a human can hand a ticket back to the AI with a note.
- **Console/admin (frontend):** ticket queue, ticket detail with transcript and
  run trace ("why did the AI do that"), approvals, metrics, KB editor, login.
- **Eval:** `eval/run_eval.py` over 55 cases in `eval/dataset/tickets.jsonl`
  (outcome, tool, groundedness, LLM judge, ablations, confidence sweep);
  promptfoo regression for the classify and verify prompts; optional Langfuse
  tracing; Redis LLM response cache for reruns.
- **Tests:** ~250 backend pytest tests plus Playwright e2e with a mocked API.

## Scope: prototype tolerance, not prototype infrastructure

The most important thing to internalise, and the easiest to get wrong in both
directions. The rule is **stop polishing early, do not skip structure.**

**Tolerate — do not spend time here:**

- Rare edge-case bugs: a stray email signature in a transcript, a race needing
  three simultaneous messages, a metric off by one on a boundary.
- Imperfect quoted-text stripping in email. 80% correct is done.
- Rough UI — unstyled states, no animations, no empty-state art.
- No horizontal scale, HA, multi-tenancy, or rate limiting beyond a per-sender
  email guard.
- Do not refactor working code for elegance.

**Keep — these are not optional:**

- Redis + `arq`, the worker process, Alembic migrations.
- `raw_events`, `refunds`, `shipments`, `agent_steps`, `tool_calls` as real
  tables. The eval harness queries across them.
- PII redaction into `messages.body_redacted`.
- The escalation loop, the handoff packet, the `verify` node, the eval harness.
- Tests on the critical paths: ticket transitions, dedupe, identity resolution,
  `authorize()`, tool customer-scoping, PII, retrieval smoke.

**Genuinely out of scope:** skill-based assignment routing (the column exists;
no algorithm), SLA breach cron, CI, mypy, coverage gates,
real load testing, RFC-7807 errors, cursor pagination.

Full reasoning in `docs/decisions/0003-prototype-scope.md`. If something looks
like an oversight, check that file before "fixing" it.

Never strip infrastructure to save time — that trades a few hours for a class
of bug that is invisible until it happens during a demo.

## Non-negotiables

Short list. Everything else is negotiable; these are not, because each one either
*is* the project or prevents a class of failure that ruins a demo.

1. **`UNIQUE (channel, external_message_id)` on `messages`.** Twilio retries
   webhooks and IMAP re-delivers. Without it one customer gets answered three
   times, live, in front of an audience.
2. **`customer_id` comes from trusted state, never from model output.** Tools read
   it from `ToolContext`. This is what makes prompt injection ("show me order
   ORD-99999") harmless.
3. **`policy/authorize()` runs in code, inside the tool wrapper.** The model can
   request a refund; it cannot approve one above the ceiling. Never move this
   check into a prompt.
4. **Eligibility is read from data, never inferred.** `orders.cancellable_until`,
   `orders.return_window_ends`, `order_items.returnable`. The LLM must not reason
   about whether a window is open.
5. **The `verify` node stays.** Groundedness check before anything reaches a
   customer. It is measured in the ablation table.
6. **Model ids live only in `.env`**, read through `app/llm/registry.py`. Providers
   deprecate models with ~2 months' notice; two have already died during planning.
7. **Bounded loops.** `MAX_TOOL_CALLS = 5`, `MAX_AI_TURNS = 4`. An unbounded agent
   loop burns a free tier in under a minute.
8. **Webhooks acknowledge before doing work.** Persist the raw event, enqueue,
   return. No LLM call inside a request handler.
9. **`agent_runs`, `agent_steps` and `tool_calls` are written for every run.**
   They power the "why did the AI do that" screen and half the eval metrics.
   Highest value per line in the codebase.

## Architecture in one paragraph

Channel adapters (web, WhatsApp, email, voice) contain **no LLM** — they normalize
provider payloads to one `InboundMessage` and render `OutboundMessage` back. One
channel-agnostic LangGraph state machine does all reasoning: `prepare → classify →
hard_route → supervisor → retrieve → specialist ×1-2 (parallel) → reconcile →
commit → answer → verify → respond | escalate`. Specialists (orders, logistics,
payments) only *propose* writes; `reconcile` settles disagreements with a rule
table in code (`policy/conflicts.py`) and `commit` carries out the survivors —
see `docs/decisions/0006-specialist-agents.md`. Tools are typed
Python functions behind a policy layer. Escalation pauses the graph at
`interrupt()`; a human works it in the console and either resolves or returns
control with a note, which resumes the graph from its checkpoint. Webhooks persist
and enqueue; an `arq` worker runs the graph (and the email poll cron). One
Postgres, one Redis, two processes (`api`, `worker`).

Do **not** build per-channel agents. That was the first draft's mistake: it
duplicates the reasoning, tools and policy per channel and lets them drift.

## Commands

```bash
make up        # docker compose: postgres 18 + pgvector, redis
make migrate   # alembic upgrade head
make seed      # wipe + reseed every table, clear agent checkpoints, re-ingest KB
make ingest    # re-chunk and re-embed KB articles only
make dev       # api + worker + vite dev server
make demo      # up, migrate, seed, start, run scripts/demo_scenario.py
make test      # backend pytest
make lint      # ruff check app
make docker-up # whole stack in containers (seed/ingest still one-off)
make eval      # python eval/run_eval.py (LLM cache on; --no-cache for latency)
make promptfoo # prompt regression: classify + verify prompts (eval/promptfoo/)
make e2e       # Playwright browser tests, API mocked (frontend/e2e/)
make langfuse  # optional self-hosted tracing UI on :3001
```

`LLM_PROVIDER=stub` runs the whole pipeline offline with a deterministic fake
model — use it for UI work and anything that would otherwise burn quota.

Finer-grained, run from `backend/` with the venv active (`. .venv/bin/activate`).
The venv is `uv`-managed; after `uv sync`, run `uv pip install -e .` or pytest
fails with "No module named 'app'".

```bash
pytest                                   # all backend tests (async mode is implicit, see pyproject.toml)
pytest tests/test_authorize.py           # one file
pytest tests/test_authorize.py -k refund # one test by name
ruff check app                           # backend lint (same as `make lint`)
```

Frontend, from `frontend/`:

```bash
pnpm dev       # vite dev server alone (make dev/demo already start this)
pnpm build     # tsc -b && vite build
pnpm lint      # oxlint
```

## Repository layout

```
backend/
  app/
    main.py, config.py        FastAPI app; all settings (pydantic-settings, .env at repo root)
    logging.py, observability.py   structured logs; optional Langfuse tracing
    agent/                    LangGraph state machine
      graph.py                wires the nodes; run.py drives one run and writes agent_runs
      nodes/                  one file per node: prepare, classify, hard_route, supervisor,
                              retrieve, specialist, reconcile, commit, answer, verify,
                              respond, escalate
      specialists.py          orders / logistics / payments: tools and prompt per domain
      prompts/                every prompt as a .md file, loaded by prompts/__init__.py
      state.py, steps.py      graph state; agent_steps recording
      checkpoint.py           psycopg pool + Postgres checkpointer (thread "ticket:{id}")
      escalation.py           handoff packet (summary, what the AI tried, suggested reply)
      progress.py             live progress events for the web chat
    api/                      routes: admin, auth, console, customer, dev (simulators), kb
    channels/                 adapters, no LLM: base, web, whatsapp, email, email_parsing,
                              voice, registry
    ingress/                  raw_events -> dedupe -> identity -> PII -> enqueue (pipeline.py)
    core/                     tickets (state machine), identity, conversation, pii, auth
    policy/                   authorize() (ceilings), conflicts.py (reconcile rules),
                              triggers.py (regex hard routes, e.g. legal/fraud)
    tools/                    order/logistics/transaction tools; context.py = ToolContext;
                              registry.py wraps each tool with authorize() + tool_calls logging
    rag/                      chunk, embed (fastembed bge-small), ingest, search (hybrid), rerank
    llm/                      registry.py (provider + fallback, model ids from .env), roles,
                              cache (Redis), pricing, stub (offline fake model)
    models/                   SQLAlchemy: commerce, support, escalation, kb, observability
    db/session.py             asyncpg engine + sessions
    seed/                     data.py (synthetic customers/orders/KB), run.py (`make seed`)
    voice/stt.py              Groq Whisper transcription
    workers/                  arq settings (jobs + email cron), tasks, queue, email_poll
    hil/, schemas/            empty placeholders
  alembic/                    migrations
  tests/                      flat, one file per area (test_authorize.py, test_ingress.py, ...)
frontend/
  src/routes/                 TanStack file routes: /chat, /login, /console, /console/approvals,
                              /admin/tickets, /admin/metrics, /admin/kb
  src/pages/, src/components/ page bodies; AppShell, RunTrace, Transcript, chat/
  src/hooks/                  useWebChat (chat + progress), useVoiceRecorder
  src/lib/                    API clients (api, console-api, admin-api, auth-api), helpers
  e2e/                        Playwright specs with mocked API (mocks.ts)
eval/
  run_eval.py                 harness; dataset/tickets.jsonl (55 cases); reports/ (JSON output)
  promptfoo/                  classify + verify prompt regression
scripts/demo_scenario.py      automated half of the escalation demo
docs/                         REPORT, agent-orchestration, architecture-overview, decisions/
docker-compose.yml            postgres 18 + pgvector, redis, pgweb; `--profile app` for the app
docker-compose.langfuse.yml   optional Langfuse on :3001
```

## Stack facts that bite

- **Two Postgres pools per process, one database.** The app uses asyncpg
  (SQLAlchemy); `langgraph-checkpoint-postgres` requires psycopg 3. Intentional.
- Checkpointer connections need `autocommit=True`, `row_factory=dict_row`, and a
  one-time `.setup()`. Set `LANGGRAPH_STRICT_MSGPACK=true`.
- **Alembic is used.** Schema changes get a migration; `make migrate` applies it.
- Three processes each hold two pools (asyncpg + psycopg). Size every pool
  explicitly and small — defaults will exhaust Postgres.
- **pgvector minimum 0.8.2** — CVE-2026-3172 (parallel HNSW build overflow).
- PostgreSQL 18 does **not** have native vector search despite what several 2026
  blog posts claim. pgvector is required. Do not repeat that claim anywhere.
- Use LangGraph's `StateGraph` directly, not LangChain's `create_agent()` — this
  project needs mid-execution interrupts, which is exactly where LangChain's own
  docs say to drop down.
- Free-tier ceiling: Groq `openai/gpt-oss-120b` is 30 RPM / 1000 RPD / 200k TPD,
  **per organization, not per key**. One conversation is 3-5 LLM calls.

## Conventions

- Python 3.13, `ruff` for lint, no mypy.
- Async everywhere in the backend.
- Prompts are files in `backend/app/agent/prompts/`, never inline strings.
- Tools are `async def` with Pydantic argument models, registered in
  `tools/registry.py`, and take `ctx: ToolContext`.
- Frontend: Vite + React + TanStack Router/Query. No Next.js — see
  `docs/decisions/0001-no-nextjs.md`.
- Every external channel gets a simulator **before** the real adapter.

## Record-keeping

- **`docs/decisions/NNNN-*.md`** — one short file per non-obvious choice. Context,
  decision, reasoning, consequences. Only for choices someone might reasonably
  question later.
- **`eval/dataset/tickets.jsonl`** — a manual test worth keeping becomes a case.
- Keep the four reader docs short and plain; do not add new docs.

## Git

- Commits are authored by the user alone. Never add a `Co-Authored-By` trailer,
  a "Generated with Claude Code" line, or any other attribution.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`), under 50
  characters, body only when the "why" is not obvious.
