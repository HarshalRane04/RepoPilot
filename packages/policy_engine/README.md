# Policy Engine Package

Status: reusable policy package. Runtime API code imports `PolicyConfig` and `PolicyEngine` from `repopilot_policy_engine`; `apps/api/app/services/policy.py` remains a compatibility re-export for existing audited call sites.

Phase 7 policy enforcement is currently implemented in `packages/policy_engine/repopilot_policy_engine`.

Current scope:

- Allowlist validation commands.
- Deny unsafe command fragments and unknown commands.
- Escalate high-risk file paths such as workflows, auth, payments, migrations, Docker files, and env files.
- Require `owner` or `maintainer` role approval for escalated plans.

This package is the stable boundary for versioned policy rules and decision helpers. The remaining API-specific work is to keep route/service authorization and audit persistence in the FastAPI app while pure policy decisions stay here.
