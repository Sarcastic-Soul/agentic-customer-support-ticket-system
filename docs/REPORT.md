# Final report

**Project:** Agentic AI customer support ticket system
**Status at time of writing:** Stages 0-11 complete, Stage 12 in progress
(this report is being written as part of Stage 12; the evaluation numbers
section is a placeholder pending a full `make eval` run — see that section
for why, and how to fill it in).

## 1. What this is

A support system that reads a customer's message on any channel (web chat,
WhatsApp, email, or a recorded voice note), tries to resolve it against real
order/payment/knowledge data using a single channel-agnostic LangGraph agent,
and — when it cannot or should not act — hands the ticket to a human with a
full context packet (summary, timeline, verified entities, a suggested
reply) rather than a shrug. The human can resolve it or return it to the AI
with a note, and the agent resumes from its checkpointed state.

Full architecture: [`docs/01-architecture.md`](01-architecture.md) and the
diagram in the [README](../README.md#architecture-in-one-paragraph).

## 2. What was actually built

All 12 planned stages, in order, each with its own live verification (real
Gemini/Groq calls, a real browser where relevant, never stub-only) before
being marked done. Stage-by-stage detail, including every bug found and how,
lives in [`docs/PROGRESS.md`](PROGRESS.md) — this section is the summary.

| Stage | What it added |
|---|---|
| 0 | Repo skeleton, docker compose (Postgres 18 + pgvector, Redis), FastAPI, Alembic |
| 1 | Data model, ticket state machine, ingress pipeline, seed data |
| 2 | Web chat end to end via Redis/arq, no AI yet (proved the queue/worker/adapter loop) |
| 3 | RAG pipeline: hybrid (dense + sparse) retrieval, calibrated retrieval gate |
| 4 | LangGraph orchestrator with live Gemini/Groq, fallback on failure |
| 5 | Order/transaction tools, policy `authorize()`, bounded tool loop |
| 6 | **Milestone.** Escalation, handoff packet, human console, `interrupt()`/resume |
| 7 | WhatsApp channel (Twilio), delivery-status tracking |
| 8 | Email channel (IMAP/SMTP), MIME parsing, thread-root resolution |
| 9 | Admin dashboard: ticket list + reasoning trace, metrics, KB management, JWT auth |
| 10 | Voice notes: STT via Groq Whisper, `ResponseStyle` enforcement across all channels |
| 11 | **Milestone.** Evaluation harness, 50-case labelled dataset, 4 ablations, threshold sweep |
| 12 | Failure drills, PII redaction (a real gap this stage caught), concurrency check, this report |

## 3. Design decisions worth knowing about

Full reasoning for each lives in `docs/decisions/`. Summary:

- **[0001](decisions/0001-no-nextjs.md) — No Next.js.** The backend is
  FastAPI; a Node server that only renders a client shell is dead weight.
  Vite + React 19 + TanStack Router/Query instead.
- **[0002](decisions/0002-model-selection.md) — Model selection.**
  `gemini-3.8-flash` primary (reasoning), `gemini-3.5-flash-lite` for
  classify/verify (cheaper, higher daily quota), Groq `openai/gpt-oss-120b`
  fallback. Two other models under consideration were deprecated *during
  planning* — model ids live only in `.env`, read through one registry
  module, specifically because of how fast this space moves.
- **[0003](decisions/0003-prototype-scope.md) — What "prototype scope"
  means here.** The single most load-bearing decision in the project:
  *tolerate rough edges, keep the structure.* An earlier draft cut Redis,
  Alembic, several audit tables, and PII redaction as "prototype
  simplification" — that went too far. The distinction that matters is
  tolerance vs. structure, not prototype vs. production. This is why the
  queue, the dedupe constraint, `agent_steps`/`tool_calls`, and PII
  redaction all stayed non-negotiable even under real time pressure.
- **[0004](decisions/0004-retrieval-score-threshold.md) — Retrieval score
  threshold.** The blueprint's placeholder (0.35) was measured against the
  real seeded KB and found to let off-topic queries through (top score 0.46
  for "what is the meaning of life"). Recalibrated to 0.55 against a
  measured on-topic/off-topic gap, not a guess.
- **[0005](decisions/0005-voice-stt-groq-fallback.md) — Voice STT via the
  Groq API, not a local model.** The documented design (Parakeet TDT
  primary, `faster-whisper` fallback) assumes a machine that can run local
  inference. This one measured ~650MB free RAM with ~4.7GB of swap already
  in use and no GPU — genuinely not practical. Went straight to the
  documented API-fallback path instead of forcing a local model onto a
  machine that couldn't support it.

## 4. Real bugs found live, and what caught them

This project's stated discipline was: unit tests and `LLM_PROVIDER=stub`
prove the plumbing works, but every LLM-touching or async-DB-touching code
path gets verified against the real thing before being called done. That
discipline caught real bugs unit tests alone would have missed — this is
the evidence for it, not just the claim:

- **Stage 2** — `redis-py` delivers pub/sub payloads as `bytes`; the WS
  handler called `send_text()` with them unconverted, silently killing the
  reply-forwarding task with no error surfaced anywhere. Found by watching a
  real browser tab never receive a reply.
- **Stage 4-ish** — `StubChatModel`'s structured-output synthesis had a
  logic bug in required-field detection that only mattered once real
  Pydantic schemas with mixed required/optional fields existed.
- **Stage 8** — `EmailAdapter.send()` used `external_thread_id` (the
  thread-root Message-ID) as the `To:` address. Email is the one channel
  where the threading id and the addressing id are genuinely different
  things — web and WhatsApp don't have this problem, which is exactly why
  the bug wasn't obvious from the design. Found via a Gmail auth error
  logged against a Message-ID-shaped string instead of an email address.
- **Stage 9** — `KBDocument.updated_at` (an `onupdate=func.now()` column)
  gets expired by SQLAlchemy on flush *independent of the session's
  `expire_on_commit` setting* — a genuinely non-obvious async-SQLAlchemy
  trap. Accessing it right after `commit()` without an explicit `refresh()`
  raised `MissingGreenlet`. Found via a real 500 through the admin UI's KB
  editor, not a test.
- **Stage 11** — `LLMRole.judge` was going through the normal
  primary-then-fallback provider dance despite `judge_model` being a Groq
  model id, guaranteeing a wasted failing attempt (and burned quota) against
  Gemini on every single judge call.
- **Stage 12** — `messages.body_redacted` existed as a schema column
  (correctly listed as non-negotiable in the scope decision) but nothing in
  the codebase ever populated it or redacted anything before it reached a
  prompt. The PII check this stage exists to run caught its own
  prerequisite missing entirely — fixed with `app/core/pii.py` and wired
  into the one real ingress choke point (`ingest_message`) plus everywhere
  `state["latest_message"]`/`history` get built into a prompt. Also found
  (and fixed): `handle_message` had no safety net if the graph raised for
  any reason — every LLM provider down, an unexpected exception — the
  customer got total silence, which is exactly the failure mode Stage 12's
  drills exist to catch. `_escalate_on_failure` now guarantees an honest
  message and a real escalation, deterministically, with no LLM call of its
  own (so it works in precisely the scenario that triggers it).
- **Also Stage 12, infrastructure rather than app code** — a `uv sync` run
  mid-Stage-9 silently broke the project's own editable install (`import
  app` failed inside `pytest` but not from a plain `python -c`, because the
  latter still had the cwd on `sys.path`). Not a bug in this project's
  logic, but exactly the kind of thing that looks like a test-runner
  problem and isn't — `uv pip install -e .` fixed it.

## 5. Stage 12 hardening results

- **Failure drills** (`backend/tests/test_failure_drills.py`,
  `docs/PROGRESS.md` Stage 12):
  - *Every LLM provider down* → customer gets an honest message, ticket
    escalates with `reason_code=system_error`, no duplicate escalation or
    message on arq retry. Fixed this session (see §4).
  - *A tool raises unexpectedly* → already handled correctly by
    `execute_tool`'s existing exception boundary; regression-tested, not a
    new fix.
  - *No Redis* → verified live (stopped the container, hit the ingress
    endpoint): the raw message is still persisted before the enqueue
    attempt (non-negotiable #1's "persist before enqueue" holds even here),
    the request fails loudly (500) rather than silently, and the system
    self-heals with no manual intervention once Redis returns.
  - *No tunnel* → design-level, not a runtime failure: WhatsApp needs a
    public tunnel to receive Twilio webhooks, but every scenario in the demo
    script has a web-chat/simulator equivalent that needs none (see
    `docs/09-risks.md` R5).
- **Concurrency sanity check**: 50 simultaneous conversations via the
  simulator, `LLM_PROVIDER=stub`. 50/50 requests succeeded, the worker
  processed 51/51 jobs (one leftover from earlier testing) with zero errors
  and zero connection-pool exhaustion, despite `db_pool_size=5` against
  `arq`'s `max_jobs=10` concurrent job slots.
- **PII check**: see §4 — this is the check that found the gap, not just
  verified an existing property. `backend/tests/test_pii.py` now covers it
  end to end, including a real graph run (stub LLM) proving a card number
  never appears in any recorded `agent_steps.prompt` row, in either the
  triggering turn or a follow-up turn's history.
- **`make demo`**: reset (full truncate + reseed, deterministic
  `SEED=20260908`), migrate, ingest, start everything, and run the
  automated half of the Stage 6 demo script (`scripts/demo_scenario.py`)
  against the running stack — policy question, real-data order-status
  lookup, and a large-refund-request-that-exceeds-policy — printing
  instructions for the two steps that need an actual human at the console
  (claim, reply, and the customer seeing it). Live-verified: steps 1-2
  completed correctly (`outcome=answered`, real citations, real tool
  results) against real Gemini/Groq; step 3 was still in flight against a
  visibly slow Gemini free tier at the time of this report (see §6) but the
  mechanism itself — dedupe-safe reset, background service startup, health
  polling before firing requests — is confirmed working.

## 6. Evaluation — pending a full run

`eval/run_eval.py` and `eval/dataset/tickets.jsonl` (50 cases, matching the
composition table in `docs/08-evaluation.md` exactly: 16 straightforward, 8
multi-tool/multi-turn, 10 must-escalate, 6 knowledge-gap, 6 adversarial, 4
noisy) are complete and mechanically verified — see `docs/PROGRESS.md`
Stage 11 for exactly what was live-tested (individual cases across every
bucket, the ticket-status-based escalation detection, the judge role fix).

**The full 50-case × 5-config (full + 4 ablations) run, plus the
`INTENT_CONFIDENCE_MIN` sweep, was not executed to completion during
development.** This was a deliberate choice, not an oversight: while
building Stage 11, `gemini-3.8-flash`'s free tier (20 requests/day) was
exhausted from earlier testing that same day, and one call hit a `503
"experiencing high demand"` that took over two minutes to fail over. A full
run through a visibly degraded API would have produced numbers that needed
re-running anyway once the API recovered, at the cost of a scarce daily
quota. The harness's fallback logic (quota-aware fast-fail, then Groq)
handled this correctly, just slowly.

**To fill in this section:** run, from `backend/`:

```bash
python ../eval/run_eval.py --all-ablations --sweep-confidence
```

against a freshly seeded database (`make seed && make ingest` first, or just
`make demo` and Ctrl-C once services are up). It prints a Markdown table per
configuration and writes timestamped JSON to `eval/reports/`. Paste the
"full" config's table here, then the ablation comparison:

| Configuration | Resolution rate | Groundedness | Hallucination | Escalation recall | Cost/ticket |
|---|---|---|---|---|---|
| Full system | *pending* | *pending* | *pending* | *pending* | *pending* |
| No RAG | *pending* | *pending* | *pending* | *pending* | *pending* |
| No `verify` | *pending* | *pending* | *pending* | *pending* | *pending* |
| Dense-only retrieval | *pending* | *pending* | *pending* | *pending* | *pending* |
| All tools exposed | *pending* | *pending* | *pending* | *pending* | *pending* |

Expected pattern, per `docs/08-evaluation.md` (to confirm or correct once
real numbers exist): removing RAG collapses groundedness; removing `verify`
raises resolution rate but raises hallucination more; dense-only retrieval
loses order-number/error-code lookups that keyword search catches; exposing
every tool (no `plan` restriction) raises wrong-tool-call rate and cost.

## 7. Known limitations

Also tracked live in `docs/PROGRESS.md`'s "Running list of known
limitations" as they were found:

- No local/offline STT or TTS — voice notes need internet and a Groq API
  key. Spoken (`piper`) replies are not implemented (build-stages checklist
  marks TTS "Optional"; text-only replies to voice notes today).
- Email and WhatsApp's real-provider tests (an actual mailbox, an actual
  phone) are manual steps documented in the README, not automated — same
  for the WhatsApp voice-note transcription path specifically.
- No horizontal scale, HA, multi-tenancy, or rate limiting beyond a
  per-sender email guard — explicit prototype scope
  (`docs/decisions/0003-prototype-scope.md`).
- Skill-based assignment routing, an SLA-breach cron, reranking, a
  self-hosted trace UI, CI, mypy, coverage gates, real load testing,
  RFC-7807 error bodies, and cursor pagination are genuinely out of scope,
  not cut corners — see `docs/07-build-stages.md`.
- The full evaluation matrix (§6) needs a rerun once Gemini's daily quota
  isn't already spent from the same day's development work.

## 8. Things that surprised us

- `ResponseStyle` was part of the `ChannelAdapter` protocol since Stage 1,
  but nothing ever actually read it until Stage 10 needed voice's
  "no markdown, no URLs" — every channel had been silently sending
  unformatted LLM output the whole time. A contract existing in a type
  system is not the same as the contract being enforced anywhere; that gap
  can hide for ten stages in a channel-agnostic design specifically because
  every individual channel *looked* like it was working.
- The same shape of gap, worse, in Stage 12: `messages.body_redacted` was
  explicitly called out as non-negotiable in the scope decision from the
  very start, existed correctly in the schema and every migration since,
  and was never once populated. A schema column is not a feature. The PII
  check existing as a required Stage 12 task — not just "PII redaction
  exists, verify it" but "check whether it actually reaches a prompt" — is
  what caught it; a less specific task ("make sure PII is handled") might
  not have.
- Async SQLAlchemy's `onupdate`-column expiration (Stage 9) and the
  editable-install breakage after `uv sync` (Stage 10/12) were both the
  kind of bug that a plain `python -c "import ..."` smoke check would miss
  but the *actual* test runner or the *actual* running server would hit
  immediately — reinforcing the project's own stated discipline that "does
  it import" and "does pytest pass" are not the same question as "does it
  work," for exactly the class of bug async Python and package tooling
  produce.

## 9. Demo video

Not produced as part of this report — recording and editing a walkthrough
video needs a human at a microphone, which this session doesn't have.
