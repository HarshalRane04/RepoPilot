# Security Policy

RepoPilot AI is a security-sensitive coding-agent project. Please report vulnerabilities privately and include enough detail for maintainers to reproduce and assess the issue.

## Supported Scope

The current supported scope is the local, single-tenant RepoPilot AI application in this repository:

- FastAPI API
- Next.js operator dashboard
- PostgreSQL/pgvector schema
- Redis/Celery worker flow
- Docker sandbox runner
- GitHub App and OAuth integration code
- Model gateway, tool execution, policy, validation, and security scanning code

## Reporting A Vulnerability

Until a public security contact is configured, open a private maintainer channel and include:

- Affected component and version or commit.
- Steps to reproduce.
- Impact and expected attacker capability.
- Logs, screenshots, or traces with secrets redacted.
- Suggested remediation if known.

Do not include live secrets, private keys, tokens, or exploit code that performs destructive actions.

## Security Expectations

- No autonomous merges.
- No code writes before approved plans.
- Model actions must pass through `ToolExecutor`.
- GitHub writes must be disabled unless explicitly configured.
- Secrets must never be committed, indexed, logged, or returned to the UI.
