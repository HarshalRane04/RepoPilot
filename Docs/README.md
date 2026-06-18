# RepoPilot Public Documentation

This folder contains the documentation intended for the public open-source release candidate. Generated evidence, local screenshots, raw smoke-test JSON, and internal planning drafts are intentionally not checked into the public source tree.

## Start Here

- [Quickstart](QUICKSTART.md): local self-hosted startup path.
- [Architecture](ARCHITECTURE.md): system boundaries and safety model.
- [Deployment Guide](DEPLOYMENT_GUIDE.md): Compose, GHCR, secrets, storage, observability, rollback, and production gates.
- [GitHub App Setup](GITHUB_APP_SETUP.md): GitHub App permissions, webhook setup, and credential flow.
- [Credential Handoff](CREDENTIAL_HANDOFF.md): exact secrets and live proof steps needed before write-mode testing.
- [Runbook](RUNBOOK.md): operational checks and troubleshooting.
- [Security](SECURITY.md): reporting, scanner posture, and safety guarantees.
- [Evaluations](EVALS.md) and [Model Testing](MODEL_TESTING.md): local and provider-backed quality gates.
- [Roadmap](ROADMAP.md): current release-candidate gaps before `v1.0.0`.
- [Release Checklist](RELEASE_CHECKLIST.md) and [Release Notes](RELEASE_NOTES.md): public release criteria and RC notes.

## Generated Evidence

The following directories are placeholders for local and CI-generated evidence:

- `Docs/eval-reports/`
- `Docs/release-artifacts/`

Commands such as `make eval-report`, `make release-hygiene`, `make deployment-validate`, `make credential-smoke`, and the GitHub release workflow write reports into those locations or upload them as workflow artifacts. Generated evidence should be reviewed, archived externally when needed, and kept out of normal source commits unless a maintainer deliberately promotes a small proof artifact.
