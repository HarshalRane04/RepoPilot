COMPOSE ?= docker compose
PYTHON ?= python3
PROVIDER ?= openrouter
MODEL ?= gemma-4-31b-it:free
TASK_COUNT ?= 5
API_KEY_ENV ?=
BASE_URL ?=
LOCAL_RUNTIME_SECRET_ENV = REPOPILOT_RUNTIME_SECRETS_KEY_PATH=.local/repopilot-secrets/runtime-secrets.key REPOPILOT_RUNTIME_SECRETS_STORE_PATH=.local/repopilot-secrets/runtime-secrets.json

.PHONY: up down logs migrate migration-verify api-test web-typecheck sandbox-image configure-runtime-secrets eval-report provider-planning-eval provider-patch-eval model-provider-smoke github-app-smoke github-oauth-smoke source-boundary-manifest readiness-snapshot security-scanner-snapshot release-gifs release-hygiene deployment-validate deployment-smoke

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

configure-runtime-secrets:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) $(PYTHON) scripts/configure_runtime_secrets.py

eval-report:
	env PYTHONPATH=packages/evals:packages/shared_contracts uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.report --out-dir Docs/eval-reports --report-name v1-local-latest --allow-failed-gates

provider-planning-eval:
	env PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-planning --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

provider-patch-eval:
	env PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_patch_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-patch --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

model-provider-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/model_provider_smoke.py --allow-blocked

github-app-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/github_app_smoke.py --allow-blocked

github-oauth-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/github_oauth_smoke.py --allow-blocked

source-boundary-manifest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/source_boundary_manifest.py

readiness-snapshot:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/readiness_snapshot.py

security-scanner-snapshot:
	PYTHONDONTWRITEBYTECODE=1 SEMGREP_ENABLED=true DEPENDENCY_AUDIT_ENABLED=true CODEQL_ENABLED=true uv run --with semgrep --with pip-audit python scripts/security_scanner_snapshot.py --allow-warnings --allow-blockers

release-gifs:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_gifs.py

release-hygiene:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_hygiene.py --json-out Docs/release-artifacts/source-boundary-hygiene.json --md-out Docs/release-artifacts/source-boundary-hygiene.md --allow-warnings --allow-failures

deployment-validate:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --json-out Docs/release-artifacts/deployment-validation.json --md-out Docs/release-artifacts/deployment-validation.md --allow-warnings --allow-failures

deployment-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --check-runtime --json-out Docs/release-artifacts/deployment-runtime-smoke.json --md-out Docs/release-artifacts/deployment-runtime-smoke.md --allow-warnings --allow-failures
