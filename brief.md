# RepoPilot AI — Design Brief

## Register
**Product** — operator console + public landing/connect pages. This is a dashboard instrument, not a brand experience.

## Product
RepoPilot AI turns GitHub issues into human-approved, tested, security-scanned draft pull requests. It is an agentic GitHub development console.

## Primary User
A platform engineer or team lead monitoring autonomous agent workflows. They arrive to check:
- What issues are being worked on
- Which plans need approval
- Whether CI and security checks passed
- What the agents are costing

## Job
**Monitor + Operate.** The dominant pattern is a split-feed dashboard (metrics, activity, risk) with drill-down into repositories, issues, agent runs, pull requests, security, evaluations, audit logs, and settings. Secondary: a **Decide** landing page that pitches the product and converts visitors into GitHub-connected users.

## Artifact
GitHub issues, plans, agent runs, pull requests, and all their metadata — rendered as tables, kanban columns, detail views, and trace timelines.

## Evidence
- Stat grid shows connected repos, agent-ready issues, plans awaiting approval, draft PRs, CI pass rate, security blocks, and cost-per-task
- Issue board shows every issue flowing from triage through plan approval to PR creation
- Agent trace shows every step, latency, token cost, and validation result
- Security screen lists findings with severity, remediation suggestions, and policy triggers

## Voice
**Technical, direct, calm.** "Issue #342 — Add rate limiting middleware" not "Your workflow is ready!" Operators want precision, not enthusiasm. Sentence case. No exclamation points. Labels name the action: "Generate plan", "Approve plan", "Index repository".

## Anti-References (what this is NOT)
- Not a marketing SaaS landing page with hero animations and social proof
- Not a consumer app with warm gradients, illustration, and emotional copy
- Not a developer-tool-in-light-mode with code-as-decoration
- Not a generic admin panel with unstyled default components

## Design Principles
- **Dark utility.** The background recedes; data surfaces. Color only where it carries meaning.
- **Consistent ambiguity handling.** "Unavailable" means the data source is missing. "N/A" means the feature doesn't exist. Nothing is blank without explanation.
- **Control at hand, not hidden.** Every screen has visible filters, action buttons, and context panels. Drill-down preserves context.
- **Accessibility is architecture.** Keyboard paths, screen-reader labels, focus management, and reduced motion are required, not aspirational.

## Visual Foundation
- **Palette:** Dark-mode surfaces (#0B0F14 bg, #11161D elevated, #151C24 cards), semantic accents (blue=action, green=success, amber=warning, red=danger, violet=secondary, cyan=info)
- **Typography:** Inter system stack, 14px base on dark background with -0.01em tracking compensation. Mono (Fira Code/Cascadia Code) for logs and code paths only. Tabular numerals on all numeric data.
- **Radius tokens:** `--radius-sm` (6px) → `--radius-md` (8px) → `--radius-lg` (10px) → `--radius-xl` (12px)
- **Motion:** Exponential-out easing, 150ms baseline press feedback, staggered stat card entrance, `prefers-reduced-motion` honored
- **Layout:** Shell with 260px sticky sidebar + scrollable content area. Screen max-width 1540px (1680px ultrawide). 8 responsive breakpoints from 800px–1920px.

## Component Rules
- No placeholder buttons — every visible action maps to a real or scaffolded endpoint
- Disabled buttons carry explanation when context matters
- Empty states explain what belongs there and what action fills it
- Loading states name the actual work (not "Loading...")
- All interactive rows support keyboard Enter/Space
- Tables have `scope="col"`, keyboard-selectable rows, and tabular-nums
- One verb per button label

## Accessibility Bar
- WCAG 2.1 AA minimum: contrast, focus visibility, keyboard operability, screen-reader labels
- Skip link from shell
- `aria-live` region for status changes
- `prefers-reduced-motion` honored
