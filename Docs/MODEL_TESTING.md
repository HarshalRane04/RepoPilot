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

Use the manual **Provider Retrieval Eval** workflow when you want provider-backed context-retrieval evidence. It uses an embedding-capable provider model and writes `Docs/eval-reports/v1-provider-retrieval.md`, `.json`, and `.observed-evidence.json`, then uploads them as artifacts. It scores retrieved fixture file citations through the existing context-precision gate.

Use the manual **Provider Patch Eval** workflow when you want provider-backed patch-attempt evidence without applying patches. It uses the same provider/model/secret-name inputs, writes `Docs/eval-reports/v1-provider-patch.md`, `.json`, and `.observed-evidence.json`, then uploads them as artifacts. It scores expected files, disallowed changes, validation commands, security result, and diff intent, but it does not claim validation passed unless explicit validation evidence is supplied.

Use the manual **Provider Applied Patch Eval** workflow when you want stronger patch proof. It copies fixture repositories to temporary workspaces, applies model-generated unified diffs, runs only benchmark-declared validation commands, writes `Docs/eval-reports/v1-provider-applied-patch.md`, `.json`, and `.observed-evidence.json`, then uploads them as artifacts. Fixture repositories are not mutated.

## Local Provider Eval

For local testing, save the provider key in RepoPilot's encrypted runtime secret store and run the same harness:

```bash
make configure-runtime-secrets
make provider-planning-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

The provider eval commands read `MODEL_API_KEY`, `MODEL_PROVIDER`, and `MODEL_BASE_URL` from `.local/repopilot-secrets/runtime-secrets.json` by default. Environment variables such as `OPENROUTER_API_KEY` still override the local store, which is useful for one-off tests and mirrors GitHub Actions behavior.

Patch-attempt eval:

```bash
make provider-patch-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

Applied patch eval:

```bash
make provider-applied-patch-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

Applied patch evals are the preferred local proof for patch quality once a model provider is configured. They apply generated diffs to temporary copies of benchmark fixtures and run only the fixture-declared validation commands.

Retrieval-quality eval:

```bash
make provider-retrieval-eval PROVIDER=openrouter MODEL=text-embedding-3-small TASK_COUNT=5
```

Retrieval evals call the provider embeddings endpoint and write `Docs/eval-reports/v1-provider-retrieval.*`. Use an embedding-capable model for the selected provider; if the provider does not expose embeddings, the report records blocked/failed retrieval evidence instead of claiming context quality.

Anthropic and Gemini use the same targets after the local store is configured for that provider, or with their provider-specific environment variables:

```bash
export ANTHROPIC_API_KEY=...
make provider-planning-eval PROVIDER=anthropic MODEL=claude-sonnet-4-6 TASK_COUNT=5

export GEMINI_API_KEY=...
make provider-planning-eval PROVIDER=google MODEL=gemini-2.5-pro TASK_COUNT=5
```

## Runtime Gateway Smoke

To test the API model gateway locally, save provider settings through the dashboard Settings screen or encrypted runtime secret helper:

```bash
make configure-runtime-secrets
```

Restart the API if it was already running, then open the dashboard settings page and run model verification. The readiness panel should show the model gateway as configured only after a verification run records the selected provider and model. LLM traces should store provider, model, call mode, hashes, token/cost metadata when available, and redacted metadata only.

## Guardrails

- Provider planning evals are evidence collection only.
- Generated code still requires approved plans, policy checks, sandbox validation, security scanning, and explicit GitHub write readiness before a draft PR can be opened.
- GitHub Actions secrets should be rotated if they are pasted into logs, issue text, comments, or local files.
