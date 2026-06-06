# Evals Package

Status: fixture dataset, executable fixture repositories, reusable fixture verification package, and local Markdown/JSON report builder. `apps/api/app/services/eval_runner.py` now delegates repository/file/command checks to `repopilot_evals.FixtureVerifier` instead of carrying duplicate API-local verifier logic.

Phase 9 is implemented by the local evaluation runner in `apps/api/app/services/eval_runner.py` with package-owned fixture verification in `repopilot_evals`.

Current scope:

- `benchmark_tasks.json` defines 31 tasks across docs, tests, bug fixes, small features, refactors, and security cases.
- `fixtures/python-service` is a runnable Python benchmark repository with route/service modules and pytest coverage for the task paths.
- `fixtures/web-dashboard` is a runnable JavaScript/TypeScript benchmark repository with dashboard files and an `npm test` smoke.
- `repopilot_evals.FixtureVerifier` verifies fixture repositories, expected files, expected command targets, and executable repository markers for API and future CLI runners.
- `repopilot_evals.BenchmarkReportBuilder` writes local JSON and Markdown eval evidence reports from fixture checks plus optional observed plan, patch, and provider comparison evidence.
- `repopilot_evals.ProviderPlanningEvalRunner` can call OpenAI-compatible providers, Anthropic Messages, or Gemini GenerateContent for planning-only observed evidence without writing patches or mutating fixture repositories.
- `POST /evals/run` validates task schemas, delegates fixture checks to this package, scores per-task outcomes, records quality-gate results, and stores benchmark-versioned reports in `eval_runs`.
- `GET /evals/reports` returns historical reports and task outcomes inside report metrics.
- Metrics include task pass rate, fixture schema pass rate, fixture repository pass rate, fixture file coverage, category pass rates, plan approval rate, patch success rate, CI pass signal, security block rate, ready-for-review count, cost per run, and latency placeholders.

Generate a local report without touching the API:

```bash
PYTHONPATH=packages/evals:packages/shared_contracts python -m repopilot_evals.report \
  --out-dir Docs/eval-reports \
  --report-name v1-local-latest \
  --allow-failed-gates
```

Add optional model/provider evidence with:

```bash
PYTHONPATH=packages/evals:packages/shared_contracts python -m repopilot_evals.report \
  --observed-evidence /path/to/observed-evidence.json \
  --out-dir Docs/eval-reports \
  --report-name v1-provider-comparison
```

Run a provider-backed planning eval by saving the provider key in RepoPilot's encrypted local runtime secret store:

```bash
make configure-runtime-secrets
make provider-planning-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

The provider eval commands use `.local/repopilot-secrets/runtime-secrets.json` by default. Environment variables such as `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, and `GEMINI_API_KEY` still override the local store for CI and one-off runs.

Run retrieval-quality evidence with an embedding-capable model:

```bash
make provider-retrieval-eval PROVIDER=openrouter MODEL=text-embedding-3-small TASK_COUNT=5
```

The retrieval harness ranks fixture files for each issue, writes `v1-provider-retrieval.*` reports, and uses context precision as the quality signal. Providers without an embeddings endpoint produce failed retrieval evidence instead of a false pass.

Anthropic and Gemini can use the same harness without changing the report contract:

```bash
ANTHROPIC_API_KEY=... make provider-planning-eval PROVIDER=anthropic MODEL=claude-sonnet-4-6
GEMINI_API_KEY=... make provider-planning-eval PROVIDER=google MODEL=gemini-2.5-pro
```

Run applied patch evidence when you need stronger patch-quality proof:

```bash
make provider-applied-patch-eval PROVIDER=openrouter MODEL=gemma-4-31b-it:free TASK_COUNT=5
```

Applied patch evals copy fixture repositories into temporary workspaces, apply model-generated unified diffs, run only benchmark-declared validation commands, and write `v1-provider-applied-patch.*` reports. The fixture repositories are not mutated.

The benchmark task list and fixture repositories in this package are the portfolio/demo seed set. Future work can run model-by-model patch assertions and CI-backed checks against cloned copies of these fixtures.
