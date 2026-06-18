# RepoPilot Release-Candidate Roadmap

RepoPilot is public as an open-source release candidate. It should not be described as production-ready until the proof gates below pass with current evidence.

## Completed RC Proof

- Public repository visibility is enabled.
- CI is green on `main`.
- CodeQL runs successfully after public code scanning became available.
- Local source-build validation, API tests, web typecheck, release hygiene, deployment validation, and release-image dry-run builds have passed.
- The operator console, local control plane, safety gates, audit surfaces, and mocked/local workflow are implemented enough for public review.

## Remaining Before `v1.0.0`

1. Publish GHCR images from a strict release run and verify package visibility from a fresh account or host.
2. Run `make ghcr-start-local` from a clean clone using the published image tag.
3. Add live GitHub App, OAuth, webhook, session, and model-provider credentials through runtime secrets or GitHub Actions secrets.
4. Run credential smoke in read-only mode with `GITHUB_WRITES_ENABLED=false`.
5. Use a disposable demo repository to prove issue webhook intake, planning, approval, sandbox implementation, real draft PR creation, and CI ingestion.
6. Enable `GITHUB_WRITES_ENABLED=true` only after read-only verification and write-smoke readiness pass.
7. Run provider-backed planning, retrieval, patch-attempt, and applied-patch evals.
8. Record plan quality, context precision, patch quality, human edit distance, provider comparison, cost, and latency evidence.
9. Keep autonomous merge out of scope.

## Credential Moment

The next point that requires user-provided credentials is live proof. Local tests can continue without secrets, but these checks cannot be completed honestly until the operator provides:

- GitHub App ID, installation ID, and private key or private-key file path.
- GitHub OAuth client ID and client secret.
- GitHub webhook secret.
- Session secret key for non-local deployment.
- At least one model-provider API key and selected model names.
- A disposable GitHub repository where RepoPilot is allowed to open a draft PR.
