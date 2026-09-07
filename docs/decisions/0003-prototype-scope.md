# 0003 — Prototype scope: what we deliberately do not build

**Date:** 2026-09-08 · **Status:** accepted

## Context

The first draft of the blueprint specified a production-shaped system: Alembic
migrations, Redis + `arq` with separate worker and scheduler processes, a test
pyramid with `testcontainers` and a CI regression gate, RFC-7807 error bodies,
cursor pagination, skill-based agent routing, SLA breach cron jobs, a PII
redact-and-restore subsystem, load testing, and self-hosted Langfuse.

This is a prototype built by one person. Every one of those is insurance against
a risk this project does not carry.

## Decision

Cut all of the above. Specifically:

| Cut | Replaced by |
|---|---|
| Alembic | `backend/schema.sql` + `make reset` |
| Redis, `arq`, worker and scheduler processes | `asyncio.create_task`, one process |
| Test pyramid, CI, mypy, coverage | ~15 smoke tests; the eval harness is the regression net |
| Load testing | nothing — it would burn free-tier quota and prove nothing |
| `agent_steps` + `tool_calls` tables | `agent_runs.steps` JSONB |
| `raw_events` table | `messages.raw` JSONB |
| `refunds` table | `transactions` rows with `type='refund'` |
| Skill routing, SLA cron | one priority-ordered queue |
| Reranking | hybrid search alone |
| Langfuse | `agent_runs.steps` rendered on the ticket page |
| PII subsystem | a regex pass before the prompt |
| RFC-7807, cursor pagination | FastAPI defaults, `limit`/`offset` |

## Reasoning

Each cut item defends against something real — data loss on restart, schema drift
across environments, regressions from a large team, throughput limits. None of
those apply: the data is synthetic and regenerable, there is one environment, one
developer, and traffic is a demo.

What they cost is build speed, which is the actual scarce resource. Rare
edge-case bugs are cheaper than the time spent preventing them.

## What is explicitly *not* cut

The list in `CLAUDE.md` under "Non-negotiables". Two are worth restating because
they look like the kind of thing this decision would cut, and are not:

- **The message dedupe unique constraint.** One line, and without it a retried
  webhook answers the same customer three times during a demo.
- **The evaluation harness.** ~35 cases and one script. It is the difference
  between a demo and a result, and it is the project's only regression net now
  that the test pyramid is gone.

## Consequences

- Work in flight is lost if the process restarts. Accepted.
- Schema changes require a full reset and re-seed. Fine while data is synthetic;
  the moment there is data worth keeping, adopt Alembic.
- Refactoring pressure will build. Resist it — this is not a codebase that needs
  to survive five years.
- The report should present these as conscious trade-offs, with this file as the
  evidence that they were decided rather than overlooked.
