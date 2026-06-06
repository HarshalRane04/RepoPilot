# Evaluations

Evaluation work now has a fixture-backed local benchmark runner after the secure issue-to-PR workflow exists.

Current pre-evaluation checks:

- Webhook signature validation tests.
- Webhook payload normalization tests.
- Deterministic triage tests for bug and prompt-injection cases.
- Repository chunking and line-citation tests.
- Policy allow, deny, and escalation tests.
- Sandbox command-blocking tests.
- Executor-mediated implementation-agent tests for isolated workspace generation, approved path enforcement, real source/test patching, and validation.
- Service tests for security lifecycle, CI summarization, revision planning, GitHub permissions, and metric ratios.
- Dashboard typecheck/build and npm audit.

Implemented benchmark categories in `packages/evals/benchmark_tasks.json`:

- 5 documentation updates.
- 5 tests-only tasks.
- 8 small bug fixes.
- 5 small API/UI features.
- 3 refactors.
- 5 security tasks.

Executable fixture repositories:

- `packages/evals/fixtures/python-service`: runnable Python service fixture with route/service modules and pytest coverage for the benchmark file paths.
- `packages/evals/fixtures/web-dashboard`: runnable dashboard fixture with `npm test` smoke coverage for local-mode labeling.
- `packages/evals/repopilot_evals`: package-owned fixture verifier used by the API eval runner for repository, file, command-target, and executable-marker checks.
- `packages/evals/repopilot_evals.PlanQualityScorer`: package-owned observed plan scorer for intended target files, disallowed paths, validation commands, human-approval requirements, summary intent, and context citation precision.
- `packages/evals/repopilot_evals.PatchQualityScorer`: package-owned observed patch scorer for changed files, disallowed changes, summary intent, validation commands, validation status, and security result.
- `packages/evals/repopilot_evals.ProviderComparisonScorer`: package-owned provider/model scorer for blended plan quality, patch quality, context precision, inverse human edit distance, cost, and latency ranking.
- `packages/evals/repopilot_evals.BenchmarkReportBuilder`: package-owned Markdown/JSON report generator for local fixture proof plus optional observed model/provider evidence.
- `packages/evals/repopilot_evals.ProviderPlanningEvalRunner`: package-owned planning-only provider harness that reads the API key from an environment variable, calls OpenAI-compatible providers, Anthropic Messages, or Gemini GenerateContent through the shared provider adapter layer, and writes observed plan/provider evidence without writing patches.

Metrics to track:

- Task pass rate.
- Fixture schema pass rate.
- Fixture repository pass rate.
- Fixture file coverage rate.
- Category pass rates.
- Plan quality observed count.
- Plan quality pass rate.
- Context precision.
- Plan approval rate.
- Context precision.
- Patch success rate.
- Patch quality observed count.
- Patch quality pass rate.
- Provider comparison count.
- Best provider by quality.
- First-run CI pass rate.
- CI pass after one revision.
- Security block rate.
- Human edit distance.
- Cost per run.
- Latency per stage.

Implemented local endpoints:

- `POST /evals/run`: loads the fixture dataset, validates task schemas, scores per-task outcomes, records quality-gate results, and persists an `eval_runs` report.
- The runner verifies fixture repository existence, expected changed-file presence, expected validation command targets, and executable repository markers before a task can pass.
- The runner can also score optional `model_config.observed_plan_results`, `model_config.observed_task_results`, and `model_config.provider_eval_results` entries against benchmark expectations and records plan quality, context precision, patch quality, human edit distance, provider comparison ranking, per-task observed results, and release gates.
- The runner now reuses the platform CI metrics calculator for first-run CI pass rate, latest CI pass rate, pass-after-revision rate, revised PR count, and fixup-attempt totals from persisted PR/run/plan/CI-step evidence.
- `GET /evals/reports`: lists benchmark version, metrics, per-task outcomes inside metrics, report URI, and creation time.

Implemented local report artifact:

- `Docs/eval-reports/v1-local-latest.md`: human-readable local fixture report.
- `Docs/eval-reports/v1-local-latest.json`: machine-readable local fixture report.
- `make eval-report`: regenerates both files with failed release gates allowed, so the report remains honest about missing observed plan/patch/provider evidence.
- `make provider-planning-eval`: runs the planning-only live-provider harness using the encrypted local runtime secret store first, then provider-specific environment variables as an override. It defaults to `PROVIDER=openrouter`, `MODEL=gemma-4-31b-it:free`, and `OPENROUTER_API_KEY` when an override is needed. Reports are written to `Docs/eval-reports/v1-provider-planning.*`.
- `make provider-retrieval-eval`: runs the provider-backed retrieval-quality harness using the encrypted local runtime secret store first, then provider-specific environment variables as an override. It calls an embedding-capable provider endpoint, retrieves fixture file citations for each benchmark issue, and feeds those citations into the existing context-precision gate. Reports are written to `Docs/eval-reports/v1-provider-retrieval.*`.
- `make provider-patch-eval`: runs the provider patch-attempt harness using the encrypted local runtime secret store first, then provider-specific environment variables as an override. It asks the model for patch evidence, scores changed files, validation commands, security result, and diff intent, and writes `Docs/eval-reports/v1-provider-patch.*`. It does not mutate fixtures or claim validation passed without supplied validation evidence.
- `.github/workflows/provider-planning-eval.yml`: runs the same planning-only provider harness from GitHub Actions with manual inputs for provider, model, task count, secret name, and optional base URL. Reports are uploaded as workflow artifacts rather than committed back to the repository.
- `.github/workflows/provider-retrieval-eval.yml`: runs the same retrieval-quality provider harness from GitHub Actions with manual inputs for provider, embedding-capable model, task count, secret name, and optional base URL. Reports are uploaded as workflow artifacts rather than committed back to the repository.
- `.github/workflows/provider-patch-eval.yml`: runs the patch-attempt provider harness from GitHub Actions with the same secret-name pattern and uploads Markdown, JSON, and observed-evidence artifacts.

Current reports are deterministic local fixture scores, optional observed plan/patch-quality scores, optional human edit distance, optional provider comparisons through `model_config.provider_eval_results`, provider-backed planning attempts, provider-backed patch-attempt evidence, and observed platform evidence from the database. Future credentialed model comparison can add an applied-patch executor that clones these fixture repositories, applies provider diffs in a sandbox, runs validation commands, submits observed plan evidence through `model_config.observed_plan_results`, submits observed patch evidence through `model_config.observed_task_results`, submits provider/model summaries through `model_config.provider_eval_results`, and compares output against expected files, disallowed changes, validation results, security results, context citations, human reference diffs, CI/mock-CI outcomes, cost, and latency without changing the API contract.
