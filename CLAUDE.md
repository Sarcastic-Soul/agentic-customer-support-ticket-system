# CLAUDE.md

Guidance for Claude Code (and any other agent) working in this repository.

## What this is

An agentic AI customer support ticket system. A customer writes in on some
channel; an LLM agent tries to actually resolve the issue against real order,
payment and knowledge-base data; when it cannot or should not, it hands the
ticket to a human with a full context packet, and can take it back afterwards.

**Read `docs/` before writing code.** The blueprint is complete and decisions in
it were made deliberately. Start with `docs/01-architecture.md` and
`docs/07-build-stages.md`.

## Scope: this is a prototype

The single most important thing to internalise. This project optimises for
build speed and a working demo, not for production robustness.

- Rare edge-case bugs are **acceptable**. The demo path and the escalation loop
  are not.
- Do not add tests beyond the ~15 smoke tests. The eval harness is the regression net.
- Do not add migrations, a job queue, Redis, a worker process, CI, mypy,
  coverage gates, rate limiters, or abstraction layers "for later".
- Do not refactor working code for elegance.
- `docs/07-build-stages.md#deliberately-not-doing` is the authoritative list of
  what is intentionally missing. If something on that list looks like an
  oversight, it is not — leave it alone.

When in doubt: the simpler thing that works.

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
8. **Webhooks acknowledge before doing work.** Persist, `asyncio.create_task`,
   return. No LLM call inside a request handler.
9. **`agent_runs.steps` is written for every run.** It powers the "why did the AI
   do that" screen and the eval harness. Highest value per line in the codebase.

## Architecture in one paragraph

Channel adapters (web, WhatsApp, email, voice) contain **no LLM** — they normalize
provider payloads to one `InboundMessage` and render `OutboundMessage` back. One
channel-agnostic LangGraph state machine does all reasoning: `prepare → classify →
hard_route → plan → retrieve → act → verify → respond | escalate`. Tools are typed
Python functions behind a policy layer. Escalation pauses the graph at
`interrupt()`; a human works it in the console and either resolves or returns
control with a note, which resumes the graph from its checkpoint. One Postgres,
one process.

Do **not** build per-channel agents. That was the first draft's mistake and
`docs/00-plan-review.md` explains why at length.

## Commands

```bash
make reset     # drop db, apply backend/schema.sql, seed synthetic data
make dev       # uvicorn + vite dev server
make seed      # re-seed without dropping
make demo      # reset + start + run the scripted demo scenario
make eval      # python eval/run_eval.py
docker compose up -d   # postgres 18 + pgvector, nothing else
```

`LLM_PROVIDER=stub` runs the whole pipeline offline with a deterministic fake
model — use it for UI work and anything that would otherwise burn quota.

## Stack facts that bite

- **Two Postgres pools, one database.** The app uses asyncpg (SQLAlchemy);
  `langgraph-checkpoint-postgres` requires psycopg 3. This is intentional. Keep
  both pool sizes small and explicit.
- Checkpointer connections need `autocommit=True`, `row_factory=dict_row`, and a
  one-time `.setup()`. Set `LANGGRAPH_STRICT_MSGPACK=true`.
- **No Alembic.** Schema changes mean editing `backend/schema.sql` and running
  `make reset`. Never hand-write a migration.
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

## Record-keeping while building

Three files, all cheap, all of which make the final report mostly write itself:

- **`docs/PROGRESS.md`** — update at the end of every stage. What works, what is
  knowingly broken, what was skipped. Two minutes each time.
- **`docs/decisions/NNNN-*.md`** — one short file per non-obvious choice. Context,
  decision, reasoning, consequences. Only for choices someone might reasonably
  question later.
- **`eval/dataset/tickets.jsonl`** — every manual test you run gets saved as a
  case, from Stage 3 onward. Do not leave the dataset until Stage 11.

## Git

- Commits are authored by the user alone. Never add a `Co-Authored-By` trailer,
  a "Generated with Claude Code" line, or any other attribution.
- Tag a commit at the end of each stage.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`), under 50
  characters, body only when the "why" is not obvious.
