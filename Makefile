COMPOSE ?= docker compose
PYTHON ?= python3
PROVIDER ?= openrouter
MODEL ?= gemma-4-31b-it:free
TASK_COUNT ?= 5

.PHONY: up down logs migrate migration-verify api-test web-typecheck sandbox-image eval-report provider-planning-eval source-boundary-manifest readiness-snapshot security-scanner-snapshot release-gifs release-hygiene deployment-validate deployment-smoke

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate:
	$(COMPOSE) exec api alembic upgrade head

migration-verify:
	$(COMPOSE) exec api python -m app.db.migration_verifier

api-test:
	$(COMPOSE) exec api pytest

web-typecheck:
	$(COMPOSE) exec web npm run typecheck

sandbox-image:
	$(COMPOSE) --profile tools build sandbox-image

eval-report:
	env PYTHONPATH=packages/evals:packages/shared_contracts uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.report --out-dir Docs/eval-reports --report-name v1-local-latest --allow-failed-gates

provider-planning-eval:
	env PYTHONPATH=packages/evals:packages/shared_contracts uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-planning --allow-failed-gates

source-boundary-manifest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/source_boundary_manifest.py

readiness-snapshot:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/readiness_snapshot.py

security-scanner-snapshot:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/security_scanner_snapshot.py --allow-warnings --allow-blockers

release-gifs:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_gifs.py

release-hygiene:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_hygiene.py --json-out Docs/release-artifacts/source-boundary-hygiene.json --md-out Docs/release-artifacts/source-boundary-hygiene.md --allow-warnings --allow-failures

deployment-validate:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --json-out Docs/release-artifacts/deployment-validation.json --md-out Docs/release-artifacts/deployment-validation.md --allow-warnings --allow-failures

deployment-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --check-runtime --json-out Docs/release-artifacts/deployment-runtime-smoke.json --md-out Docs/release-artifacts/deployment-runtime-smoke.md --allow-warnings --allow-failures
