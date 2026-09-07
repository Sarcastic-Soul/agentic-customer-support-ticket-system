# 0003 — What "prototype scope" means here

**Date:** 2026-09-08 · **Status:** accepted

## Context

This is a prototype built by one person, and build speed is the scarce resource.
An earlier pass at this decision over-corrected: it cut Redis and the job queue,
Alembic, the `raw_events` / `refunds` / `shipments` / `agent_steps` / `tool_calls`
tables, PII redaction, and most of the test coverage. That went too far — those
are not polish, they are the parts that keep the system honest and debuggable.

The distinction that actually matters is not "production vs prototype". It is
**tolerance versus structure**.

## Decision

**Tolerate rough edges. Keep the structure.**

Accepted, not worth spending time on:

- Rare edge-case bugs — a stray email signature left in a transcript, a race that
  needs three simultaneous messages, a metric off by one on a boundary.
- Imperfect quoted-text stripping in email. 80% correct is done.
- Rough UI: unstyled states, no empty-state illustrations, no animations.
- No horizontal scale, no HA, no multi-tenancy, no rate limiting beyond a
  per-sender email guard.
- Thin test coverage outside the critical paths.

Kept, non-negotiable:

- **Redis + `arq`, with worker and scheduler processes.** LLM calls take seconds
  on a rate-limited free tier; the queue is what keeps webhooks fast and gives
  retry-with-backoff. On a free tier the retry path is exercised regularly.
- **Alembic.** The schema changes across twelve stages.
- **`raw_events`.** Persist before enqueueing, so a crash between webhook and job
  never loses a customer message.
- **`refunds` as its own table.** A refund has an approval lifecycle a payment
  does not, and that lifecycle — AI requests, policy denies, human approves — is
  the most demo-critical write path in the system.
- **`agent_steps` and `tool_calls` as tables, not JSONB.** The eval harness
  queries across them: tool-selection accuracy is a `GROUP BY tool_name`.
- **PII redaction with `messages.body_redacted`.** Regex-grade detection, but a
  real path, so what the model saw is on the record.
- **The message dedupe unique constraint.** One line; without it a retried
  webhook answers the same customer three times during a demo.
- **The evaluation harness.** The difference between a demo and a result.

Genuinely out of scope, as scope rather than shortcut: skill-based assignment
routing (the `skills` column exists and filters the queue view; no algorithm), SLA
breach cron, reranking, a self-hosted trace UI, CI, mypy, coverage gates, real
load testing, RFC-7807 error bodies, cursor pagination, live-editable threshold
config.

## Reasoning

Every item in the "kept" list either *is* the project (escalation, verify, eval)
or prevents a class of failure that is invisible until it happens in front of an
audience (dedupe, raw events, queue retry). None of them cost more than a few
hours.

Every item in the "tolerate" list costs unbounded time and buys polish nobody is
grading.

The failure mode to avoid is stripping structure to buy time, then spending that
time debugging problems the structure would have prevented. If time runs short,
**cut a whole stage** — that is what the cut list in `07-build-stages.md` is for.
It is cheaper and more honest than half-building six of them.

## Consequences

- Schema changes go through a migration. Not free, but it is minutes.
- Three processes to run in development; `make dev` starts all of them.
- Testing is roughly 40 tests on named critical paths, not a pyramid, and the
  eval harness is the regression net for agent behaviour.
- The report presents the "out of scope" list as deliberate trade-offs, with this
  file as evidence they were decided rather than overlooked.
