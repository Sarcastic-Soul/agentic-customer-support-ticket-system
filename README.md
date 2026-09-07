# Agentic AI Customer Support System

An AI support system that reads a customer's problem on any channel, tries to
actually solve it using the company's real order, payment and knowledge data,
and — when it cannot or should not — hands the ticket to a human with a full
context packet instead of a shrug.

Runs entirely on a laptop. No paid services.

## What makes it "agentic"

Not "an LLM with a chat window". The system:

- **Plans** — classifies intent, picks a tool group, decides whether it needs to
  retrieve knowledge or query the business database.
- **Acts** — calls typed tools against real order, shipment and transaction data,
  in a bounded loop, recovering from tool errors.
- **Verifies** — checks its own draft for groundedness, policy safety and
  completeness before anything reaches a customer.
- **Knows its limits** — refuses to act beyond authorization ceilings, escalates
  on low confidence, knowledge gaps, policy limits, abuse or legal risk.
- **Hands off well** — produces a summary, a timeline, the entities it verified,
  what it could not do, and a suggested reply and action.
- **Resumes** — the human can return the ticket to the AI with a note, and the
  agent continues from its checkpointed state.

## Architecture in one paragraph

Channel adapters (web chat, WhatsApp, email, later voice) contain no LLM; they
normalize provider payloads into one canonical `InboundMessage` and render
replies back. An ingress gateway dedupes and persists, acknowledges the webhook,
then spawns a background task. That task runs a single channel-agnostic LangGraph
state machine: prepare, classify, hard-route, plan, retrieve (hybrid RAG over
pgvector + Postgres full-text), act (bounded tool loop behind a policy layer),
verify, then respond or escalate. Escalation pauses the graph at a checkpoint,
writes a handoff packet to a priority queue, and a human agent picks it up in a
console — replying through the same channel the customer used, or handing control
back to the AI. Everything is one PostgreSQL database and one process, and every run is recorded
with its full reasoning trace for the dashboard and the evaluation harness.

Full detail: [`docs/01-architecture.md`](docs/01-architecture.md).

## Documentation

| Document | Contents |
|---|---|
| [`docs/00-plan-review.md`](docs/00-plan-review.md) | What was wrong with the first draft design and why the current one differs |
| [`docs/01-architecture.md`](docs/01-architecture.md) | Layers, diagrams, request and escalation lifecycles, process topology |
| [`docs/02-tech-stack.md`](docs/02-tech-stack.md) | Every dependency and the reason for it; repository layout |
| [`docs/03-data-model.md`](docs/03-data-model.md) | Full schema with SQL, state machine, seed data plan |
| [`docs/04-agent-design.md`](docs/04-agent-design.md) | Graph state, node by node, tool catalog, prompting, failure handling |
| [`docs/05-escalation-policy.md`](docs/05-escalation-policy.md) | Trigger table, authorization matrix, handoff packet, resume mechanics |
| [`docs/06-api-spec.md`](docs/06-api-spec.md) | REST and WebSocket surface |
| [`docs/07-build-stages.md`](docs/07-build-stages.md) | 12-week plan, definitions of done, demo scripts, cut list |
| [`docs/08-evaluation.md`](docs/08-evaluation.md) | Golden dataset, metrics, judging, ablations |
| [`docs/09-risks.md`](docs/09-risks.md) | Failure modes and mitigations |

## Stack

Python 3.13 · FastAPI 0.141 · LangGraph 1.2 · PostgreSQL 18 + pgvector 0.8.6 ·
SQLAlchemy 2.0 · Vite + React 19 + TanStack Router/Query
+ Tailwind + shadcn/ui · `gemini-3.8-flash` primary with Groq `openai/gpt-oss-120b`
fallback · local `bge-small-en-v1.5` embeddings via fastembed ·
Twilio WhatsApp sandbox · Gmail IMAP/SMTP · Parakeet TDT + Piper for voice.

Versions verified 8 September 2026. Notably **not** used: `gemini-2.5-*`
(a generation behind, and `gemini-2.0-flash` is shut down), Groq
`llama-3.3-70b-versatile` (deprecated 16 Aug 2026), and Next.js — the backend is
FastAPI, so a Node server that only renders a shell is dead weight. Reasoning in
[`docs/02-tech-stack.md`](docs/02-tech-stack.md).

## Quick start

```bash
cp .env.example .env          # add GEMINI_API_KEY and/or GROQ_API_KEY
docker compose up -d          # postgres only
make reset                    # apply schema.sql + seed synthetic data
make dev                      # api + frontend
```

- Customer web chat: http://localhost:3000/chat
- Agent console: http://localhost:3000/console
- Admin dashboard: http://localhost:3000/admin
- API docs: http://localhost:8000/docs

No API key? Set `LLM_PROVIDER=stub` for a deterministic fake model — the whole
pipeline runs offline for tests and for developing the UI.

## Scope

**This is a prototype.** One process, one database, no queue, no migrations, no
test pyramid, no CI. Rare edge-case bugs are acceptable; the demo path and the
escalation loop are not. Everything skipped is listed explicitly in
[`docs/07-build-stages.md`](docs/07-build-stages.md#deliberately-not-doing) so it
reads as a trade-off rather than an oversight.

## Project status

Blueprint stage — no code yet. See
[`docs/07-build-stages.md`](docs/07-build-stages.md) for the stage checklists and
[`docs/PROGRESS.md`](docs/PROGRESS.md) for what is actually built.
**Stage 6 is the milestone**: a complete vertical slice with escalation and the
human console. Everything after it is breadth.
