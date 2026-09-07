# API Specification

Base URL `http://localhost:8000`. Everything under `/api/v1`. Dashboard and
console routes require a JWT bearer token; channel webhooks use provider
signature verification instead.

## Channel ingress

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/channels/whatsapp/webhook` | Twilio signature | Must return 200 within ~1s. Enqueues and returns. |
| `POST` | `/channels/email/ingest` | internal token | Called by the IMAP poller task; also usable manually. |
| `WS` | `/channels/web/ws?session_id=` | none (public widget) | Bidirectional web chat. |
| `POST` | `/channels/voice/upload` | none | Stage 10. Multipart audio. |
| `POST` | `/dev/simulate/{channel}` | dev only | Injects a synthetic `InboundMessage`. Build this first. |

Webhook contract: **acknowledge, then work.** The handler persists `raw_events`,
dedupes on `(channel, external_message_id)`, enqueues `handle_message`, and
returns. No LLM call ever happens inside a request handler.

## Customer-facing

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/chat/session` | Start a web chat session, returns `session_id`. |
| `GET` | `/api/v1/chat/{session_id}/messages` | Transcript (polling fallback for the WS). |
| `GET` | `/api/v1/tickets/by-reference/{reference}` | Public status lookup by ticket reference. |

## Admin — tickets

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/tickets` | Filter: `status`, `channel`, `intent`, `priority`, `assigned_to`, `q`, date range. Paginated. |
| `GET` | `/api/v1/admin/tickets/{id}` | Ticket + conversation + events + linked order/transactions. |
| `GET` | `/api/v1/admin/tickets/{id}/runs` | Agent runs with steps and tool calls — the "why did it do that" view. |
| `PATCH` | `/api/v1/admin/tickets/{id}` | Change status, priority, assignee. Validated by the state machine. |
| `POST` | `/api/v1/admin/tickets/{id}/note` | Internal note (not sent to the customer). |
| `POST` | `/api/v1/admin/tickets/{id}/reply` | Human reply, delivered via the ticket's channel adapter. |

## Admin — escalation queue / console

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/console/queue` | Queued escalations, priority-ordered, optional `skill` filter. |
| `POST` | `/api/v1/console/escalations/{id}/claim` | Atomic claim (`FOR UPDATE SKIP LOCKED`). 409 if already claimed. |
| `POST` | `/api/v1/console/escalations/{id}/release` | Return to the queue. |
| `GET` | `/api/v1/console/escalations/{id}` | Handoff packet + transcript + suggested draft and action. |
| `POST` | `/api/v1/console/escalations/{id}/approve-action` | Execute the AI's suggested gated tool with `approved_by` recorded. |
| `POST` | `/api/v1/console/escalations/{id}/return-to-ai` | Body `{note}`. Resumes the graph from its checkpoint. |
| `POST` | `/api/v1/console/escalations/{id}/resolve` | Body `{summary, create_kb_article?}`. |
| `WS` | `/api/v1/console/ws` | Live: `escalation.created`, `ticket.updated`, `message.created`, `sla.breach`. |

## Admin — knowledge base

| Method | Path | Purpose |
|---|---|---|
| `GET` `POST` | `/api/v1/admin/kb/documents` | List / create. Create triggers chunk + embed. |
| `GET` `PUT` `DELETE` | `/api/v1/admin/kb/documents/{id}` | Update bumps `version` and re-embeds. |
| `POST` | `/api/v1/admin/kb/search` | Debug endpoint: returns dense, sparse, fused and reranked results side by side with scores. Invaluable while tuning, and a good demo screen. |
| `GET` | `/api/v1/admin/kb/gaps` | Tickets escalated with `knowledge_gap`, grouped by cluster — the KB backlog. |

## Admin — metrics

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/admin/metrics/overview` | Open/closed counts, AI resolution rate, escalation rate, avg first response, avg resolution time, CSAT. `?range=7d`. |
| `GET` | `/api/v1/admin/metrics/channels` | Volume, resolution rate and latency per channel. |
| `GET` | `/api/v1/admin/metrics/intents` | Volume and escalation rate per intent — shows where the AI is weak. |
| `GET` | `/api/v1/admin/metrics/escalations` | Breakdown by `reason_code` over time. |
| `GET` | `/api/v1/admin/metrics/cost` | Tokens and estimated cost per ticket, per model, per day. |
| `GET` | `/api/v1/admin/metrics/timeseries` | Daily series for the dashboard charts. |

Thresholds and policy limits are read from `policy/thresholds.py` and changed by
editing that file and restarting — no live-editable config endpoint. The threshold
sweep in the eval harness makes the tuning point better than an admin screen would.

## Auth

| Method | Path |
|---|---|
| `POST` | `/api/v1/auth/login` -> `{access_token, refresh_token}` |
| `POST` | `/api/v1/auth/refresh` |
| `GET` | `/api/v1/auth/me` |

Roles: `agent` (queue and tickets) and `admin` (adds KB editing). Two roles, not
three — a supervisor tier has nothing distinct to do in a prototype.

## Conventions

- Errors: FastAPI's default `{"detail": ...}`. RFC 7807 problem details buy
  nothing when one developer writes both ends.
- Pagination: `?limit=&offset=`. Cursor pagination is not needed at this size.
- Every response carries `X-Request-ID`, echoed into logs and `agent_runs`.
- Path prefix `/api/v1` is kept for tidiness, not because a v2 is planned.
