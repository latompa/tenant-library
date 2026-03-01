.PHONY: run stop test migrate seed

run:
	docker compose up --build

stop:
	docker compose down

test:
	docker compose exec api pytest tests/ -v

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.seed_runner
