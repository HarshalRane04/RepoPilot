# RepoPilot

[![CI](https://github.com/HarshalRane04/RepoPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/HarshalRane04/RepoPilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](apps/api/Dockerfile)
[![Node.js 22](https://img.shields.io/badge/Node.js-22-339933.svg)](apps/web/Dockerfile)

## Brief Description

RepoPilot is a self-hosted control plane for running AI-assisted software-engineering work against GitHub repositories without giving models unrestricted access. It turns an issue into an auditable workflow: repository context, a human-reviewed plan, isolated implementation, validation and security evidence, and a gated draft pull request.

The operator console shows what a run is doing, why it is blocked, which tools the agent invoked, which checks passed, and what action is safe next. FastAPI and Celery orchestrate the workflow, PostgreSQL with pgvector stores state and evidence, and the sandbox runner executes allowlisted commands inside isolated workspaces.

![RepoPilot operator console showing an active run, approval state, validation results, and the next safe action](Docs/assets/readme/repopilot-overview-ui.png)

_The overview keeps the current task, lifecycle stage, trust gates, and next safe action in one review surface._

## What RepoPilot Does

1. Connects a GitHub repository or receives a supported issue event.
2. Retrieves bounded repository context and creates an implementation plan with source citations.
3. Pauses for a human to approve, reject, or revise the plan.
4. Runs approved implementation work through typed tools in an isolated workspace.
5. Records the patch, tool calls, tests, security checks, artifacts, and model metadata as reviewable evidence.
6. Opens a draft pull request only when repository authorization and required trust gates pass.

## Features

- **Operator console:** manage repositories, tasks, plans, runs, pull requests, security findings, evaluations, audit records, and runtime settings.
- **Human approval gates:** require approved plans before implementation or GitHub write operations.
- **Agent tool boundary:** route model actions through typed, permissioned, audited tools instead of arbitrary functions or shell access.
- **Repository context:** acquire repositories safely, index source, and retrieve bounded lexical/vector context with citations.
- **Isolated execution:** run allowlisted commands in authenticated, network-disabled sandbox workspaces with resource limits.
- **Evidence-based review:** bind validation and security evidence to the current patch before a run can advance.
- **GitHub integration:** support OAuth, GitHub App installations, signed webhooks, repository sync, CI evidence, and gated draft pull requests.
- **Provider-aware model routing:** validate models dynamically and bind encrypted API keys to the selected provider.
- **Auditability:** record state transitions, tool calls, artifacts, model traces, validation results, security findings, and pull-request actions.
- **Evaluation and release tooling:** provide fixture-backed evals, readiness checks, source-boundary scans, deployment validation, and security posture reports.

## Architecture

| Component | Technology | Responsibility |
| --- | --- | --- |
| Operator console | Next.js 16, React 19, TypeScript | Human review, configuration, evidence inspection, and workflow control |
| API | FastAPI, Pydantic, SQLAlchemy | Authentication, orchestration, policy enforcement, contracts, and GitHub/model integration |
| Database | PostgreSQL 16, pgvector, Alembic | Durable workflow state, audit records, artifacts, and repository embeddings |
| Queue | Redis, Celery | Asynchronous ingestion, implementation, validation, and reconciliation |
| Sandbox | Isolated Python service and Docker runtime | Authenticated, allowlisted, resource-bounded command execution |
| Integrations | GitHub App/OAuth and provider adapters | Repository events, draft pull requests, model calls, and CI evidence |

Runtime code lives in `apps/api`, `apps/web`, `packages`, and `services/sandbox_runner`. See [Architecture](Docs/ARCHITECTURE.md) for component boundaries and [Security](Docs/SECURITY.md) for the threat model.

## Installation

### Prerequisites

- Docker Desktop or a compatible Docker Engine with Compose
- Git
- GNU Make
- A POSIX-compatible shell
- Optional for host-side tooling: Python 3.12, Node.js 22, `uv`, `curl`, and `jq`

### Local installation

```bash
git clone https://github.com/HarshalRane04/RepoPilot.git
cd RepoPilot
make start-local
```

`make start-local` creates local-safe configuration, builds and starts the Compose stack, and applies database migrations.

Open:

- Operator console: [http://localhost:3001](http://localhost:3001)
- API health: [http://localhost:8000/health](http://localhost:8000/health)
- API readiness: [http://localhost:8000/ready](http://localhost:8000/ready)
- OpenAPI documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

For a step-by-step setup, published-container instructions, and credentialed smoke-test order, see the [Self-Hosted Quickstart](Docs/QUICKSTART.md).

### Configuration

The generated `.env` file contains local service wiring only and is excluded from Git. Save GitHub and model-provider credentials through **Settings** in the operator console or through the encrypted runtime-secret helper:

```bash
make configure-runtime-secrets
```

Important defaults:

- `GITHUB_WRITES_ENABLED=false`
- `ALLOW_MODEL_FALLBACK=false` outside local development
- `EMBEDDING_SOURCE_TRANSFER_ENABLED=false`
- runtime secrets stored under the ignored `.local/repopilot-secrets/` directory

Use an external secret manager and `REPOPILOT_RELEASE_PROFILE=production` for non-local deployments. Never commit `.env`, provider keys, GitHub private keys, session secrets, or runtime-secret stores.

## Usage

### Operator workflow

1. Configure a model provider and GitHub integration in **Settings**.
2. Connect or select a repository.
3. Create a task from the operator console or ingest a supported GitHub issue event.
4. Review the generated plan and approve, reject, or request a revision.
5. Start the approved run.
6. Inspect tool calls, patch provenance, validation output, security findings, and CI evidence.
7. Create a draft pull request only after required gates pass.

The intended lifecycle is:

```text
issue
  -> triage
  -> retrieve context
  -> generate plan
  -> human approval
  -> isolated implementation
  -> validation
  -> security review
  -> draft pull request
```

### Common commands

| Command | Purpose |
| --- | --- |
| `make start-local` | Initialize and start the local stack |
| `make logs` | Follow Compose service logs |
| `make down` | Stop the local stack |
| `make migrate` | Apply database migrations |
| `make api-test` | Run the API test suite |
| `make api-lint` | Run Ruff across Python source and tests |
| `pnpm -C apps/web test` | Run frontend regression tests |
| `pnpm -C apps/web typecheck` | Run TypeScript validation |
| `make web-build` | Build the production web image |
| `make readiness-snapshot` | Generate a redacted readiness report |
| `make deployment-validate` | Validate deployment topology and documentation |
| `make release-verify` | Run the strict credentialed release gate |

## Screenshots

### Agent Run Timeline

![RepoPilot agent run timeline showing execution steps, risk, runtime, cost, and pull-request context](Docs/assets/readme/repopilot-run-trace-ui.png)

_Every orchestration, tool, implementation, validation, security, and pull-request step is recorded in order with its outcome._

### Security Review

![RepoPilot security workspace showing scanner results and enforced workflow policies](Docs/assets/readme/repopilot-security-ui.png)

_The security workspace combines workflow findings with approval requirements, secret-reading protection, and the disabled auto-merge policy._

## Safety Model

RepoPilot is designed around the following invariants:

- No autonomous merges.
- No implementation before human plan approval.
- No unrestricted shell or arbitrary function access for models.
- No generated code applied outside isolated run workspaces.
- No GitHub writes without credentials, explicit write mode, authorization, validation evidence, and security gates.
- No implicit repository-source transfer to embedding providers.
- Every privileged action is attributable through audit and trace records.

Review [Docs/SECURITY.md](Docs/SECURITY.md) before enabling live providers or GitHub writes.

## Validation

Run the local validation set before opening a pull request:

```bash
docker compose config --quiet
make api-test
make api-lint
pnpm -C apps/web test
pnpm -C apps/web typecheck
python3 scripts/ui_truth_guard.py
python3 scripts/deployment_validate.py
python3 scripts/release_hygiene.py --allow-warnings
make web-build
make sandbox-image
```

Credentialed release environments should also run:

```bash
make release-verify
```

## Documentation

- [Documentation index](Docs/README.md)
- [Self-hosted quickstart](Docs/QUICKSTART.md)
- [Architecture](Docs/ARCHITECTURE.md)
- [GitHub App setup](Docs/GITHUB_APP_SETUP.md)
- [Model testing](Docs/MODEL_TESTING.md)
- [Runbook](Docs/RUNBOOK.md)
- [Deployment guide](Docs/DEPLOYMENT_GUIDE.md)
- [Roadmap](Docs/ROADMAP.md)
- [Release checklist](Docs/RELEASE_CHECKLIST.md)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before submitting changes.

Contributions must:

1. Keep behavior changes scoped and documented.
2. Add or update regression tests.
3. Preserve human approval, policy, sandbox, and audit boundaries.
4. Avoid committing secrets, generated artifacts, or local runtime state.
5. Pass the validation commands above.

## License

RepoPilot is available under the [MIT License](LICENSE).
