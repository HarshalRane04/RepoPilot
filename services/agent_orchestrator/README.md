# Agent Orchestrator Service

Status: scaffold only. This is a planned extraction boundary, not a separate deployable service in v1.

Runtime orchestration currently lives in `apps/api/app/services/`, the API routes, and the Celery worker; this directory is reserved for future extraction of a standalone orchestrator service.

The first persisted orchestration slice is implemented in `apps/api/app/services/planning.py`, `apps/api/app/services/implementation_agent.py`, and the `/issues`, `/plans`, and `/runs` routes.

Current scope:

- Retrieve repository context before planning.
- Create an `ImplementationPlan` from issue and context metadata.
- Persist a linked `Plan` and `AgentRun`.
- Record context retrieval, plan generation, and policy review as `agent_steps`.
- Hold the run in `WAIT_FOR_APPROVAL` until a human approves the plan.
- Copy an approved workspace into an isolated run directory.
- Generate a scoped pytest evidence patch in the copied workspace.
- Persist patch hashes, changed-file metadata, audit events, and sandbox validation output.
- Run security scans and block high or critical findings.
- Create local draft PR records after validation and security evidence pass.
- Ingest CI conclusions and promote clean successful runs to review.
- Enforce explicit state-machine transitions before implementation, validation, security, PR, and CI states.
- Normalize `/repopilot` issue-comment commands and PR-linked `workflow_run` events into audited control-plane inputs.
- Expose run traces and eval reports as release evidence.

General-purpose implementation agents and real GitHub branch/commit/PR writes remain intentionally gated until the authenticated GitHub client is configured and `GITHUB_WRITES_ENABLED=true`. The current implementation lane is intentionally scoped to generated tests in isolated workspaces and local draft PR records.
