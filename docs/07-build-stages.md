# Build Stages

Prototype scope: **stop polishing early, do not skip structure.** Rare edge-case
bugs are acceptable and not worth chasing. The demo path, the escalation loop and
the infrastructure that keeps the system honest are not negotiable. See
`01-architecture.md#what-prototype-means-here` for where that line sits.

No dates, no durations. Stages are ordered by dependency, and each ends with a
checklist. Tick everything before moving on — a half-finished stage is how these
projects stall.

**Ordering principle:** one complete vertical slice first — one channel, one
domain, the orchestrator, escalation, a minimal human console. Then breadth. If
you run out of time you still have an agentic support system, just with fewer
channels.

---

## Stage 0 — Foundations

- [ ] Repo skeleton, `docker compose` with `pgvector/pgvector:pg18` and `redis`
- [ ] FastAPI app, `Settings` from `.env`, `structlog`, `/health`
- [ ] Alembic wired, first migration
- [ ] `ruff` configured (skip mypy — it costs more time than it saves here)
- [ ] `Makefile`: `up`, `migrate`, `seed`, `dev`, `demo`, `eval`

**Done when:** `make up && make migrate && make dev` from a clean clone gives a
healthy API on a migrated database.

---

## Stage 1 — Data model and seed

- [ ] All tables from `03-data-model.md` as SQLAlchemy models + migration
- [ ] `core/tickets.py` — validated status transitions
- [ ] Tests: every legal and illegal ticket transition
- [ ] Seed script with a fixed random seed; **edge cases written first**
- [ ] `POST /dev/simulate/web` stores an inbound message (no agent yet)

**Done when:** the database is seeded, and you can hand-query "orders for
customer 12 that are past their ETA" and get interesting rows back.

---

## Stage 2 — Web chat end to end, no AI

- [ ] `ChannelAdapter` protocol, `InboundMessage`, `OutboundMessage`, `ResponseStyle`
- [ ] Web adapter over WebSocket
- [ ] Minimal Vite + React `/chat` page
- [ ] Ingress: raw event persistence, dedupe on
      `(channel, external_message_id)`, identity resolution, conversation
      threading, ticket creation
- [ ] Redis + `arq` worker; message handling runs in the worker, not the request
- [ ] Tests: dedupe drops a replayed message, identity resolution maps a phone
      number to the right customer
- [ ] Echo responder, so the loop is visible

**Done when:** typing in the browser creates customer, conversation and ticket
rows, an echo comes back, and replaying the same `external_message_id` is
silently dropped.

This is the skeleton. Everything after swaps the echo for reasoning.

---

## Stage 3 — RAG pipeline

- [ ] `fastembed` with `bge-small-en-v1.5`
- [ ] Ingest: markdown → heading-aware chunks → embeddings → `kb_chunks`
- [ ] Dense search (pgvector HNSW) + sparse search (`tsvector`), fused with RRF
- [ ] Score threshold that returns **nothing** rather than something bad
- [ ] `POST /api/kb/search` debug endpoint showing dense / sparse / fused results
- [ ] ~20 hand-written retrieval queries with expected document ids

**Done when:** recall@5 is around 0.85 on those queries, and an out-of-scope
question returns an empty result instead of a low-relevance chunk.

Measure it once, then move on — do not spend days chasing the last few points.

---

## Stage 4 — Orchestrator: classify, retrieve, answer

- [ ] `llm/registry.py` — Gemini primary, Groq fallback, retry, `stub` provider,
      token/cost accounting
- [ ] LangGraph graph: `prepare → classify → retrieve → answer → respond`
- [ ] Postgres checkpointer (psycopg pool, `.setup()` called once)
- [ ] `agent_runs` and `agent_steps` written for every run
- [ ] Prompts as files in `agent/prompts/`

**Done when:** a policy question in the web chat gets a grounded, cited answer,
the run is fully visible in `agent_runs` / `agent_steps`, and removing the Gemini
key silently falls back to Groq.

Spike the checkpointer separately first — a three-node graph that pauses and
resumes. It is the least familiar piece of the stack and you do not want to be
debugging it inside the real graph.

---

## Stage 5 — Tools: orders and transactions

- [ ] Tool registry with Pydantic argument models and a `ToolContext` carrying the
      trusted `customer_id`
- [ ] Order tools and transaction tools from `04-agent-design.md`
- [ ] `act` node: bounded tool loop (max 5 calls), structured tool errors,
      `tool_calls` persisted
- [ ] `plan` node restricting the tool set per intent family
- [ ] `policy/authorize()` — refund ceiling and cancellation window
- [ ] Tests: `authorize()` decision table, and a tool called with another
      customer's order number returns nothing

**Done when:** "where is ORD-10432", "why did my payment fail" and "when will my
refund land" are answered from real rows; a large refund request is denied by
policy with a recorded reason; asking about another customer's order returns
nothing.

---

## Stage 6 — Escalation and human console — **MILESTONE**

- [ ] Deterministic trigger table + judgemental triggers
- [ ] `verify` node (grounded / answers the question / policy safe), one repair pass
- [ ] Handoff packet builder
- [ ] `escalations` table, priority queue, atomic claim (`FOR UPDATE SKIP LOCKED`)
- [ ] Console UI: queue list, work view with packet + transcript, send reply,
      return-to-AI, resolve
- [ ] `interrupt()` / `Command(resume=...)` working end to end

**Done when — the demo script runs clean:**
1. Policy question → AI answers with citations
2. Order status question → AI calls a tool, answers with real data
3. Large refund request → policy denies → escalation appears in the console
4. Human claims it, sees the packet, edits the draft, sends
5. Customer sees the human reply in the same thread
6. Human returns the ticket to the AI with a note → AI continues correctly
7. Open `agent_runs` for that ticket and show every node, tool call and token count

**This is the project.** Everything after it is breadth and polish. If nothing
else gets finished, this being solid is a complete result.

---

## Stage 7 — WhatsApp channel

- [ ] Twilio sandbox + `cloudflared` tunnel, signature verification
- [ ] WhatsApp adapter: parse the form-encoded webhook, render within length limits
- [ ] Phone-number identity resolution, unverified-sender path
- [ ] Note the 24-hour service window in the code where it bites
- [ ] Retry and delivery-status tracking on outbound

**Done when:** a real WhatsApp message from your phone produces a ticket and a
reply, Twilio's retry does not duplicate it, and with the tunnel down the
simulator still exercises the same path.

Budget the Twilio trial credit for rehearsal and the demo — develop against the
simulator.

---

## Stage 8 — Email channel

- [ ] IMAP poller as an `arq` cron job (30-60s) against a throwaway Gmail with an
      app password
- [ ] MIME parsing: prefer `text/plain`, strip quoted history and signatures
- [ ] Threading via `Message-ID` / `In-Reply-To`
- [ ] SMTP send preserving headers
- [ ] Ignore `Auto-Submitted` and `List-Id` mail, and rate-limit per sender

**Done when:** emailing the support inbox produces a correctly threaded reply, and
replying to that reply continues the same ticket.

Email parsing is fiddlier than it looks. If quoted-text stripping is 80% right,
that is good enough — move on. **This is the first stage to cut if you are
behind.**

---

## Stage 9 — Dashboard and metrics

- [ ] JWT auth (argon2), `agent` and `admin` roles
- [ ] Ticket list with filters; ticket detail with the reasoning timeline from
      `agent_runs` / `agent_steps` / `tool_calls`
- [ ] Metrics: open/closed, AI resolution rate, escalation rate and reasons,
      channel breakdown, avg first response, cost per ticket
- [ ] KB management: create/edit a document, re-embed on save
- [ ] Live updates over WebSocket

**Done when:** you can log in, find any ticket, understand why the AI did what it
did, edit a KB article, and watch the numbers move after a burst of simulated
traffic.

---

## Stage 10 — Voice notes

Asynchronous voice messages. Not telephony.

- [ ] Parakeet TDT local STT (faster-whisper fallback for other languages)
- [ ] Record in the web widget / accept WhatsApp audio → normal pipeline, unchanged
- [ ] Voice `ResponseStyle`: short sentences, no markdown, no URLs
- [ ] Optional spoken reply via `piper`

**Done when:** a voice note asking for order status gets a correct reply, and the
orchestrator needed zero changes. That "zero changes" is the payoff of
channel-agnostic design — say so in the report.

---

## Stage 11 — Evaluation

The thing that turns a demo into a result. Keep it small; see `08-evaluation.md`.

- [ ] ~50 labelled cases (collect these from Stage 3 onward as you test, not all
      at the end)
- [ ] `eval/run_eval.py` replays them through the real graph against a fresh seed
- [ ] Metrics: intent accuracy, resolution rate, escalation precision/recall,
      hallucination rate, latency, cost per ticket
- [ ] Ablations: no-RAG, no-`verify`, dense-only retrieval, all-tools-exposed
- [ ] One threshold sweep on `INTENT_CONFIDENCE_MIN`

**Done when:** `make eval` prints a table you can paste into the report, and the
ablations show what RAG, the verify node and hybrid search each contribute.

---

## Stage 12 — Demo and writeup

- [ ] Failure drills: no LLM key, no Redis, no tunnel, tool raises — each must
      produce an honest customer-facing message, never silence
- [ ] Concurrency sanity check: ~50 simultaneous conversations through the
      simulator on `LLM_PROVIDER=stub`. This is not a load test; it exists to
      find connection-pool sizing problems before the demo
- [ ] PII check: a card-like or OTP-like string in a customer message never
      appears in a recorded prompt
- [ ] `make demo` — reset, seed, start everything, run the scripted scenario
- [ ] README, exported diagrams, demo video, report

**Done when:** a stranger can clone the repo, run one command, and reproduce the
Stage 6 demo script.

---

## Testing policy

Not a test pyramid, and not nothing. Test the paths where a silent failure is
expensive and hard to notice:

- [ ] Ticket state transitions, legal and illegal
- [ ] Message dedupe — a replayed `external_message_id` is dropped
- [ ] Identity resolution across channels, including the unknown-sender path
- [ ] `policy/authorize()` decision table
- [ ] Tool customer-scoping — another customer's order returns nothing
- [ ] PII redaction — nothing card-like or OTP-like reaches a prompt
- [ ] Retrieval smoke test — the 20 queries from Stage 3

Roughly 40 tests. Everything else is covered by the eval harness, which is the
real regression net for agent behaviour. No CI, no coverage gate, no
`testcontainers` — run `pytest` locally when you change one of the above.

## Deliberately not doing

Scope decisions, not shortcuts. Worth naming in the report as conscious
trade-offs:

- **Skill-based assignment routing and SLA breach cron.** One priority-ordered
  queue; the `skills` column exists and filters the view.
- **Reranking.** Hybrid search is adequate.
- **A self-hosted trace UI (Langfuse).** The ticket-detail reasoning timeline
  covers the same need.
- **CI, mypy, coverage gates, real load testing.**
- **RFC-7807 error bodies, cursor pagination, live-editable threshold config.**
- **Horizontal scale, HA, multi-tenancy, rate limiting** beyond a per-sender
  email guard.

## Cut list, in order, if you fall behind

1. Voice (Stage 10) — describe the design in the report instead
2. Email (Stage 8) — WhatsApp plus web chat already proves multi-channel
3. Dashboard metrics charts — keep the ticket list and the reasoning timeline
4. The last two ablations (dense-only, all-tools) — keep no-RAG and no-verify

**Never cut:** escalation, the `verify` node, the handoff packet, or the
evaluation harness. Those four are the project.

## Working rhythm

- Save every manual test you run as an eval case. By Stage 11 the dataset should
  mostly already exist.
- Tag a commit at the end of each stage.
- Keep `docs/decisions/` going — one short file per non-obvious choice. Nearly
  free, and the report ends up half-written.
