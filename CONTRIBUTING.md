# Contributing To RepoPilot AI

Thanks for helping improve RepoPilot AI. This project is intentionally safety-first: agent behavior must remain human-approved, audited, policy-checked, and sandboxed.

## Development Workflow

1. Create or update an issue that explains the change.
2. Keep changes scoped to one feature, fix, or documentation update.
3. Add or update tests for behavior changes.
4. Run the relevant checks before opening a PR.
5. Do not commit local secrets, runtime stores, generated dependency folders, or build artifacts.

## Local Checks

```bash
docker compose config
docker compose run --rm api pytest apps/api/tests -q
docker compose run --rm web npm run typecheck
docker compose --profile tools build sandbox-image
```

## Safety Requirements

- Do not bypass `ToolExecutor` for model-triggered actions.
- Do not add raw shell execution paths for the model.
- Do not allow code writes before human plan approval.
- Bind generated diffs to approved plan hashes.
- Keep GitHub writes behind `GITHUB_WRITES_ENABLED=true`, configured credentials, validation evidence, and security gates.
- Redact secrets from logs, traces, prompts, audit metadata, and test fixtures.

## Pull Request Expectations

Every PR should include:

- Summary of the user-visible behavior.
- Tests or verification commands run.
- Security impact notes for auth, sandbox, model, GitHub, or file-system changes.
- Documentation updates when workflows or configuration change.
