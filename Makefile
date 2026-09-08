.PHONY: up down migrate seed ingest dev api worker frontend demo eval test lint

BACKEND=cd backend && . .venv/bin/activate &&

up:
	docker compose up -d
	@echo "waiting for postgres..."
	@until docker compose exec -T postgres pg_isready -U support -d support >/dev/null 2>&1; do sleep 1; done
	@docker compose exec -T postgres psql -U support -d support -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS citext;" >/dev/null

down:
	docker compose down

migrate:
	$(BACKEND) alembic upgrade head

seed:
	$(BACKEND) python -m app.seed.run

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
# "fresh, reproducible" reset docs/08-evaluation.md and CLAUDE.md call for,
# there is no separate `reset` target.
demo:
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) seed
	$(MAKE) ingest
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) api & \
	$(MAKE) worker & \
	$(MAKE) frontend & \
	$(BACKEND) python ../scripts/demo_scenario.py; \
	wait

eval:
	$(BACKEND) python ../eval/run_eval.py

test:
	$(BACKEND) pytest

lint:
	$(BACKEND) ruff check app
