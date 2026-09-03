.PHONY: up down logs migrate shell seed test fmt

up:            ## start postgres, redis, main, worker and both classifiers
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f main worker

migrate:       ## apply migrations without restarting the API
	docker compose exec main alembic upgrade head

revision:      ## autogenerate a migration: make revision m="add x"
	docker compose exec main alembic revision --autogenerate -m "$(m)"

shell:
	docker compose exec main python

register-classifiers: ## register the bundled classifiers in a fresh install
	./scripts/register_classifiers.sh
