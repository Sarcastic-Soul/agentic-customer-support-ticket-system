.PHONY: up down migrate seed ingest dev api worker frontend demo eval test lint docker-up docker-down \
	langfuse langfuse-down promptfoo e2e

BACKEND=cd backend && . .venv/bin/activate &&

# databases only, for native `make dev` - `make docker-up` runs everything
up:
	docker compose up -d postgres redis pgweb
	@echo "waiting for postgres..."
	@until docker compose exec -T postgres pg_isready -U support -d support >/dev/null 2>&1; do sleep 1; done
	@docker compose exec -T postgres psql -U support -d support -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS citext;" >/dev/null

down:
	docker compose down

migrate:
	$(BACKEND) alembic upgrade head

# seed wipes the KB chunks, so it always re-embeds them - a seed without
# ingest leaves search empty and every policy question unanswered
seed:
	$(BACKEND) python -m app.seed.run
	$(MAKE) ingest

ingest:
	$(BACKEND) python -m app.rag.ingest

api:
	$(BACKEND) uvicorn app.main:app --reload --port 8000

worker:
	$(BACKEND) arq app.workers.settings.WorkerSettings

frontend:
	cd frontend && pnpm dev

# api + worker + frontend together, backgrounded, cleaned up on Ctrl-C.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) api & \
	$(MAKE) worker & \
	$(MAKE) frontend & \
	wait

# seed truncates+reseeds every table (app/seed/run.py) - this is the
# "fresh, reproducible" reset the eval and demo need,
# there is no separate `reset` target.
demo:
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) seed
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) api & \
	$(MAKE) worker & \
	$(MAKE) frontend & \
	$(BACKEND) python ../scripts/demo_scenario.py; \
	wait

# make eval ARGS="--all-ablations --sweep-confidence"
eval:
	$(BACKEND) python ../eval/run_eval.py $(ARGS)

# Prompt regression checks (eval/promptfoo/) - classify and verify prompts
# against fixed cases, through the same app/llm/registry.py the agent uses.
promptfoo:
	$(BACKEND) python ../eval/promptfoo/build_tests.py
	cd eval/promptfoo && npx --yes promptfoo@latest eval -c promptfooconfig.yaml

test:
	$(BACKEND) pytest

# Browser tests (frontend/e2e/) against the vite dev server with a mocked API.
e2e:
	cd frontend && pnpm exec playwright test

lint:
	$(BACKEND) ruff check app

# Everything containerized - nothing but Docker needed. Same as plain
# `docker compose up -d --build`: the setup container migrates, and seeds +
# ingests on first boot only (app/seed/bootstrap.py).
docker-up:
	docker compose up -d --build
	@echo "open http://localhost:5173 (staff login: priya.agent@example.com / dev-password)"

docker-down:
	docker compose down

# Self-hosted Langfuse on :3001 for tracing - see docker-compose.langfuse.yml.
langfuse:
	docker compose -f docker-compose.langfuse.yml -p langfuse up -d

langfuse-down:
	docker compose -f docker-compose.langfuse.yml -p langfuse down
