set shell := ["sh", "-eu", "-c"]

sync:
    uv run --project tools --locked --all-groups quality-sync

test:
    uv run --project tools --locked --all-groups quality-test

lint:
    uv run --project tools --locked --all-groups quality-lint

fmt:
    uv run --project tools --locked --all-groups quality-format

integration:
    uv run --project tools --locked --all-groups quality-integration

mutation:
    uv run --project tools --locked --all-groups quality-mutation

audit:
    uv run --project tools --locked --all-groups quality-audit

sql:
    uv run --project tools --locked --all-groups quality-sql

clean:
    uv run --project tools --locked project-clean

up:
    docker compose up -d --build

down:
    docker compose down

logs:
    docker compose logs -f api worker-outbox worker-pipeline worker-index

migrate:
    docker compose run --rm migrate

web:
    cd apps/web && bun install --frozen-lockfile && bun run test && bun run build

contracts:
    uv run --project tools --locked contracts-check

contracts-export:
    uv run --project tools --locked contracts-export

live-integration:
    for script in live_nats_smoke live_nats_dlq_smoke live_garage_smoke live_meili_smoke live_ingest_client_smoke; do docker compose exec -T api python - < services/main/test/$script.py || exit $?; done

compose-smoke:
    uv run --project tools --locked compose-smoke

reindex:
    docker compose exec -T api python - < tools/ops/reindex.py

pipeline-load:
    uv run --project tools --locked pipeline-load
