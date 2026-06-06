# RepoPilot Release Workflow Dry Run

- Workflow: `Release Images`
- Run: `27059971285`
- URL: `https://github.com/HarshalRane04/RepoPilot/actions/runs/27059971285`
- Artifact: `release-evidence-27059971285`
- Evidence job: `release-evidence` -> `success`
- Image job: `build-images` -> `success`

## Evidence Artifact

| Path | Bytes | SHA-256 |
|---|---:|---|
| `eval-reports/v1-local-latest.json` | 12063 | `856c15a64e979ead0bbfd2acb0b94f1df06481475a574d7f3217cd67ff8573a5` |
| `eval-reports/v1-local-latest.md` | 1425 | `103bdb7ba720963f07338fec0a9df7a660a5ae899c2e395f915fc79e4c8b484b` |
| `release-artifacts/deployment-validation.json` | 285 | `158a3bd18879e525d19d25a362dd5c41d659b65ca1c701c3353fa955aedcf1cf` |
| `release-artifacts/deployment-validation.md` | 255 | `e67a77b522a7b3add6d8a66547141c165c55426a5efaf6d2ca3beaca58c8d8bd` |
| `release-artifacts/source-boundary-manifest.json` | 69525 | `feeb7307c2849598cb2741bfcba4b946c230953bbb1f76042a8a491a85e2ca3e` |
| `release-artifacts/source-boundary-manifest.md` | 11270 | `719e7100e3bb18a317ffd80dfdbcc1ce0723124ae8b6bd5c4fc44b9fae438ce3` |

## Key Results

- Source-boundary manifest was generated from clean GitHub checkout `c99a0966e821ec279f4e49ffdef711528a5c2e31`.
- Source-boundary status count: `0`.
- Source-boundary file count: `346`.
- Source-boundary manifest SHA-256: `a320706fc917d32f2bf898651b369d5115d27e9eb64dc95f5077d22426f2d2fc`.
- Deployment validation failed findings: `0`.
- Deployment validation warnings: `0`.
- Local benchmark task count: `31`.
- Local benchmark task pass rate: `1.0`.
- Fixture repository pass rate: `1.0`.
- Fixture file coverage rate: `1.0`.

## Remaining Eval Gates

The dry run intentionally preserves honest release gating. The fixture gates passed, while live/provider evidence gates remain incomplete:

- `plan_quality_observations_required`: `false`
- `plan_quality_pass_rate_required`: `false`
- `context_precision_required`: `false`
- `patch_quality_observations_required`: `false`
- `patch_quality_pass_rate_required`: `false`
- `human_edit_distance_required`: `false`
- `provider_comparisons_required`: `false`
