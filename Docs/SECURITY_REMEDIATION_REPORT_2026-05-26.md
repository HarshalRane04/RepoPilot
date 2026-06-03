# RepoPilot Security Remediation Report

Date: 2026-05-26
Scope: Static application security remediation for the RepoPilot API, tool execution layer, sandbox, runtime settings, and Docker development stack.

## Executive Summary

This report documents the remediation of 8 security issues identified during the RepoPilot application security audit. The fixes focused on fail-closed authentication, route protection, workspace isolation, sandbox containment, server-side tool-call authority, SSRF prevention, infrastructure hardening, and request/response middleware defenses.

All 8 requested vulnerabilities have been patched. Verification completed successfully with Python compilation, API tests, and Docker Compose configuration rendering.

Severity breakdown:

| Severity | Count | Status |
| --- | ---: | --- |
| Critical | 3 | Fixed |
| High | 3 | Fixed |
| Medium | 2 | Fixed |
| Low | 0 | Not applicable |

Verification results:

```text
/Users/harshalrane/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m compileall -q apps/api/app apps/api/tests
PASS

/Users/harshalrane/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pytest apps/api/tests -q
49 passed in 0.93s

POSTGRES_PASSWORD=test-postgres REDIS_PASSWORD=test-redis GITHUB_WEBHOOK_SECRET=test-webhook SESSION_SECRET_KEY=test-session-secret-01234567890123456789 docker compose config --quiet
PASS
```

## Detailed Findings And Fixes

### 1. Fail-Open Development Header Authentication

Severity: Critical
Category: Broken Authentication / Improper Authentication

Locations changed:

- `apps/api/app/services/auth.py`
- `apps/api/app/core/config.py`
- `apps/api/tests/test_api_routes.py`

Issue:

The authentication dependency allowed development header identity to act as a fallback. In a non-local deployment, a caller could potentially authenticate by supplying `X-RepoPilot-User` and `X-RepoPilot-Role` headers if that path remained enabled.

Impact:

An attacker with network access to the API could impersonate privileged users, access protected resources, and perform control-plane actions without a valid session.

Fix implemented:

- Added `DEV_HEADER_AUTH_ENABLED`, defaulting to `false`.
- Header-based development auth is only honored when both conditions are true:
  - `DEV_HEADER_AUTH_ENABLED=true`
  - `REPOPILOT_ENV=local`
- Valid signed session cookies are checked first.
- Missing or invalid authentication now returns `401 Authentication required`.
- Tests now explicitly opt into local dev header auth only when needed.

Why the fix works:

The authentication path now fails closed. Development-only identity injection cannot be accidentally used in production or staging, and protected requests must present either a valid session cookie or an explicitly enabled local development configuration.

Representative secure behavior:

```python
if config.dev_header_auth_enabled and config.environment == "local":
    return CurrentUser(...)
raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
```

### 2. Unprotected Control-Plane Routers

Severity: Critical
Category: Broken Access Control

Locations changed:

- `apps/api/app/api/router.py`
- `apps/api/tests/test_api_routes.py`
- `apps/api/tests/test_tool_registry.py`

Issue:

Several API routers were mounted directly on the application router without a global authentication dependency. This made route protection dependent on individual route handlers and increased the chance of accidental unauthenticated exposure.

Impact:

Unauthenticated callers could potentially access repositories, runs, tools, plans, settings, metrics, security findings, or other control-plane endpoints if individual routes omitted explicit authorization.

Fix implemented:

- Created a `protected_router` with `Depends(get_current_user)`.
- Mounted control-plane routers under `protected_router`.
- Left only intentional public routes outside the protected router:
  - `/health`
  - `/auth/*`
  - `/webhooks/*`
- Added a regression test asserting `/settings/readiness` returns `401` without authentication.

Why the fix works:

Authentication is now enforced at router composition time. New route handlers inside these protected routers inherit the dependency automatically, reducing the risk of missed per-endpoint checks.

Protected routers:

```text
/activity
/prompts
/installations
/repos
/issues
/plans
/runs
/tools
/prs
/security
/metrics
/evals
/settings
```

### 3. Arbitrary Local File Read And Repository Indexing

Severity: Critical
Category: Path Traversal / Local File Disclosure / Improper File Access Control

Locations changed:

- `apps/api/app/services/repo_indexer.py`
- `apps/api/app/services/tools/registry.py`
- `apps/api/app/core/config.py`
- `apps/api/tests/test_tool_registry.py`

Issue:

Repository indexing and model-facing read tools accepted caller-supplied filesystem paths. A privileged or compromised caller could direct the system to index or read sensitive host paths outside intended repository workspaces.

Impact:

Potential local file disclosure, source exfiltration outside the target repository, indexing of secrets, and exposure of host files to model/tool outputs.

Fix implemented:

- Added `REPOPILOT_REPOSITORY_WORKSPACE_ROOT`, defaulting to `/tmp/repopilot-repositories`.
- Repository indexing now resolves `source_path` and requires it to stay under `settings.repository_workspace_root`.
- Model-facing read tools now require the isolated run workspace `/tmp/repopilot-agent-workspaces/{run_id}`.
- Workspace copy creation only accepts source repositories under the configured repository workspace root.
- Child paths reject absolute paths and `..` traversal.

Why the fix works:

All file access now has two boundaries:

1. Repository sources must originate from a server-managed repository root.
2. Runtime read/write tools must operate in the isolated workspace for the current run ID.

This prevents arbitrary host path reads and prevents cross-run workspace access.

Key helper behavior:

```python
def _repository_workspace(workspace_path: str) -> Path:
    workspace = _workspace(workspace_path)
    root = Path(settings.repository_workspace_root).expanduser().resolve()
    if not workspace.is_relative_to(root):
        raise ToolBlocked(...)
    return workspace

def _isolated_workspace(run_id: UUID, workspace_path: str) -> Path:
    workspace = _workspace(workspace_path)
    expected = (WORKSPACE_ROOT / str(run_id)).resolve()
    if workspace != expected:
        raise ToolBlocked(...)
    return workspace
```

### 4. Sandbox Host Exposure Through Arbitrary Workspace Paths

Severity: High
Category: Sandbox Escape Surface / Improper Isolation

Locations changed:

- `apps/api/app/services/sandbox.py`
- `apps/api/app/api/routes/runs.py`
- `apps/api/app/services/implementation_agent.py`
- `apps/api/app/services/tools/registry.py`
- `apps/api/tests/test_phase5_to_8_services.py`

Issue:

Sandbox command execution accepted a caller-supplied workspace path. Even though commands were policy-filtered and Docker ran with `--network none`, arbitrary mounted workspaces could expose host directories to sandboxed processes.

Impact:

An attacker who could invoke sandboxed commands might mount sensitive host paths into the container or execute local commands over unintended directories.

Fix implemented:

- `SandboxRunner.run_command()` now requires a server-provided `run_id`.
- The workspace must exactly equal `/tmp/repopilot-agent-workspaces/{run_id}`.
- The local backend is blocked unless `REPOPILOT_ENV=local`.
- Docker execution was hardened with:
  - `--network none`
  - `--cap-drop ALL`
  - `--security-opt no-new-privileges`
  - memory, CPU, and PID limits
- All call sites now pass server-derived run IDs.

Why the fix works:

The caller can no longer choose what host path gets mounted into the sandbox. The sandbox mount is bound to the isolated run workspace, and local execution is limited to intentional local development.

### 5. Client-Controlled ToolExecutor Run ID, Actor, And State

Severity: High
Category: Broken Access Control / Privilege Escalation / IDOR

Locations changed:

- `apps/api/app/api/routes/runs.py`
- `apps/api/app/services/tools/registry.py`

Issue:

The tool execution API accepted a full model-facing `ToolCallRequest`, including `run_id`, `state`, `actor`, and nested arguments. A client could attempt to invoke tools against another run, forge the actor, or supply stale/mismatched state.

Impact:

Potential cross-run access, unauthorized run transitions, audit-log actor spoofing, and policy bypass attempts.

Fix implemented:

- Replaced public request bodies with limited route DTOs:
  - `RunToolCallBody`
  - `RunToolCallBatchBody`
- Public DTOs reject unknown top-level fields with `extra="forbid"`.
- The server now derives:
  - `run_id` from the URL and database run object
  - `state` from the database run state
  - `actor` as server-controlled `"user"`
- If nested tool arguments contain a `run_id`, it is overwritten with the server-derived run ID.
- `ToolExecutor` independently blocks parsed payloads whose `run_id` does not match the server tool-call run ID.
- Internal run/state/security/pr tool handlers now use `request.run_id` rather than payload IDs.

Why the fix works:

Authority now comes from server-side state, not client JSON. Even if a client supplies a conflicting nested run ID, the route overwrites it and the executor enforces the match after Pydantic parsing.

### 6. SSRF Through Model Provider Base URL

Severity: High
Category: Server-Side Request Forgery / Unsafe URL Handling

Locations changed:

- `apps/api/app/api/routes/settings.py`

Issue:

The model provider configuration accepted custom base URLs without sufficiently constraining the scheme, credentials, or host relationship to the selected provider.

Impact:

An attacker with settings access could potentially direct model verification or provider traffic to internal services, metadata endpoints, or attacker-controlled hosts.

Fix implemented:

- `model_base_url` must be an absolute HTTPS URL.
- Credentials in the URL are rejected.
- The configured host must match the selected provider default hostname.
- Verification re-validates the effective stored base URL before calling the provider.

Why the fix works:

Provider traffic can no longer be redirected to arbitrary hosts. The API can still use provider-specific base URLs, but only for the selected provider hostname and only over HTTPS.

Core validation:

```python
if parsed.scheme != "https" or not parsed.netloc:
    raise ValueError(...)
if parsed.username or parsed.password:
    raise ValueError(...)
if parsed.hostname != default.hostname:
    raise ValueError(...)
```

### 7. Insecure Docker Defaults And Root Containers

Severity: Medium
Category: Security Misconfiguration / Insecure Defaults

Locations changed:

- `docker-compose.yml`
- `apps/api/Dockerfile`
- `apps/web/Dockerfile`
- `.env.example`

Issue:

The Docker development stack used default Postgres credentials, unauthenticated Redis URLs, exposed database/cache ports, and root users in application containers.

Impact:

In a shared or production-like environment, default credentials and exposed database/cache ports increase the risk of unauthorized access. Running application containers as root increases impact if a process is compromised.

Fix implemented:

- `docker-compose.yml` now requires:
  - `POSTGRES_PASSWORD`
  - `REDIS_PASSWORD`
  - `GITHUB_WEBHOOK_SECRET`
  - `SESSION_SECRET_KEY`
- Redis is started with `--requirepass`.
- API and worker Redis URLs include the password.
- Postgres and Redis no longer expose host ports.
- API and web Dockerfiles create and run as non-root `appuser`.
- `.env.example` now documents empty required secrets rather than insecure default values.

Why the fix works:

The stack no longer silently starts with known database/cache credentials or unauthenticated Redis. Application processes also run with reduced container privileges by default.

### 8. Missing Security Headers And Request Body Limit

Severity: Medium
Category: Security Misconfiguration / Resource Exhaustion

Locations changed:

- `apps/api/app/main.py`

Issue:

The FastAPI application did not set several standard browser-facing security headers and did not enforce a global request body size limit.

Impact:

Missing headers can increase exposure to browser-based abuse such as MIME sniffing or clickjacking. Missing body limits can allow oversized request bodies to consume memory and processing time.

Fix implemented:

- Added a 1MB request body limit.
- Enforces the limit using both `Content-Length` and streamed body counting.
- Malformed `Content-Length` returns `400`.
- Oversized requests return `413`.
- Added security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

Why the fix works:

Requests are bounded before application handlers consume them, and responses now carry baseline browser hardening headers.

## Test And Verification Updates

Tests were updated to reflect the new security posture:

- Authenticated tests now explicitly enable local development header auth.
- A new test asserts protected routes return `401` without authentication.
- Tool registry tests use `/tmp/repopilot-agent-workspaces/{run_id}` for allowed reads.
- Sandbox tests pass server-style `run_id` values and use the isolated workspace root.

Updated test files:

- `apps/api/tests/test_api_routes.py`
- `apps/api/tests/test_tool_registry.py`
- `apps/api/tests/test_phase5_to_8_services.py`

## Residual Notes And Follow-Up Recommendations

The requested remediation scope is complete. Recommended follow-up hardening work:

1. Add role-based authorization checks for owner-only control-plane routes beyond simple authentication.
2. Add rate limiting for auth, settings, tool execution, and webhook endpoints.
3. Consider making CORS stricter outside local development by removing localhost regex in non-local environments.
4. Add negative tests for SSRF cases such as `http://`, embedded credentials, and mismatched provider hostnames.
5. Add integration tests for tool-call attempts that try to smuggle conflicting `run_id`, `actor`, and `state`.
6. Consider requiring non-placeholder secret values at application startup when `REPOPILOT_ENV` is not `local`.

## Final Completion Checklist

- [x] 1. Fail-closed authentication implemented.
- [x] 2. All control-plane routers protected by `get_current_user`.
- [x] 3. Repository and workspace file access bound to server-managed roots.
- [x] 4. Sandbox execution constrained to `/tmp/repopilot-agent-workspaces/{run_id}`.
- [x] 5. ToolExecutor request authority derived server-side and revalidated.
- [x] 6. Model provider SSRF prevention implemented.
- [x] 7. Docker and env defaults hardened.
- [x] 8. Security headers and 1MB request body limit added.

