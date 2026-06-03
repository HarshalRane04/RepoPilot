# GitHub Client Package

Status: reusable GitHub helper package. GitHub permission role mapping and `/repopilot` command authorization helpers now live in `packages/github_client/repopilot_github_client`; `apps/api/app/services/github_permissions.py` keeps the API-specific database/client wrapper. Runtime GitHub App, OAuth, and guarded PR-write clients still live in `apps/api/app/services/github_app.py` and `apps/api/app/services/github_oauth.py` because they depend on API settings, encrypted runtime secrets, and audit-controlled services.

The current implementation creates local branch and draft PR records while `GITHUB_WRITES_ENABLED=false`. When write mode is enabled and credentials are present, the API now has guarded client methods for real branch, commit, draft PR, issue-comment, permission, and check-run operations.

Production scaffolding exists in the API service for:

- GitHub App installation tokens.
- GitHub App JWT signing.
- Guarding real GitHub writes behind credentials and `GITHUB_WRITES_ENABLED`.
- Repository refs and contents APIs.
- Draft pull request creation.
- Check runs and workflow logs.
- Issue comments and labels.
- Collaborator/permission checks for `/repopilot` comment commands.

Those wrappers should call the existing approval, policy, validation, security, and audit services rather than bypassing the control plane.
