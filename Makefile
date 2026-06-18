COMPOSE ?= docker compose
COMPOSE_GHCR ?= $(COMPOSE) -f docker-compose.ghcr.yml
PYTHON ?= python3
PROVIDER ?= openrouter
MODEL ?= gemma-4-31b-it:free
TASK_COUNT ?= 5
API_KEY_ENV ?=
BASE_URL ?=
LOCAL_RUNTIME_SECRET_ENV = REPOPILOT_RUNTIME_SECRETS_KEY_PATH=.local/repopilot-secrets/runtime-secrets.key REPOPILOT_RUNTIME_SECRETS_STORE_PATH=.local/repopilot-secrets/runtime-secrets.json

.PHONY: init-local-env start-local bootstrap up down logs migrate migration-verify api-test web-typecheck ui-truth-guard sandbox-image ghcr-config ghcr-pull ghcr-up ghcr-start-local ghcr-down ghcr-logs ghcr-migrate configure-runtime-secrets eval-report provider-planning-eval provider-retrieval-eval provider-patch-eval provider-applied-patch-eval model-provider-smoke github-app-smoke github-oauth-smoke credential-smoke credential-smoke-strict source-boundary-manifest readiness-snapshot security-scanner-snapshot security-scanner-snapshot-strict release-gifs release-hygiene release-hygiene-strict deployment-validate deployment-validate-strict deployment-smoke deployment-smoke-strict release-verify

init-local-env:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/init_local_env.py

start-local: init-local-env up migrate sandbox-image
	@printf "\nRepoPilot local stack is ready.\n"
	@printf "Dashboard: http://localhost:3001\n"
	@printf "API health: http://localhost:8000/health\n"
	@printf "API docs: http://localhost:8000/docs\n\n"

bootstrap: start-local

up:
	$(COMPOSE) up -d --build

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

ui-truth-guard:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/ui_truth_guard.py

sandbox-image:
	$(COMPOSE) --profile tools build sandbox-image

ghcr-config: init-local-env
	$(COMPOSE_GHCR) config --quiet

ghcr-pull: init-local-env
	$(COMPOSE_GHCR) pull

ghcr-up: init-local-env
	$(COMPOSE_GHCR) up -d

ghcr-start-local: init-local-env ghcr-pull ghcr-up ghcr-migrate
	@printf "\nRepoPilot GHCR stack is ready.\n"
	@printf "Dashboard: http://localhost:3001\n"
	@printf "API health: http://localhost:8000/health\n"
	@printf "API docs: http://localhost:8000/docs\n\n"

ghcr-down:
	$(COMPOSE_GHCR) down

ghcr-logs:
	$(COMPOSE_GHCR) logs -f

ghcr-migrate:
	$(COMPOSE_GHCR) exec api alembic upgrade head

configure-runtime-secrets:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) $(PYTHON) scripts/configure_runtime_secrets.py

eval-report:
	env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/evals:packages/shared_contracts uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.report --out-dir Docs/eval-reports --report-name v1-local-latest --allow-failed-gates

provider-planning-eval:
	env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-planning --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

provider-retrieval-eval:
	env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_retrieval_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-retrieval --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

provider-patch-eval:
	env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_patch_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-patch --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

provider-applied-patch-eval:
	env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/evals:packages/shared_contracts:packages/llm_client $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python -m repopilot_evals.provider_applied_patch_harness --provider $(PROVIDER) --model $(MODEL) --task-count $(TASK_COUNT) --out-dir Docs/eval-reports --report-name v1-provider-applied-patch --allow-failed-gates $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV),) $(if $(BASE_URL),--base-url $(BASE_URL),)

model-provider-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/model_provider_smoke.py --allow-blocked

github-app-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/github_app_smoke.py --allow-blocked

github-oauth-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/github_oauth_smoke.py --allow-blocked

credential-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/credential_smoke.py --allow-blocked

credential-smoke-strict:
	PYTHONDONTWRITEBYTECODE=1 $(LOCAL_RUNTIME_SECRET_ENV) uv run --with-requirements apps/api/requirements.txt python scripts/credential_smoke.py

source-boundary-manifest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/source_boundary_manifest.py

readiness-snapshot:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/readiness_snapshot.py

security-scanner-snapshot:
	PYTHONDONTWRITEBYTECODE=1 SEMGREP_ENABLED=true DEPENDENCY_AUDIT_ENABLED=true CODEQL_ENABLED=true uv run --with semgrep --with pip-audit python scripts/security_scanner_snapshot.py --allow-warnings --allow-blockers

security-scanner-snapshot-strict:
	PYTHONDONTWRITEBYTECODE=1 SEMGREP_ENABLED=true DEPENDENCY_AUDIT_ENABLED=true CODEQL_ENABLED=true uv run --with semgrep --with pip-audit python scripts/security_scanner_snapshot.py

release-gifs:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_gifs.py

release-hygiene:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_hygiene.py --json-out Docs/release-artifacts/source-boundary-hygiene.json --md-out Docs/release-artifacts/source-boundary-hygiene.md --allow-warnings --allow-failures

release-hygiene-strict:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/release_hygiene.py --json-out Docs/release-artifacts/source-boundary-hygiene.json --md-out Docs/release-artifacts/source-boundary-hygiene.md

deployment-validate:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --json-out Docs/release-artifacts/deployment-validation.json --md-out Docs/release-artifacts/deployment-validation.md --allow-warnings --allow-failures

deployment-validate-strict:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --json-out Docs/release-artifacts/deployment-validation.json --md-out Docs/release-artifacts/deployment-validation.md

deployment-smoke:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --check-runtime --json-out Docs/release-artifacts/deployment-runtime-smoke.json --md-out Docs/release-artifacts/deployment-runtime-smoke.md --allow-warnings --allow-failures

deployment-smoke-strict:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/deployment_validate.py --check-runtime --json-out Docs/release-artifacts/deployment-runtime-smoke.json --md-out Docs/release-artifacts/deployment-runtime-smoke.md

release-verify: source-boundary-manifest release-hygiene-strict ui-truth-guard credential-smoke-strict security-scanner-snapshot-strict deployment-validate-strict deployment-smoke-strict
