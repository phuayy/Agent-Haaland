.PHONY: up down migrate seed backfill web test lint chaos-pool debug-sample lark-check lark-send logs

up:        ## bring up postgres, redis, api, worker
	docker compose up -d --build

down:
	docker compose down

migrate:   ## run Alembic migrations inside the api container
	docker compose exec api alembic upgrade head

seed:      ## migrate, then put demo services in the registry the dashboard reads
	$(MAKE) migrate
	docker compose exec api python scripts/seed_services.py

backfill:  ## link incidents opened before the service registry existed
	docker compose exec api python scripts/backfill_incident_services.py --dry-run
	docker compose exec api python scripts/backfill_incident_services.py

# Direct mode: the dashboard talks to the API origin itself, so Add Service and
# Trigger work. With NEXT_PUBLIC_API_URL unset it proxies through /dash-api
# instead, which forwards GET only — that is the deployed, read-only build.
web:       ## run the dashboard against the local API
	cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

debug-sample: ## submit the bundled broken seed repo as a debug session
	curl -sS -X POST localhost:8000/api/debug-sessions \
		-H 'content-type: application/json' \
		-d @demo/seed_repo/sample_request.json

lark-check: ## verify the Lark connection (token + chat list), sends nothing
	docker compose exec api python scripts/lark_check.py

lark-send: ## same, then post a real test card to the configured destination
	docker compose exec api python scripts/lark_check.py --send

test:      ## run the pytest suite inside the api container
	docker compose exec api pytest -q

lint:      ## ruff + mypy + import-linter, inside the api container
	docker compose exec api ruff check src/
	docker compose exec api mypy src/haaland/services src/haaland/domain
	docker compose exec api lint-imports

logs:
	docker compose logs -f api worker
