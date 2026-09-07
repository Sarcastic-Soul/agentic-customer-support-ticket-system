# Progress Log

Update at the end of every stage. Two minutes each time. This file is what the
final report's "what was built" section gets written from, and it is the fastest
way for anyone (including a future you, or an agent) to know the real state of
the repo rather than the planned one.

Format per entry: what works, what is knowingly broken, what was skipped and why.
Be honest about the broken parts — an acknowledged limitation reads better than
an unnoticed one.

---

## Stage 0 — Foundations
**Status:** done

- Works: `docker compose up -d` (postgres 18 + pgvector 0.8.6, redis 7); FastAPI
  skeleton with `/health` checking both; Alembic wired against `app.db.Base`
  with an empty baseline migration applied; `ruff` clean; one smoke test
  (`/health` returns 200) passing; `Makefile` targets `up/migrate/seed/dev/demo/eval/test/lint`.
- Known broken: none.
- Skipped: `make demo`/`make seed` are stubs until Stage 1 (`app.seed.run`
  does not exist yet) and Stage 6 (no scripted scenario yet).
- Notes:
  - Toolchain: Python 3.13 via `uv` (system only has 3.10-3.12), deps managed
    with `uv pip install -e .` into `backend/.venv`. `pnpm` for the frontend
    later.
  - Host ports 5432/5433 were already taken by other local projects
    (`paintkart-postgres`, `agentrail-postgres`) — this project's Postgres is
    remapped to host port **5434** in `docker-compose.yml` and `.env`. Redis
    stayed on the default 6379.
  - `pgvector/pgvector:pg18` changed its volume convention vs. earlier images:
    it expects a single mount at `/var/lib/postgresql`, not
    `/var/lib/postgresql/data` — mounting at the old path crashes the
    container on startup with a `pg_ctlcluster`-format error. Fixed in
    `docker-compose.yml`.
  - `.env` lives at the repo root, not `backend/`, so `app/config.py`
    resolves `_REPO_ROOT_ENV` relative to the file's own location rather than
    cwd — otherwise `alembic` (run from `backend/`) silently falls back to
    default settings and connects to the wrong Postgres.

## Stage 1 — Data model and seed
**Status:** not started

## Stage 2 — Web chat end to end, no AI
**Status:** not started

## Stage 3 — RAG pipeline
**Status:** not started

## Stage 4 — Orchestrator: classify, retrieve, answer
**Status:** not started

## Stage 5 — Tools: orders and transactions
**Status:** not started

## Stage 6 — Escalation and human console (MILESTONE)
**Status:** not started

## Stage 7 — WhatsApp channel
**Status:** not started

## Stage 8 — Email channel
**Status:** not started

## Stage 9 — Dashboard and metrics
**Status:** not started

## Stage 10 — Voice notes
**Status:** not started

## Stage 11 — Evaluation
**Status:** not started

## Stage 12 — Demo and writeup
**Status:** not started

---

## Running list of known limitations

Things that are broken or missing on purpose. Keep this current — it goes almost
verbatim into the report's limitations section.

- (nothing yet)

## Things that surprised us

Anything that cost more time than expected, or turned out differently than the
blueprint assumed. Good report material, and it stops the same surprise twice.

- (nothing yet)
