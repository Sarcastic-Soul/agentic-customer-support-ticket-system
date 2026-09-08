# API Specification

Base URL `http://localhost:8000`. No `/api/v1` prefix — this was in the
original plan below before any code existed; the real routers use `/api/*`
and `/channels/*` directly, and a version prefix bought nothing for a
single-developer prototype with no external consumers. Dashboard and console
routes require a JWT bearer token (`app/core/auth.py`); channel webhooks use
provider signature verification instead.

This reflects what `backend/app/api/` and `backend/app/ingress/` actually
register, not a plan — see `docs/PROGRESS.md` for how each stage got built.

## Health

| Method | Path | Auth |
|---|---|---|
| `GET` | `/health` | none |

Checks the database and Redis are reachable. `{"status": "ok" | "degraded", "checks": {"db": bool, "redis": bool}}`.

## Channel ingress

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/channels/whatsapp/webhook` | Twilio signature | Acknowledges and enqueues; the reply goes out later, asynchronously. |
| `POST` | `/channels/whatsapp/status` | Twilio signature | Delivery-status callback (`queued`→`sent`→`delivered`/`failed`). |
| `WS` | `/channels/web/ws?session_id=` | none (public widget) | Bidirectional web chat. |
| `POST` | `/channels/voice/upload` | none, gated on `VOICE_ENABLED` | Multipart audio from the web widget's mic button; transcribes via Groq Whisper, returns `{"transcript": str}`. |

Email has no HTTP ingress at all — `app/workers/email_poll.py` is an arq
cron job that polls IMAP directly; nothing needs to reach in.

Webhook contract: **acknowledge, then work.** The handler persists
`raw_events`, dedupes on `(channel, external_message_id)`, enqueues
`handle_message`, and returns. No LLM call ever happens inside a request
handler.

## Dev simulators

| Method | Path | Notes |
|---|---|---|
| `POST` | `/dev/simulate/web` | `{session_id, text, external_message_id?}` — exercises the real ingest pipeline without a WebSocket. |
| `POST` | `/dev/simulate/whatsapp` | `{phone, text, external_message_id?}` — same shape, without Twilio or a tunnel. |
| `POST` | `/dev/simulate/email` | `{from_email, text, subject?, external_message_id?, in_reply_to?}` — same shape, without IMAP or a mailbox. |

Every channel got one of these before its real adapter, per the project's
own convention — used throughout development and by `scripts/demo_scenario.py`.

## Auth

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/auth/login` | `{email, password}` → `{access_token, role, full_name}`. |
| `GET` | `/api/auth/me` | Bearer token → `{id, email, full_name, role}`. |

One long-lived access token (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24`, argon2
password hashes), no refresh-token flow — not worth the complexity for a
prototype console. Two roles: `agent` (queue, tickets, KB reads) and `admin`
(adds KB writes). Seeded agents all use password `dev-password`.

## Admin — tickets and reasoning trace

All routes below require a bearer token (any role) unless noted.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/admin/tickets` | Filterable, paginated ticket list. |
| `GET` | `/api/admin/tickets/{ticket_id}` | Ticket detail with transcript and timeline. |
| `GET` | `/api/admin/tickets/{ticket_id}/runs` | `agent_runs` with their `agent_steps`/`tool_calls` — the "why did it do that" view, powers the admin dashboard's reasoning-trace panel. |

## Admin — metrics

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/admin/metrics/overview?range=7` | Total/open/closed tickets, AI resolution rate, escalation rate, avg first response and resolution time, total estimated LLM cost. |
| `GET` | `/api/admin/metrics/channels?range=7` | AI-resolved vs. escalated volume per channel. |
| `GET` | `/api/admin/metrics/intents?range=7` | Ticket volume per classified intent. |
| `GET` | `/api/admin/metrics/escalations?range=7` | Escalation count grouped by `reason_code`. |

Powers the Recharts dashboard at `/admin/metrics` in the frontend. These are
live traffic numbers, not the evaluation harness — see
`docs/08-evaluation.md`'s "Live metrics are not evaluation".

## Admin — knowledge base

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/admin/kb/documents` | any role | List, with active/inactive status. |
| `GET` | `/api/admin/kb/documents/{doc_id}` | any role | Full document body. |
| `POST` | `/api/admin/kb/documents` | `admin` | Create; chunks and embeds immediately. |
| `PUT` | `/api/admin/kb/documents/{doc_id}` | `admin` | Update; bumps `version` and re-embeds only if the body actually changed. |
| `POST` | `/api/kb/search` | none | Debug endpoint — dense, sparse and RRF-fused results side by side with scores, plus whether the real retrieval gate would return nothing for this query. Not admin-scoped; built for tuning `RETRIEVAL_SCORE_MIN` (see `docs/decisions/0004-retrieval-score-threshold.md`), useful as a demo screen too. |

## Escalation console

All routes require a bearer token; prefix `/api/console`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/queue` | Queued escalations, priority-ordered. |
| `GET` | `/escalations/{escalation_id}` | Handoff packet: summary, timeline, verified entities, suggested reply. |
| `GET` | `/escalations/{escalation_id}/transcript` | Full conversation transcript. |
| `POST` | `/escalations/{escalation_id}/claim` | Atomic claim (`FOR UPDATE SKIP LOCKED`). |
| `POST` | `/escalations/{escalation_id}/reply` | Human's reply, delivered through the ticket's own channel adapter. |
| `POST` | `/escalations/{escalation_id}/return-to-ai` | `{note}` — resumes the LangGraph checkpoint (`Command(resume=...)`) with the human's note fed into the next AI turn. |
| `POST` | `/escalations/{escalation_id}/resolve` | Marks the escalation resolved. |
| `GET` | `/stats` | Console-level counters (queue depth, claimed-by-me, etc.) for the console UI. |

No live WebSocket push for the console — it polls via TanStack Query, which
was enough at this scale and one fewer moving part than a second
long-lived connection type alongside the customer-facing web chat WS.

## Conventions

- Errors: FastAPI's default `{"detail": ...}`. RFC 7807 problem details buy
  nothing when one developer writes both ends — explicit prototype scope,
  see `docs/decisions/0003-prototype-scope.md`.
- Pagination: `?limit=&offset=` where it exists. Cursor pagination is not
  needed at this size.
- Model ids used for a given response are visible via `agent_runs`/
  `agent_steps`, not echoed on every response — see `app/llm/registry.py`.
