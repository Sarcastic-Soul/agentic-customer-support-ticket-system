# Agentic AI Customer Support System

![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-arq-DC382D?logo=redis&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![License](https://img.shields.io/badge/license-MIT-blue)

A customer writes in on web chat, WhatsApp, email or a voice note. AI agents try
to actually fix the problem using real order, delivery and payment data. When
they can't or shouldn't, a person gets the ticket with everything they need, and
can hand it back. Runs on a laptop with free-tier AI keys.

![How a support message gets answered](docs/architecture-overview.svg)

## What it does

- **Specialist agents** for orders, delivery and payments work side by side on
  one message.
- **Agents propose, code decides.** Rules, limits and disagreements between
  agents are settled in plain code, never by the AI.
- **Every reply is fact-checked** against the data before it is sent.
- **Asks before giving up.** Unclear messages get a question; refunds above the
  limit go to a one-click approval queue instead of a full handoff.
- **Good handoffs.** A person gets a summary, what the AI tried and a suggested
  reply, and can return the ticket to the AI with a note.
- **Everything is recorded**, so you can see why the AI did what it did.

## Read these

| Doc | What it covers |
|---|---|
| [`docs/architecture-overview.md`](docs/architecture-overview.md) | How the whole system fits together |
| [`docs/agent-orchestration.md`](docs/agent-orchestration.md) | The agents: who does what, who talks to whom, how disagreements are settled |
| [`docs/REPORT.md`](docs/REPORT.md) | What was built, results, limits, lessons |

Everything else in `docs/` is the original build plan and working notes,
kept for reference.

## Quick start

```bash
cp .env.example .env          # add GEMINI_API_KEY and GROQ_API_KEY
make up                       # postgres + redis
make migrate                  # database tables
make seed                     # sample customers, orders, payments, help articles
make dev                      # api + worker + frontend
```

`make demo` resets everything and runs a scripted demo. `LLM_PROVIDER=stub` runs
the whole thing offline with a fake model, no keys needed.

No Python or Node installed? `make docker-up`, then
`docker compose exec api python -m app.seed.run` and
`docker compose exec api python -m app.rag.ingest`.

| URL | What |
|---|---|
| http://localhost:5173/chat | Customer chat |
| http://localhost:5173/login | Staff login (any seeded agent, password `dev-password`) |
| http://localhost:5173/console | Handoff queue and refund approvals |
| http://localhost:5173/admin | Tickets with the AI's reasoning, metrics, help articles |
| http://localhost:8000/docs | API docs |

Other commands: `make eval` (score the agent on 55 test tickets), `make test`,
`make e2e` (browser tests), `make langfuse` (optional tracing UI on :3001).

## Real channels

Every channel can be tested with a simulator (`POST /dev/simulate/*`). For the
real thing:

| Channel | Turn on | Also needs |
|---|---|---|
| Web chat | on by default | nothing |
| Voice notes | `VOICE_ENABLED=true` + `GROQ_API_KEY` | mic permission |
| WhatsApp | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Twilio sandbox + a public tunnel to `/channels/whatsapp/webhook` |
| Email | `EMAIL_ENABLED=true`, `SUPPORT_EMAIL`, `SUPPORT_EMAIL_APP_PASSWORD` | a Gmail address with an app password |

## Stack

Python 3.13, FastAPI, LangGraph, async SQLAlchemy + Alembic, PostgreSQL 18 +
pgvector, Redis + `arq`, Vite + React 19 + TanStack. AI: Gemini
`gemini-3.5-flash-lite`, with Groq `openai/gpt-oss` as fallback and as the eval
judge. Local embeddings (`bge-small-en-v1.5`) and reranker (flashrank). Model
names live only in `.env`.

## License

[MIT](LICENSE)
