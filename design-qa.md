# Design QA

## Source truth

- Source image: `/Users/harshalrane/.codex/generated_images/019f4d88-d2a3-7fe3-9f2b-4072da0ca8d2/exec-1fa7b995-ea79-43c7-a751-c5e2728ecd48.png`
- Selected direction: Option 1, Obsidian Relay, adapted to preserve the RepoPilot AI brand and existing product capabilities.

## Implementation evidence

- Implementation screenshot: `/tmp/repopilot-redesign-qa/01-overview.png`
- Viewport: `1440 x 1024`
- State: authenticated Overview with active run `#aed3e333`, issue `#2`, waiting for CI.
- Full-view comparison: `/tmp/repopilot-redesign-qa/compare-overview-pass2.png`
- Focused comparison: `/tmp/repopilot-redesign-qa/compare-overview-hero-pass2.png`

## Comparison history

1. P1: The original dashboard used a metric wall and weak lifecycle hierarchy. Replaced it with the active-run hero, four-stage lifecycle, proof strip, next safe action, attention queue, and activity ledger.
2. P1: The seven-column task board required horizontal panning and contained ambiguous global actions. Consolidated it to five operational stages, removed implicit-record actions, and made the mobile board vertical.
3. P1: The nine-column PR table hid trust evidence at ordinary widths. Replaced it with a responsive review ledger that groups status, CI, security, and risk.
4. P1: Plan detail cards overlapped under long content. Changed the panel rhythm to two columns with full-width odd rows and wrapping pills; geometry checks report no intersections.
5. P2: Model settings exposed provider switching and hundreds of catalog entries at once. Added progressive disclosure while keeping current configuration and Save visible.
6. P2: The tablet cascade initially restored the desktop block navigation, and the mobile review grid compressed its queue column. Reasserted horizontal tablet navigation and one-column detail/review grids at the final responsive layer.

## Responsive evidence

- Tablet Overview: `/tmp/repopilot-redesign-qa/09-overview-tablet.png`, `1024 x 768`, document scroll width equals client width.
- Mobile Overview: `/tmp/repopilot-redesign-qa/10-overview-mobile.png`, `390 x 844`, document scroll width equals client width.
- Mobile Tasks: `/tmp/repopilot-redesign-qa/11-tasks-mobile.png`, five workflow columns stacked to one 311 px column.
- Mobile Reviews: `/tmp/repopilot-redesign-qa/12-reviews-mobile.png`, review ledger width 311 px with no document overflow.
- Mobile Review detail: `/tmp/repopilot-redesign-qa/13-review-detail-mobile.png`, detail grid stacked to one 311 px column.
- Plan layout: `/tmp/repopilot-redesign-qa/14-plan-bottom.png`, responsive panel geometry checked with zero overlaps.

## Functional evidence

- `Review evidence` opens `#pull-request-detail` for PR #3.
- `Open full run` opens the selected Agent Run and displays `Recorded runtime` as `0m 1s`.
- Global search for `Provider smoke` returns only the matching task.
- New task remains disabled when empty and enables after valid title/details input without submitting test data.
- Settings provider disclosure toggles open and closed while the model catalog remains collapsed.
- Semantic browser snapshot includes the skip link, named primary navigation, labeled search, headings, lists, and form labels.

## Verification

- `pnpm -C apps/web typecheck`: passed.
- `make web-build`: passed.
- Production container smoke at `http://127.0.0.1:3002/`: HTTP 200, then container removed.
- `python3 scripts/ui_truth_guard.py`: passed.
- `docker run --rm -v "$PWD:/repo:ro" -w /repo/apps/api repopilot-api pytest tests/test_ui_truth_guard.py -q`: 3 passed.
- `git diff --check`: passed.
- Browser diagnostics: no application errors; edit-time Fast Refresh warnings only.

## Residual differences

- P3 intentional: the product brand remains RepoPilot AI rather than adopting the concept-image name.
- P3 intentional: the implementation preserves the full global search field and additional System navigation required by the existing product.
- P3 intentional: the setup progress card remains visible because it exposes a real incomplete operational state.

No actionable P0, P1, or P2 findings remain.

final result: passed
