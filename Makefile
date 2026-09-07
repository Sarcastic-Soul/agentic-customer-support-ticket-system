.PHONY: up down migrate seed dev demo eval test lint fmt

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

dev:
	$(BACKEND) uvicorn app.main:app --reload --port 8000

demo:
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) seed
	$(MAKE) dev

eval:
	$(BACKEND) python ../eval/run_eval.py

test:
	$(BACKEND) pytest

lint:
	$(BACKEND) ruff check app
