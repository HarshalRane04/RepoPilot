# CI Analyzer Service

Status: service scaffold. Runtime implementation currently lives in `apps/api/app/services/ci_analyzer.py`; this directory is reserved for future extraction of GitHub Actions log retrieval and CI analysis workers.

Phase 10 is implemented in `apps/api/app/services/ci_analyzer.py`, the `/prs/{pr_id}/ci` route, and PR-linked `workflow_run` webhook normalization.

Current scope:

- Accept workflow name, conclusion, and log text.
- Extract concise failure signals from CI logs.
- Persist `WAIT_FOR_CI` and `READY_FOR_REVIEW` run steps.
- Promote clean successful runs only when validation passed and no high or critical findings are open.
- Route PR-linked `workflow_run` events through the same analyzer once a local/real PR record is known.

The current implementation still uses local workflow summaries rather than fetching full GitHub Actions logs. The credentialed GitHub client should add checks/log retrieval behind the same service contract.
