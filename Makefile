.PHONY: up down migrate seed test lint chaos-pool debug-sample logs

up:        ## bring up postgres, redis, api, worker
	docker compose up -d --build

down:
	docker compose down

migrate:   ## run Alembic migrations inside the api container
	docker compose exec api alembic upgrade head

seed:      ## alias kept for parity with docs/07 — nothing to seed in this slice yet
	$(MAKE) migrate

debug-sample: ## submit the bundled broken seed repo as a debug session
	curl -sS -X POST localhost:8000/api/debug-sessions \
		-H 'content-type: application/json' \
		-d @demo/seed_repo/sample_request.json

test:      ## run the pytest suite inside the api container
	docker compose exec api pytest -q

lint:      ## ruff + mypy + import-linter, inside the api container
	docker compose exec api ruff check src/
	docker compose exec api mypy src/haaland/services src/haaland/domain
	docker compose exec api lint-imports

logs:
	docker compose logs -f api worker
