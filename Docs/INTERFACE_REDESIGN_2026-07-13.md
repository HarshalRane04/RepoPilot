# RepoPilot Interface Redesign

Date: 2026-07-13
Direction: Obsidian Relay, adapted to the RepoPilot AI brand
Status: Implemented and verified

## Executive summary

RepoPilot now presents itself as an evidence-first engineering control plane instead of a collection of disconnected dashboards. The redesign makes the active work item, its lifecycle stage, its trust evidence, and its next safe action the dominant interface hierarchy.

The visual language is intentionally technical and restrained: deep graphite surfaces, crisp typography, thin structural borders, electric blue actions, mint verification, amber attention, and red only for true blockers. Dense card walls were replaced with ledgers, lifecycle rails, and progressive disclosure.

## Product concept

The interface follows one operational narrative:

> Task -> Plan -> Run -> Review

Every primary screen answers four questions in order:

1. What work is active?
2. What stage is it in?
3. What evidence supports the current state?
4. What is the next safe action?

The Overview is therefore an active-run instrument, not a generic analytics landing page. It surfaces the current work item, lifecycle state, latest meaningful event, validation/security/policy proof, and the next human decision before secondary queues and activity.

## Palette

| Role | Value | Usage |
| --- | --- | --- |
| Deep ink | `#080b10` | Application background |
| Raised ink | `#0b1017` | Secondary background |
| Panel graphite | `#0f151e` | Primary panels and ledgers |
| Recessed graphite | `#0c121a` | Inputs, disclosures, nested surfaces |
| Structural border | `#1c2632` | Dividers and panel boundaries |
| Primary text | `#f3f6fa` | Titles and critical values |
| Secondary text | `#a8b3c2` | Supporting copy |
| Muted text | `#758294` | Metadata and labels |
| Electric blue | `#5b7cff` | Primary actions and active navigation |
| Violet | `#8a79ff` | Secondary accent and identity |
| Signal blue | `#64b5f6` | Informational states |
| Verified mint | `#44d19d` | Passed trust gates and healthy systems |
| Attention amber | `#f2b35d` | Waiting and approval-required states |
| Critical red | `#ff6b6b` | Failed, rejected, or blocked states |

## Information architecture

Navigation is grouped by operator intent:

- Work: Overview, New task, Tasks, Runs
- Evidence: Reviews, Security
- System: Repositories, Evaluations, Audit trail, Settings

The persistent top bar carries workspace context, the active run, global search, refresh, and profile access. This keeps route navigation separate from work context.

## Implemented structural changes

### Overview

- Replaced the metric-card wall with an active-run hero.
- Added a Task -> Plan -> Run -> Review lifecycle rail.
- Brought validation, security, and policy proof next to the next safe action.
- Added focused Needs attention and Activity stream ledgers.
- Kept operational readiness visible without competing with the work item.

### Tasks

- Consolidated seven narrow workflow columns into five meaningful stages: Needs info, Ready, Approval, Execution & review, and Blocked.
- Removed ambiguous global Generate plan and Run triage actions that silently acted on an implicit first record.
- Kept New task as the single clear primary action.
- Preserved Board and Queue modes while making the mobile board a vertical flow instead of a horizontal pan.

### Runs

- Renamed Runtime to Recorded runtime.
- Stopped inflating duration while a run is waiting for external CI evidence; duration now ends at the latest recorded trace step for waiting or terminal runs.
- Reduced repetitive timeline actions to compact icon controls.

### Reviews

- Reframed Pull Requests as Reviews to match the human evidence workflow.
- Replaced the nine-column table with a compact review ledger.
- Grouped CI, security, status, and risk into readable trust-gate badges.
- Preserved direct access to the complete review record.

### Settings

- Kept the currently selected provider, model, key, base URL, and Save action immediately visible.
- Moved provider switching and the full model catalog into explicit disclosures.
- Reduced initial settings density without removing capability.

### Detail screens

- Removed title truncation at normal desktop widths.
- Reset workspace scroll when the route or selected record changes.
- Converted dense three-panel sections into a two-column rhythm with full-width odd rows.
- Allowed long pills, security notes, and plan content to wrap without collision.

## Responsive behavior

- Desktop keeps the grouped 248 px sidebar and contextual top bar.
- Tablet converts navigation to a horizontal, independently scrollable strip and stacks the primary workspace grid.
- Mobile keeps document width fixed to the viewport, stacks lifecycle evidence, turns task columns into a vertical board, and converts review rows into compact multi-line records.
- The task board, review ledger, review detail, plan detail, and Overview were checked at 1440 x 1024, 1024 x 768, and 390 x 844.

## Accessibility and interaction principles

- Semantic regions, headings, list roles, labels, and a skip link remain intact.
- Every interactive control retains a visible focus treatment.
- Status never depends on color alone; labels and icons carry the same meaning.
- Reduced-motion preferences collapse animation and transition duration.
- Primary actions are verb-led and record-specific.
- Destructive actions remain visually distinct from primary progress actions.

## Removed or de-emphasized redundancy

- Ten competing Overview metrics.
- Seven-column workflow board at ordinary desktop sizes.
- Global actions with implicit record targeting.
- Nine-column review table with hidden horizontal content.
- Always-expanded provider catalog and model browser.
- Continuously increasing wait-state runtime.
- Repeated text labels on every timeline detail icon.

## Recommended next enhancements

These are deliberately outside this redesign's implementation boundary:

1. Add a true command palette behind the existing search shortcut, with navigation and record actions.
2. Persist Board/Queue preference per operator.
3. Add saved task and review filters once server-side filtering is available.
4. Add notification semantics only when there is a real unread/read state; avoid a decorative bell.
5. Extract the final visual tokens into a small typed theme module if a second product surface begins consuming them.
6. Run formal contrast and screen-reader audits in the release pipeline in addition to the current semantic and responsive checks.

## Verification evidence

- Web TypeScript check: passed.
- Isolated production Docker build: passed.
- Production image HTTP smoke test: `200`, 344736-byte response.
- UI truth guard: passed.
- UI truth guard test: 3 passed in the API test image.
- Git whitespace validation: passed.
- Browser console: no application errors; only expected Fast Refresh warnings recorded while source files were being edited.
- Core interactions verified: global task search, New task form readiness, Overview to run, Overview to review evidence, and settings disclosure controls.
- Source and implementation were compared together at the same 1440 x 1024 viewport; no actionable P0, P1, or P2 visual differences remain.

## Primary implementation files

- `apps/web/app/operator-console.tsx`
- `apps/web/app/globals.css`
- `design-qa.md`
