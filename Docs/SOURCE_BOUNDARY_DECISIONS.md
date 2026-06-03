# RepoPilot Source-Boundary Decisions

This file records release-boundary decisions for files that should not be silently removed or included without context.

## README 2.md

- Status: resolved for the GitHub baseline push.
- Decision: remove before the first intentional baseline commit.
- Reason: `README 2.md` is an older README variant. It describes "Phases 1-13" as implemented, points the dashboard to `http://localhost:3000`, and omits later safety/evidence work now documented in `README.md`, `Docs/IMPROVEMENT_PLAN.md`, and the release evidence reports.
- Current handling: file removed from the source boundary before the baseline GitHub commit.
- Hygiene behavior: `make release-hygiene` should no longer warn about the duplicate README.

## Baseline Commit

- Status: approved for the GitHub baseline push.
- Current recommendation: create the first intentional source-boundary commit after regenerating release hygiene, source-boundary manifest, scanner snapshot, and deployment validation evidence.
- Reason: the workspace currently has no baseline commit, so Git cannot yet prove a frozen release source boundary.
