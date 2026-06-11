# Sandbox Runner Service

Status: scaffold only. This is a planned extraction boundary, not a separate deployable service in v1.

Phase 8 is implemented by `apps/api/app/services/sandbox.py`, the `/runs/{run_id}/sandbox` route, and this local sandbox image.

Current scope:

- Require an approved plan before sandbox execution.
- Re-check command policy before execution.
- Run through Docker by default with `--network none`, CPU/memory/pid limits, and a scrubbed environment.
- Provide Python, Node, npm, git, `pytest`, `ruff`, and `mypy` in the local image.
- Persist command output as `validation_results` and `agent_steps`.
- Keep a `local` backend available only for controlled tests/development.

Build the image:

```bash
make sandbox-image
```

Generated patch execution now happens in copied workspaces through the Phase 9 implementation lane. The sandbox remains the only execution boundary for validation commands.
