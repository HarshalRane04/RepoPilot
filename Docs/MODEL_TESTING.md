# Model Testing

RepoPilot keeps live model testing behind explicit credentials, planning-only eval workflows, and human approval gates. No provider key should be committed to this repository.

## GitHub Actions Provider Eval

Use the manual **Provider Planning Eval** workflow when the code has been pushed to GitHub and you want provider-backed planning evidence.

1. Add one or more repository secrets in GitHub:

   - `OPENROUTER_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `GEMINI_API_KEY`
   - `MODEL_API_KEY` for a custom provider secret name

2. Open GitHub Actions, choose **Provider Planning Eval**, and run it with:

   - `provider`: `openrouter`, `anthropic`, or `google`
   - `model`: provider model id, for example `gemma-4-31b-it:free`
   - `task_count`: start with `5`
   - `api_key_secret`: the repository secret name that stores the provider key
   - `base_url`: only set this for OpenAI-compatible custom endpoints

3. Download the workflow artifact named `provider-planning-eval-<run_id>`.

The workflow writes `Docs/eval-reports/v1-provider-planning.md` and `.json` inside the runner workspace, then uploads those reports as artifacts. It does not write patches, push branches, open pull requests, or mutate fixture repositories.

Use the manual **Provider Patch Eval** workflow when you want provider-backed patch-attempt evidence without applying patches. It uses the same provider/model/secret-name inputs, writes `Docs/eval-reports/v1-provider-patch.md`, `.json`, and `.observed-evidence.json`, then uploads them as artifacts. It scores expected files, disallowed changes, validation commands, security result, and diff intent, but it does not claim validation passed unless explicit validation evidence is supplied.

## Local Provider Eval

For local testing, set the provider key in your shell and run the same harness:

```bash
export OPENROUTER_API_KEY=...
make provider-planning-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

Patch-attempt eval:

```bash
make provider-patch-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

Anthropic and Gemini use the same target with their provider-specific key variables:

```bash
export ANTHROPIC_API_KEY=...
make provider-planning-eval PROVIDER=anthropic MODEL=claude-sonnet-4-6 TASK_COUNT=5

export GEMINI_API_KEY=...
make provider-planning-eval PROVIDER=google MODEL=gemini-2.5-pro TASK_COUNT=5
```

## Runtime Gateway Smoke

To test the API model gateway locally, place provider settings in `.env`:

```bash
MODEL_PROVIDER=openrouter
MODEL_NAME=gemma-4-31b-it:free
MODEL_API_KEY=...
MODEL_BASE_URL=https://openrouter.ai/api/v1
```

Restart the API and open the dashboard settings page. The readiness panel should show the model gateway as configured only after a verification run records the selected provider and model. LLM traces should store provider, model, call mode, hashes, token/cost metadata when available, and redacted metadata only.

## Guardrails

- Provider planning evals are evidence collection only.
- Generated code still requires approved plans, policy checks, sandbox validation, security scanning, and explicit GitHub write readiness before a draft PR can be opened.
- GitHub Actions secrets should be rotated if they are pasted into logs, issue text, comments, or local files.
