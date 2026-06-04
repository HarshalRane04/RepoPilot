# RepoPilot Release Hygiene Report

- Root: `/Users/harshalrane/Documents/RepoPilot`
- Failed findings: `0`
- Warnings: `6`

| Check | Status | Path | Detail |
|---|---|---|---|
| env_file | warning | .env | Ignored local environment file is present; keep it out of commits and remove it before final source-boundary packaging. |
| generated_artifact | warning | apps/web/node_modules | Allowed Docker mount point; stop the web service before final source-boundary packaging if physical absence is required. |
| generated_artifact | warning | apps/web/.next | Allowed Docker mount point; stop the web service before final source-boundary packaging if physical absence is required. |
| secret_content | warning | apps/api/tests/test_phase5_to_8_services.py | Secret-like content matched pattern private_key_block; value intentionally omitted. |
| secret_content | warning | apps/api/tests/test_api_routes.py | Secret-like content matched pattern private_key_block; value intentionally omitted. |
| git_boundary | warning |  | Working tree has uncommitted or untracked changes; release source boundary is not frozen. |
