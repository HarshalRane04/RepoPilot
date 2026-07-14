# Sandbox Runner Service

Status: active isolated execution service used by both source and GHCR deployments.

The execution boundary is implemented by `apps/api/app/services/sandbox.py`, the `/runs/{run_id}/sandbox` route, and this local sandbox image.

Current scope:

- Require an approved plan before sandbox execution.
- Re-check command policy before execution.
- Receive authenticated requests over a Unix-domain socket shared only with the API/worker.
- Run with Docker `network_mode: none`, a read-only root filesystem, dropped capabilities, CPU/memory/pid limits, and a scrubbed environment.
- Re-check command policy, exact run-workspace containment, request size, timeout, and output bounds inside the runner.
- Permit only an existing, non-symlink working directory contained by the exact run workspace, so monorepo validation can run from the relevant project root without weakening containment.
- Provide Python, the API dependency set, Node, npm, git, `pytest`, `ruff`, and `mypy` in the local image. Repository-specific dependencies still need a prebuilt cache or a purpose-built runner image; the networkless runner never installs packages at execution time.
- Persist command output as `validation_results` and `agent_steps`.
- Keep a `local` backend available only for controlled tests/development.

Build the runner image:

```bash
make sandbox-image
```

Generated patch execution happens in copied run workspaces. The API cannot invoke Docker and never receives the host Docker socket; the sandbox runner remains the only execution boundary for validation commands.
