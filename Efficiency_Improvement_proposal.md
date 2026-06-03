# RepoPilot AI — Efficiency & Lightweight Improvement Proposal

> Formal improvement document. **No source code is modified by this document.** Every item below is a proposed change with exact file/line references, an implementation stub, and short reasoning. Items are grouped by area, tagged with impact (`L` / `M` / `S`) and risk (`L` / `M` / `H`).

---

## 0. Scope and method

Read-only review of `apps/api`, `apps/web`, `services/*`, `packages/*`, Dockerfiles, `docker-compose.yml`, `.github/workflows/*`, `Makefile`, and root configs. Four parallel explore agents (api, web, services+packages, infra/CI), then three review passes: (1) verify highest-impact findings against source, (2) deduplicate and cross-validate, (3) prioritize and stage. Every "high-impact" item below was confirmed by re-reading the cited file/line.

## 1. Headline numbers (today)

| Surface | Measurement |
|---|---|
| `apps/web/app/operator-console.tsx` | **4 000 LOC**, 172 KB, single `"use client"` file shipping every screen on first paint |
| `apps/web/app/globals.css` | **3 171 LOC**, 60 KB, loaded on every route (landing too) |
| `apps/web/lib/api.ts` | Calls **18 endpoints with `cache: "no-store" + revalidate: 0`**, then re-polls them every **20 s** on the client |
| Backend N+1 hot paths | At least 6 confirmed: `installations.py`, `issues.py`, `repos.py`, `runs.py`, `activity.py`, `ci_analyzer.py` |
| `await engine.dispose()` in worker `finally` | `apps/api/app/worker/tasks.py:37, 51` — connection pool torn down after **every Celery task** |
| `effective_settings()` re-decrypts the secret store | `apps/api/app/services/runtime_secrets.py:212-223`, called from ~25 call sites |
| `httpx.AsyncClient(...)` blocks | **9 separate per-call clients** in `model_gateway.py:207,296`, `github_app.py:56,112,368`, `github_oauth.py:51,73,97`, `model_provider_verification.py:48` |
| API Dockerfile | No BuildKit cache, copies `apps/api/tests/` + `celerybeat-schedule` (16 KB binary, also committed to git) into the image; `pytest` in prod `requirements.txt:19`; `uvicorn[standard]` in prod |
| Web Dockerfile | No multi-stage, single `CMD ["npm", "run", "dev", "--", "--webpack"]` — no real prod image |
| CI | No pip cache (`api-tests`), no Docker layer cache (`sandbox-image`/`release.yml`), no `concurrency:` group, no `timeout-minutes` |

## 2. Top 15 highest-impact, lowest-risk changes

Ordered roughly by ROI. Each is described in detail later in the report.

| # | Area | Change | Impact | Risk |
|---|------|--------|--------|------|
| 1 | web | Split `apps/web/app/operator-console.tsx` (4 000 LOC `"use client"`) into App Router route segments; keep forms/modals as small client islands | L | M |
| 2 | api | Remove `await engine.dispose()` from `worker/tasks.py:37, 51` — pool is module-level, disposing it on every Celery task thrashes Postgres | L | L |
| 3 | api | Cache `effective_settings()` with `lru_cache(maxsize=1)`, invalidate on store-file mtime | L | L |
| 4 | api | Push `retrieve_context` vector search into SQL with pgvector (`ORDER BY embedding <=> :q LIMIT :k`) + add `hnsw`/`ivfflat` index | L | M |
| 5 | web | Stop using `cache: "no-store"` on the 18 dashboard endpoints in `apps/web/lib/api.ts:419-438`; tier `revalidate` | L | L |
| 6 | web | Replace 20-s `setInterval` polling (`operator-console.tsx:293-298`) with SWR/React Query, dedup'd, visibility-aware | L | M |
| 7 | api | Add a single module-level `httpx.AsyncClient` with `Limits(max_connections=50, max_keepalive_connections=20)` — replaces 9 per-call clients | L | M |
| 8 | infra | Multi-stage `apps/web/Dockerfile` (deps / builder / runtime) using `output: "standalone"` in `next.config.mjs` | L | L |
| 9 | infra | Add BuildKit `--mount=type=cache,target=/root/.cache/pip` to `apps/api/Dockerfile`; extend `.dockerignore` | L | L |
| 10 | api | Fix 6 N+1 hot paths with `selectinload` / single grouped SQL | L | M |
| 11 | api | Make `RepositoryIndexer.index_repository` incremental (per-file `sha256`, short-circuit on matching `commit_sha`) | L | M |
| 12 | CI | Add `cache: 'pip'` + `cache-dependency-path` to `setup-python` in `ci.yml:59`; switch `sandbox-image` to `docker/build-push-action@v6` with `cache-from: type=gha`; add `concurrency:` group | M-L | L |
| 13 | api | Replace `subprocess.run` in `sandbox.py:118` with `asyncio.create_subprocess_exec` | L | M |
| 14 | infra | Move `pytest` to a new `apps/api/requirements-dev.txt`; switch `uvicorn[standard]` to `uvicorn[performance]` in prod | M | L |
| 15 | web | Split `apps/web/app/globals.css` (3 171 LOC) per route; add `content-visibility: auto`; add `experimental.optimizePackageImports: ["lucide-react"]` | M | L |

> If only three are done, do **#1, #2, #5**.

---

## 3. Findings — `apps/web` (Next.js dashboard)

### A1. Monolithic 4 000-line `"use client"` component — `apps/web/app/operator-console.tsx:1-4000`  [Impact: L · Risk: M]
- **Problem.** A single `"use client"` directive at line 1 pulls every screen, helper, type and icon into one client bundle. The marketing landing page at `/` ships the whole tree.
- **Reasoning.** First-paint JS is the largest web cost; route-level code-splitting is the standard fix.
- **Stub (illustrative; do not apply yet):**
  ```tsx
  // app/page.tsx  (new file, server component by default)
  import { LandingPage } from "./_screens/landing";
  export default function Page() { return <LandingPage />; }

  // app/(console)/dashboard/page.tsx
  import { DashboardScreen } from "../../_screens/dashboard";
  export default function Page() { return <DashboardScreen />; }

  // app/_screens/settings/index.tsx  (small "use client" island)
  "use client";
  export function SettingsScreen() { /* existing JSX, trimmed */ }
  ```

### A2. No fetch caching — `apps/web/lib/api.ts:419-438`  [L · L]
- **Problem.** All 18 endpoints use `cache: "no-store", next: { revalidate: 0 }`.
- **Reasoning.** Repos / installations / catalog / policy / integrations / evals are mostly static; re-rendering 18 times per page load is wasted work.
- **Stub:**
  ```ts
  // lib/api.ts
  async function safeFetch<T>(path: string, opts: { revalidate?: number; tags?: string[] } = {}): Promise<T | null> {
    const { revalidate = 60, tags = [] } = opts;
    // ...
    const response = await fetch(`${baseUrl}${path}`, {
      next: { revalidate, tags },
    });
    // ...
  }
  // Then per-endpoint:
  safeFetch<MetricsResponse>("/metrics/overview",    { revalidate: 60  });
  safeFetch<RepositoryResponse[]>("/repos",         { revalidate: 300, tags: ["catalog"] });
  safeFetch<ModelCatalogResponse>("/settings/models/catalog", { revalidate: 3600 });
  safeFetch<ActivityItem[]>("/activity?limit=160", { revalidate: 0   }); // live
  ```

### A3. 20 s polling of all 18 endpoints — `apps/web/app/operator-console.tsx:293-298, 306-360`  [L · M]
- **Problem.** `setInterval(..., 20_000)` triggers `refresh()` which `Promise.all`s 17 fetches.
- **Reasoning.** 51 req/min/user; per-endpoint `refreshInterval` and deduping is the right tool.
- **Stub:**
  ```ts
  import useSWR from "swr";
  const { data: runs } = useSWR("/runs?limit=80", fetcher, { refreshInterval: 5000, dedupingInterval: 2000 });
  const { data: metrics } = useSWR("/metrics/overview", fetcher, { refreshInterval: 60_000 });
  // Pause on tab hidden:
  useEffect(() => {
    const onVis = () => setPaused(document.visibilityState !== "visible");
    document.addEventListener("visibilitychange", onVis); return () => document.removeEventListener("visibilitychange", onVis);
  }, []);
  ```

### A4. Oversized default API limits — `apps/web/lib/api.ts:371-376`  [L · L]
- **Problem.** `?limit=300/200/300/160/80` unconditional. JSON is 1-2 MB for a fresh dashboard.
- **Reasoning.** Default small; let table views ask for more.
- **Stub:**
  ```ts
  safeFetch<IssueResponse[]>("/issues?limit=20"),
  // Tables/board pass:   /issues?limit=300
  ```

### A5. 3 171-line `globals.css` loaded on every route — `apps/web/app/globals.css:1-3171` (imported at `app/layout.tsx:2`)  [L · L]
- **Problem.** 492 class selectors, including page-specific ones, on every route.
- **Reasoning.** Route-level CSS scoping drops landing CSS from 60 KB to ~5 KB.
- **Stub:**
  ```css
  /* app/_styles/tokens.css  */ :root { --bg:#0B0F14; --radius-md:8px; ... }
/* app/_styles/base.css    */ /* reset + body */
  /* app/(console)/dashboard/page.tsx */
  import "./_styles/dashboard.css";
  ```

### A6. Every state change re-renders every screen — `apps/web/app/operator-console.tsx:226-256, 731-938`  [M · M]
- **Problem.** 22 `useState` calls + a giant JSX that returns every screen component inline.
- **Reasoning.** After A1, each screen is its own file and gets its own props.
- **Stub:**
  ```tsx
  const DashboardScreen = memo(function DashboardScreen({ data }: { data: DashboardData }) { /* ... */ });
  ```

### A7. Re-derived lookups — `apps/web/app/operator-console.tsx:258-262`  [M · L]
- **Problem.** 4× `Array.find` on arrays of up to 300 items per render.
- **Reasoning.** O(n) per render × per state change × per filter keystroke.
- **Stub:**
  ```ts
  const repoMap = useMemo(() => new Map(data.repositories.map(r => [r.id, r])), [data.repositories]);
  const selectedRepo = repoMap.get(selectedRepoId) ?? data.repositories[0] ?? null;
  ```

### A8. Inline row keyboards duplicate `rowKeyboard` helper — `apps/web/app/operator-console.tsx:1271, 1513, 1882, 2092, 2320` vs unused `app/lib/keyboard.ts:7-20`  [M · L]
- **Problem.** New function identity per render defeats future `React.memo`.
- **Reasoning.** The helper exists; use it.
- **Stub:**
  ```ts
  <tr onKeyDown={rowKeyboard(() => onRepo(repo))} ... />
  ```

### A9. `key={index}` in list primitives — `apps/web/app/components/ui/lists.tsx:8, 17, 26` and `pill-list.tsx:8`  [M · L]
- **Problem.** Causes stale state, broken animations, input focus loss on reorder/grow.
- **Reasoning.** Use stable keys.
- **Stub:**
  ```tsx
  {items.map((item) => <ItemRow key={item.id} item={item} />)}
  ```

### A10. Two copies of every UI component — `apps/web/app/components/ui/*` shadowed by `apps/web/app/operator-console.tsx:3358-3539`  [M · L]
- **Problem.** Bundle ships both, types drift.
- **Reasoning.** Single source of truth.
- **Stub:**
  ```tsx
  // In operator-console.tsx — delete the local Badge/Breadcrumb/EmptyState/Field/StatCard definitions
  import { Badge, Breadcrumb, EmptyState, Field, StatCard } from "../components/ui";
  ```

### A11. Barrel `apps/web/app/components/ui/index.ts` defeats tree-shaking — [M · L]
- **Reasoning.** Either delete the barrel and import directly, or keep it and consume from a single server component.
- **Stub:**
  ```ts
  // app/components/ui/index.ts
  export { Button } from "./button";
  export { Badge } from "./badge";
  // ... explicit re-exports only
  ```

### A12. `Record<string, unknown>` leaks in 13 places — `apps/web/lib/api.ts:53, 81, 131`; `apps/web/app/operator-console.tsx:107, 122, 670, 2192, 3534, 3541, 3566, 3574, 3940, 3967`  [M · L]
- **Reasoning.** Mirror backend Pydantic; eliminate JS-with-types defensive code.
- **Stub:**
  ```ts
  export type EvalMetrics = { pass_rate: number; category_pass_rates: Record<string, number>; ... };
  export type EvalReport = { id: string; benchmark_version: string; metrics: EvalMetrics; report_uri: string | null; created_at: string };
  ```

### A13. Inline styles bypass design tokens — `apps/web/app/operator-console.tsx:1094, 2641, 3463, 3557, 3577`; `apps/web/app/components/ui/policy-toggle.tsx:5`, `threshold.tsx:6`  [M · L]
- **Stub:**
  ```css
  /* app/_styles/utilities.css */
  .text-success-strong { color: var(--green); font-weight: 740; font-size: 13px; }
  .progress-fill       { width: var(--progress); }
  ```

### A14. No dynamic imports for Settings / Evaluations / Profile / Audit Logs — `apps/web/app/operator-console.tsx:2172 (EvaluationsScreen), 2355 (SettingsScreen)`  [L · L]
- **Stub:**
  ```ts
  const SettingsScreen = dynamic(() => import("./_screens/settings").then(m => m.SettingsScreen), { ssr: false });
  ```

### A15. 7 separate filter `useState`s could be a reducer/URL-state — `apps/web/app/operator-console.tsx:245-256`  [M · L]
- **Stub:**
  ```ts
  type IssuesFilters = { status: IssueStatusFilter; risk: RiskFilter; type: TypeFilter };
  const [filters, dispatch] = useReducer(filterReducer, defaultFilters);
  // Or move into URL with nuqs: const [status] = useQueryState("status");
  ```

### A16. `safeFetch` waterfall over 4 base URLs on every endpoint — `apps/web/lib/api.ts:419-451`  [M · L]
- **Reasoning.** First hop is normally correct, but misconfiguration costs 4× timeout per call.
- **Stub:**
  ```ts
  let _resolvedBase: string | null = null;
  async function resolveApiBase(): Promise<string> {
    if (_resolvedBase) return _resolvedBase;
    for (const url of apiBaseUrls()) {
      try {
        const c = new AbortController(); setTimeout(() => c.abort(), 1500);
        const r = await fetch(`${url}/health`, { signal: c.signal });
        if (r.ok) return (_resolvedBase = url);
      } catch {}
    }
    return (_resolvedBase = apiBaseUrls()[0]);
  }
  ```

### A17. `setInterval` keeps running when tab is hidden — `apps/web/app/operator-console.tsx:293-298`  [M · L]
- **Reasoning.** Battery + bandwidth waste; SWR handles this for free (A3).
- **Stub:** covered by the `visibilitychange` listener in A3.

### A18. `next.config.mjs` missing `experimental.optimizePackageImports` and `output: "standalone"` — `apps/web/next.config.mjs:1-15`  [M · L]
- **Stub:**
  ```js
  // next.config.mjs
  export default {
    output: "standalone",
    experimental: { optimizePackageImports: ["lucide-react"] },
    reactStrictMode: true,
  };
  ```

### A19. No `Cache-Control` / `headers()` in `next.config.mjs` — `apps/web/next.config.mjs:1-15`  [M · L]
- **Stub:**
  ```js
  async headers() {
    return [{
      source: "/_next/static/:path*",
      headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
    }];
  }
  ```

### A20. Dead `useBrowserLayoutEffect` shim — `apps/web/app/operator-console.tsx:223`  [S · L]
- **Stub:**
  ```ts
  import { useLayoutEffect } from "react";
  // delete the ternary; use useLayoutEffect directly
  ```

### A21. `JSON.stringify(finding, null, 2)` on every render — `apps/web/app/operator-console.tsx:2148, 3538`  [S · L]
- **Stub:**
  ```ts
  const pretty = useMemo(() => JSON.stringify(finding, null, 2), [finding]);
  ```

### A22. Convoluted button-prop types — `apps/web/app/components/ui/button.tsx:48, 52, 56, 60, 64`  [S · L]
- **Stub:**
  ```ts
  export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "subtle" | "link"; size?: "sm" | "md" };
  export function Button({ variant = "primary", size = "md", ...rest }: ButtonProps) { /* ... */ }
  // Drop the 5 wrapper functions
  ```

### A23. `tsconfig.json` missing strict flags — `apps/web/tsconfig.json`  [S · L]
- **Stub:**
  ```json
  { "compilerOptions": { "noUncheckedIndexedAccess": true, "exactOptionalPropertyTypes": true } }
  ```

### A24. `IssueRiskFilter` reused as `prRiskFilter` — `apps/web/app/operator-console.tsx:251`  [S · L]
- **Stub:**
  ```ts
  export type RiskFilter = "all" | "low" | "medium" | "high";
  ```

### A25. No ESLint / Prettier / web test runner — `apps/web/package.json:5-10`  [S · L]
- **Stub:**
  ```json
  "scripts": { "lint": "next lint", "test": "vitest run" },
  "devDependencies": { "@next/eslint-plugin-next": "16.2.6", "eslint": "9.x", "eslint-plugin-react-hooks": "...", "vitest": "..." }
  ```

### A26. `--webpack` flag in compose is overridden by `turbopack.root` in config — `docker-compose.yml:157` vs `apps/web/next.config.mjs:10-12`  [S · L]
- **Stub:** remove `--webpack` from `command:` in `docker-compose.yml:157`.

### A27. `turbopack.root` block is a no-op — `apps/web/next.config.mjs:10-12`  [S · L]
- **Stub:** delete the block; Turbopack is the default for `next dev`.

### A28. `window.prompt` / `window.confirm` block the main thread — `apps/web/app/operator-console.tsx:477, 528, 551, 606, 629, 649`  [S · L]
- **Stub:** replace each with a small `<Dialog>` form.

---

## 4. Findings — `apps/api` (FastAPI backend)

### B1. `engine.dispose()` in worker `finally` — `apps/api/app/worker/tasks.py:37, 51`  [L · L]
- **Problem.** Pool is module-level (`apps/api/app/db/session.py:7`); disposing it after every event forces the next event to rebuild TCP/TLS/startup to Postgres.
- **Reasoning.** Let FastAPI/Celery manage the engine lifecycle (one disposal at shutdown).
- **Stub:**
  ```python
  # apps/api/app/worker/tasks.py
  async def _process_github_event(event_id: str) -> dict[str, str]:
      async with AsyncSessionLocal() as db:
          return await process_github_event(db, event_id=UUID(event_id))
      # No engine.dispose() — Celery handles engine lifecycle at shutdown.
  ```

### B2. `effective_settings()` re-decrypts the secret store on every call — `apps/api/app/services/runtime_secrets.py:212-223`  [L · L]
- **Problem.** Reads the JSON store + Fernet-decrypts every secret per call; ~25 call sites.
- **Reasoning.** Memoize; invalidate on store-file mtime.
- **Stub:**
  ```python
  # apps/api/app/services/runtime_secrets.py
  import functools, time
  @functools.lru_cache(maxsize=1)
  def _cached_effective(base_id: int, store_mtime: float) -> Settings:
      base = settings  # or accept as arg
      try:
          stored = RuntimeSecretStore(base).load_values()
      except Exception:
          stored = {}
      updates = {attr: stored[env] for env, attr in RUNTIME_SECRET_FIELDS.items() if stored.get(env)}
      return base.model_copy(update=updates)

  def effective_settings(config: Settings | None = None) -> Settings:
      base = config or settings
      path = Path(base.runtime_secrets_store_path).expanduser()
      mtime = path.stat().st_mtime if path.exists() else 0.0
      return _cached_effective(id(base), mtime)
  ```

### B3. `retrieve_context` does vector search in Python — `apps/api/app/services/repo_indexer.py:186-208`  [L · M]
- **Problem.** Loads every chunk; `_cosine_similarity` (1 536 dims per chunk) in a Python loop; never uses the `pgvector` `<=>` operator.
- **Reasoning.** Move to SQL + add an ANN index.
- **Stub:**
  ```python
  # apps/api/app/services/repo_indexer.py
  from sqlalchemy import text
  async def retrieve_context(self, db, *, repository_id, query, limit=6):
      # 1. Embed the query (kept as is)
      query_embedding = self._embed_query(db, query)
      # 2. Single SQL with pgvector operator
      result = await db.execute(
          text("""
              SELECT file_path, symbol_name, chunk_type, chunk_text,
                     1 - (embedding <=> :q_vec) AS vec_score
              FROM code_chunks
              WHERE repository_id = :rid
              ORDER BY embedding <=> :q_vec
              LIMIT :k
          """),
          {"rid": repository_id, "q_vec": query_embedding, "k": limit},
      )
      rows = result.mappings().all()
      # 3. Re-rank with lexical + path bonus (Python, but only on the k=6 candidates)
      ...
  ```
  ```sql
  -- Alembic migration
  CREATE INDEX IF NOT EXISTS code_chunks_repo_emb_idx
  ON code_chunks USING hnsw (embedding vector_cosine_ops);
  ```

### B4. N+1 in `list_installations` — `apps/api/app/api/routes/installations.py:11-29`  [L · M]
- **Stub:**
  ```python
  from sqlalchemy import func, select
  stmt = (
      select(Installation, func.count(Repository.id))
      .outerjoin(Repository, Repository.installation_id == Installation.id)
      .group_by(Installation.id)
      .order_by(Installation.created_at.desc())
  )
  ```

### B5. N+1 in `list_issues` — `apps/api/app/api/routes/issues.py:23-36`  [L · M]
- **Stub:**
  ```python
  issues = (await db.execute(select(Issue).order_by(Issue.created_at.desc()).limit(limit))).scalars().all()
  repos = (await db.execute(select(Repository).where(Repository.id.in_({i.repository_id for i in issues})))).scalars().all()
  latest_plans = await _latest_plans_for_issues(db, [i.id for i in issues])
  latest_runs  = await _latest_runs_for_issues(db, [i.id for i in issues])
  ```
  Use `selectinload(Issue.repository)` (when the relationship exists) or pre-fetched dicts to avoid the per-row `db.get`.

### B6. N+1 in `list_repositories` + full chunk load — `apps/api/app/api/routes/repos.py:17-51`  [L · M]
- **Stub:**
  ```python
  # 1 query for repos, 1 for issue counts grouped, 1 for distinct file_paths grouped, 1 for chunk count.
  repos = (await db.execute(select(Repository).order_by(Repository.created_at.desc()))).scalars().all()
  issue_counts = dict((await db.execute(
      select(Issue.repository_id, func.count(Issue.id)).group_by(Issue.repository_id)
  )).all())
  chunk_stats = dict((await db.execute(
      select(CodeChunk.repository_id,
             func.count(CodeChunk.id),
             func.count(func.distinct(CodeChunk.file_path)))
      .group_by(CodeChunk.repository_id)
  )).all())
  ```

### B7. N+1 in `list_runs` — `apps/api/app/api/routes/runs.py:50-81`  [L · M]
- **Stub:**
  ```python
  # Latest step per run via DISTINCT ON (Postgres) or a window function
  latest_step = await db.execute(text("""
      SELECT DISTINCT ON (run_id) run_id, step_name, status
      FROM agent_steps
      WHERE run_id = ANY(:ids)
      ORDER BY run_id, created_at DESC
  """), {"ids": [r.id for r in runs]})
  # Then GROUP BY for validation statuses
  ```

### B8. 9 sequential activity queries — `apps/api/app/api/routes/activity.py:32-40, 45-186`  [L · M]
- **Stub:**
  ```python
  # Replace 9 awaits with asyncio.gather on separate sessions:
  import asyncio
  from app.db.session import AsyncSessionLocal
  async def _gather(db):
      return await asyncio.gather(
          _audit_activity(db), _step_activity(db), _event_activity(db),
          _issue_activity(db), _run_activity(db), _validation_activity(db),
          _security_activity(db), _pr_activity(db), _eval_activity(db),
      )
  # Or use a single UNION ALL view with a typed discriminator.
  ```

### B9. `subprocess.run` blocks the event loop — `apps/api/app/services/sandbox.py:118-152` (also `apps/api/app/services/tools/registry.py:748-756`)  [L · M]
- **Stub:**
  ```python
  # sandbox.py — replace the body of _execute()
  proc = await asyncio.create_subprocess_exec(
      *args, cwd=cwd, env=env,
      stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
  )
  try:
    stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
  except asyncio.TimeoutError:
    proc.kill(); await proc.wait()
    ...
  return SandboxCommandResult(..., stdout=stdout_b.decode("utf-8", "replace")[-8000:], ...)
  ```

### B10. `index_repository` is full delete + re-embed — `apps/api/app/services/repo_indexer.py:101-137, 346-354`  [L · M]
- **Reasoning.** Per-file `sha256` is already computed at line 351; use it to skip unchanged files; short-circuit when `commit_sha == repository.last_indexed_sha`.
- **Stub:**
  ```python
  # _iter_indexable_files: yield (path, sha256, text) tuples
  for path, sha, text in self._iter_indexable_files(...):
      new_hashes[path.as_posix()] = sha
      if existing_hashes.get(path.as_posix()) == sha:
          continue  # unchanged: do not re-embed
      changed_chunks.append((path, text))
  if not changed_chunks and new_hashes == existing_hashes:
      return RepositoryIndexResult(...unchanged=True)
  ```

### B11. No `httpx.AsyncClient` connection reuse — 9 per-call clients across:
- `apps/api/app/services/model_gateway.py:207` and `:296`
- `apps/api/app/services/github_app.py:56`, `:112`, `:368`
- `apps/api/app/services/github_oauth.py:51`, `:73`, `:97`
- `apps/api/app/services/model_provider_verification.py:48`
  [L · M]
- **Stub:**
  ```python
  # apps/api/app/core/http.py  (new file)
  import httpx, asyncio
  _client: httpx.AsyncClient | None = None
  _lock = asyncio.Lock()
  async def get_http_client() -> httpx.AsyncClient:
      global _client
      async with _lock:
          if _client is None:
              _client = httpx.AsyncClient(
                  timeout=httpx.Timeout(20.0, connect=5.0),
                  limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
              )
          return _client
  # Then in model_gateway.py:
  client = await get_http_client()
  response = await client.post(...)
  ```

### B12. `implementation_plan_from_db` re-validates the same plan JSON many times per request — `apps/api/app/services/planning.py:192-202`  [L · M]
- **Reasoning.** Hit in planning, policy, approval, tool registry, run-implementation, draft PR, revision planner, etc.
- **Stub:**
  ```python
  # Add a Plan-cache hook in services/planning.py
  from functools import lru_cache
  def _plan_cache_key(plan: Plan) -> tuple[str, int]:
      payload = plan.plan_json or {}
      # Hash of the relevant slice; bump on save via ORM event listener
      return (str(plan.id), hash(json.dumps(payload, sort_keys=True, default=str)))

  @lru_cache(maxsize=256)
  def _parsed_plan(plan_id: str, payload_hash: int, json_blob: str) -> ImplementationPlan:
      payload = json.loads(json_blob)
      payload["plan_id"] = plan_id
      for k in ("context","policy_decision","approval_policy_decision","approved_plan_hash","rejection_reason","revision_parent_plan_id","revision_instructions"):
          payload.pop(k, None)
      return ImplementationPlan.model_validate(payload)

  def implementation_plan_from_db(plan: Plan) -> ImplementationPlan:
      payload = plan.plan_json or {}
      blob = json.dumps(payload, sort_keys=True, default=str)
      return _parsed_plan(str(plan.id), hash(blob), blob)
  ```

### B13. `BudgetGuard.enforce` runs 3 separate count/sum queries per LLM call — `apps/api/app/services/security_envelope.py:80-102`  [M · L]
- **Stub:**
  ```python
  async def snapshot(self, db, *, run_id):
      run = await db.get(AgentRun, run_id)
      if run is None: raise ValueError(...)
      # Single aggregate, prefer AgentRun columns when available
      aggregates = (await db.execute(
          select(
              func.count(LLMTrace.id),
              func.coalesce(func.sum(LLMTrace.tokens), 0),
              func.coalesce(func.sum(LLMTrace.cost), 0.0),
          ).where(LLMTrace.agent_run_id == run_id)
      )).one()
      llm_calls, tokens, cost = aggregates
      return BudgetSnapshot(run_id=run_id, llm_call_count=int(llm_calls),
                            total_tokens=max(int(run.total_tokens or 0), int(tokens or 0)),
                            total_cost=max(float(run.total_cost or 0.0), float(cost or 0.0)))
  ```

### B14. `_record_trace` re-loads `AgentRun` after caller has it — `apps/api/app/services/model_gateway.py:385-389`  [M · L]
- **Stub:** pass `run` in from `complete()` / `complete_json()`, or `UPDATE agent_run SET total_tokens = total_tokens + :t, total_cost = total_cost + :c WHERE id = :id`.

### B15. `httpx` on the hot model path — see B11 [L · M]

### B16. `run_trace` does 6 sequential queries — `apps/api/app/services/observability.py:12-30`  [M · L]
- **Stub:** `asyncio.gather` over the 6 `db.execute`s using a single `db` (FastAPI session is concurrency-safe with `asyncmy`/`asyncpg` for simple statements; for stricter drivers use separate `AsyncSessionLocal()` instances).

### B17. `eval_runner.metrics` runs 8 separate `count(*)` queries — `apps/api/app/services/eval_runner.py:96-176`  [S · L]
- **Stub:** single `select(func.count().filter(...), ...)` over a subquery, or cache with a 30 s TTL.

### B18. `stable_json_hash` / `redact_text` / `redact_data` re-walk on every audit/tool/LLM call — `apps/api/app/services/security_envelope.py:21-64`  [M · L]
- **Stub:**
  ```python
  _SECRET_REGEX = re.compile(
      r"(?:" +
      r"|".join(p.pattern for p in SECRET_VALUE_PATTERNS) +
      r")", re.IGNORECASE,
  )
  def redact_text(value: str) -> str:
      return _SECRET_REGEX.sub("[REDACTED_SECRET]", value)
  ```

### B19. `authorization.require_*_access` chain does N+1 DB gets per request — `apps/api/app/services/authorization.py:41-124`  [M · L]
- **Stub:** collapse the chain into a single JOIN (e.g., `Run -> Issue -> Repository`) and only fetch inner entities on failure.

### B20. `RoleLevel` / `ROLE_LEVELS` defined twice — `apps/api/app/services/authorization.py:11-19` and `packages/github_client/repopilot_github_client/permissions.py:22-30`  [M · L]
- **Stub:** delete the local copy in `authorization.py`; import `role_allows`, `ROLE_LEVELS` from the package.

### B21. `approved_plan_hash_matches` re-dumps + re-hashes the full plan JSON each call — `apps/api/app/services/planning.py:205-211`  [M · L]
- **Reasoning.** Hash the immutable plan fields only; store the hash on the Plan row at approval time.

### B22. `body` read through counting middleware AND in the route — `apps/api/app/main.py:42-69` and `apps/api/app/api/routes/webhooks.py:34-44`  [M · L]
- **Stub:** drop the custom `limited_receive`; just check `Content-Length` header up front; `await request.body()` once in the route.

### B23. `GitHubSignatureVerifier` instantiated per webhook — `apps/api/app/api/routes/webhooks.py:35`  [M · L]
- **Stub:** module-level singleton verifier built once on app startup; combined with B2 (cache `effective_settings`), the secret lookup becomes free.

### B24. Dedupe via SELECT-then-INSERT instead of relying on the `unique` index — `apps/api/app/services/github_ingestion.py:39-67`  [M · L]
- **Stub:** try `INSERT` and catch `IntegrityError` from the unique constraint on `delivery_id`; treat it as duplicate.

### B25. `_workspace_diff_payload` re-reads + sha256s every file on every tool call — `apps/api/app/services/tools/registry.py:1621-1656`  [M · M]
- **Stub:** in-process cache `_SNAPSHOT_CACHE: dict[Path, tuple[float, dict]]` invalidated on `write_file`/`apply_patch`; baseline stores `(path, mtime, size)` only and the live content is re-read on demand for the unified diff.

### B26. `_read_context_snippets` makes N sequential `repo.read_file` tool calls — `apps/api/app/services/implementation_agent.py:299-319`  [M · M]
- **Stub:** bypass the tool registry for internal reads; use `await asyncio.gather(*(read_file_async(p) for p in paths))` directly from the workspace.

### B27. `execute_batch` is sequential despite the name — `apps/api/app/services/tools/registry.py:472-489`  [M · M]
- **Stub:** run read-tier tools concurrently with `asyncio.gather`; serialize mutating ones; share the `db.get(AgentRun)`.

### B28. `_assert_plan_allows_write_path` re-loads Plan + Pydantic-validates per write call — `apps/api/app/services/tools/registry.py:1518-1534`  [M · M]
- **Stub:** memoize parsed `ImplementationPlan` on the executor keyed by `(plan_id, approved_plan_hash)` (see B12).

### B29. `git_ingestion` policy check constructs `PolicyEngine()` and re-validates the plan from JSONB for a hot webhook path — `apps/api/app/services/github_ingestion.py:144-153`  [M · M]
- **Stub:** store `policy.decision.value` (and `reason`) on the plan row at plan-create time; read directly in webhook hot path.

### B30. `_content_fingerprint` reads every file in full twice — `apps/api/app/services/repo_indexer.py:346-354` and `:109`  [M · L]
- **Stub:** stream-read each file once in `_iter_indexable_files`, yielding `(path, sha256, text)` tuples.

### B31. `_iter_indexable_files` collects the full list, breaks the `for` but `rglob` still walks the whole tree — `apps/api/app/services/repo_indexer.py:231-250`  [M · L]
- **Stub:**
  ```python
  def _iter_indexable_files(self, root, *, max_files, max_file_bytes):
      files = []
      for dirpath, dirnames, filenames in os.walk(root):
          dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
          for name in filenames:
              if len(files) >= max_files: return
              p = Path(dirpath) / name
              if not p.is_file() or p.stat().st_size > max_file_bytes: continue
              rel = p.relative_to(root)
              if self._is_sensitive_file(rel.as_posix()): continue
              if p.suffix.lower() not in TEXT_EXTENSIONS: continue
              files.append(p)
      return sorted(files)
  ```

### B32. 4 separate `log_text.splitlines()` scans in CI analyzer + 5 regexes per line — `apps/api/app/services/ci_analyzer.py:102-136`  [M · L]
- **Stub:** single pass collecting all 4 signals; call `redact_text` only on the chosen final line(s).

### B33. `_scan_sources` walks the entire workspace when no patch payload — `apps/api/app/services/security_scanner.py:400-424`  [M · L]
- **Stub:** cache file list per scan; skip when manifest mtime unchanged.

### B34. `redact_text` is called per SARIF finding instead of once on the SARIF text — `apps/api/app/services/security_scanner.py:289, 317`  [M · L]
- **Stub:** redact the raw SARIF message text once before the loop.

### B35. `shutil.copytree` + `_write_baseline` (full content in JSON) per implementation run — `apps/api/app/services/tools/registry.py:717-727, 1602-1605`  [M · M]
- **Stub:** use APFS `cp -c` on macOS / `reflink` on Linux; baseline stores `(path, mtime, size, sha256)` only.

### B36. `_safe_env` rebuilt every sandbox call — `apps/api/app/services/sandbox.py:154-162`  [S · L]
- **Stub:** `@functools.lru_cache(maxsize=1) def _safe_env(): ...`.

### B37. `_mock_embedding` does `json.dumps+sha256` per word — `apps/api/app/services/model_gateway.py:357-358`  [S · L]
- **Stub:**
  ```python
  @functools.lru_cache(maxsize=10_000)
  def _word_bucket(word: str, dimensions: int) -> int:
      h = hashlib.md5(word.encode("utf-8")).digest()[:4]
      return int.from_bytes(h, "big") % dimensions
  ```

### B38. `auth.get_current_user` calls `effective_settings` per request — `apps/api/app/services/auth.py:28-55`  [S · L]
- **Auto-fixed by B2.**

### B39. `redact_data` builds a new dict on every call — `apps/api/app/services/security_envelope.py:48-64`  [S · L]
- **Stub:** memoize by `id(value)` for read-only repeated inputs.

### B40. `asdict(normalized)` deep-copies an already-stored dataclass — `apps/api/app/services/github_ingestion.py:400`  [S · L]
- **Stub:** store only the fields you need; skip the asdict.

### B41. `__init__.py` re-exports 80+ Pydantic models with `extra="forbid"` — `packages/shared_contracts/repopilot_contracts/__init__.py:1-165`  [S · L]
- **Stub:** split into sub-modules; `__init__.py` re-exports only the public surface.

### B42. `provider_by_id` and `model_ids_for_provider` linear scan — `packages/llm_client/repopilot_llm_client/model_catalog.py:191-201`  [S · L]
- **Stub:**
  ```python
  _PROVIDER_BY_ID = {p.id: p for p in ALL_PROVIDERS}
  def provider_by_id(pid: str): return _PROVIDER_BY_ID.get(pid)
  ```

### B43. `provider_catalog` re-`asdict`s every provider on every readiness check — `packages/llm_client/repopilot_llm_client/model_catalog.py:187-188`  [S · L]
- **Stub:** cache the JSON-ready dict at import.

### B44. `PolicyConfig()` rebuilt for every `PolicyEngine()` — `packages/policy_engine/repopilot_policy_engine/engine.py:50-95`  [S · L]
- **Stub:** `DEFAULT_POLICY_CONFIG = PolicyConfig(...)`; `PolicyEngine(config=DEFAULT_POLICY_CONFIG)` everywhere.

### B45. `shlex.split` on every command evaluation — `packages/policy_engine/repopilot_policy_engine/engine.py:81-86`  [S · L]
- **Stub:** precomputed dict for the 12 allowlisted commands; skip split when no shell metachars.

### B46. `FixtureVerifier.fixture_path` resolves the path on every call — `packages/evals/repopilot_evals/fixtures.py:19-21, 86-97`  [S · L]
- **Stub:** `@functools.lru_cache def fixture_path(self, repo: str) -> Path`.

### B47. `model_catalog.py` re-export wrapper in `apps/api/app/services/model_catalog.py` is dead weight  [S · L]
- **Stub:** delete the wrapper; import directly from `repopilot_llm_client`.

### B48. `approved_plan_hash_matches` re-dumps and re-hashes the full plan JSON each call — `apps/api/app/services/planning.py:205-211`  [S · L]
- **See B21.** Hash the immutable plan fields only; store the hash on the Plan row at approval time.

---

## 5. Findings — Build, Docker, CI

### C1. Web Dockerfile has no prod target — `apps/web/Dockerfile:1-18`  [L · L]
- **Problem.** Ships dev mode as the only target; `npm ci` installs devDeps; image is fat.
- **Stub:**
  ```dockerfile
  # syntax=docker/dockerfile:1.6
  FROM node:22-alpine AS deps
  WORKDIR /app/apps/web
  COPY apps/web/package*.json ./
  RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev

  FROM node:22-alpine AS builder
  WORKDIR /app/apps/web
  COPY apps/web/package*.json ./
  RUN --mount=type=cache,target=/root/.npm npm ci
  COPY apps/web ./
  ENV NEXT_TELEMETRY_DISABLED=1
  RUN npm run build

  FROM node:22-alpine AS runtime
  WORKDIR /app/apps/web
  COPY --from=deps    /app/apps/web/node_modules ./node_modules
  COPY --from=builder /app/apps/web/.next        ./.next
  COPY --from=builder /app/apps/web/public       ./public
  COPY apps/web/docker-entrypoint.sh ./
  EXPOSE 3000
  USER node
  ENTRYPOINT ["/app/apps/web/docker-entrypoint.sh"]
  CMD ["node", "server.js"]
  ```
  Pair with `output: "standalone"` in `apps/web/next.config.mjs` (A18) and update `docker-entrypoint.sh` to copy `.next/standalone` to `/app/apps/web` and run `node server.js` from there.

### C2. API Dockerfile has no BuildKit cache and ships test data — `apps/api/Dockerfile:9-26`  [L · L]
- **Problem.** `pip install` re-downloads every clean rebuild; blanket `COPY apps/api ./apps/api` includes `tests/` and `celerybeat-schedule`.
- **Stub:**
  ```dockerfile
  # syntax=docker/dockerfile:1.6
  FROM python:3.12-slim AS deps
  WORKDIR /app
  COPY packages/ ./packages/
  COPY apps/api/requirements.txt ./apps/api/requirements.txt
  RUN --mount=type=cache,target=/root/.cache/pip \
      pip install -r apps/api/requirements.txt

  FROM python:3.12-slim AS runtime
  WORKDIR /app
  RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*
  COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
  COPY --from=deps /usr/local/bin /usr/local/bin
  COPY packages/ ./packages/
  COPY apps/api/ ./apps/api/
  RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
  USER appuser
  WORKDIR /app/apps/api
  EXPOSE 8000
  HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD ["python","-c","import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=2).status==200 else 1)"]
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
  Extend `.dockerignore` (see C19).

### C3. `pytest` is in prod `requirements.txt` — `apps/api/requirements.txt:19`  [L · L]
- **Stub:** create `apps/api/requirements-dev.txt` with `pytest>=8.2,<9.0`; remove from `apps/api/requirements.txt:19`.

### C4. `uvicorn[standard]` pulls `watchfiles` and `websockets` — `apps/api/requirements.txt:18`  [L · L]
- **Stub:** change to `uvicorn[performance]>=0.30` in `apps/api/requirements.txt:18` (keeps `uvloop` + `httptools`, drops `watchfiles` + `websockets`).

### C5. CI has no pip cache in `api-tests` — `.github/workflows/ci.yml:59-71`  [L · L]
- **Stub:**
  ```yaml
  - uses: actions/setup-python@v5
    with:
      python-version: "3.12"
      cache: "pip"
      cache-dependency-path: apps/api/requirements.txt
  ```
  Add the same to `package-boundaries` (`:77-79`).

### C6. `sandbox-image` has no Docker layer cache — `.github/workflows/ci.yml:131-136`  [L · L]
- **Stub:**
  ```yaml
  - uses: docker/setup-buildx-action@v3
  - uses: docker/build-push-action@v6
    with:
      context: .
      file: services/sandbox_runner/Dockerfile
      push: false
      tags: repopilot-sandbox:local
      cache-from: type=gha
      cache-to:   type=gha,mode=max
  ```

### C7. No `concurrency:` group on CI — `.github/workflows/ci.yml:1-6`  [M · L]
- **Stub:**
  ```yaml
  on:
    push:
    pull_request:
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```

### C8. `release.yml` runs 3 Docker builds serially — `.github/workflows/release.yml:8-24`  [M · L]
- **Stub:** convert to a matrix of `{api,web,sandbox}` jobs each using `docker/build-push-action@v6` with `cache-from: type=gha,scope=${{ matrix.image }}` and `push: true` to `ghcr.io/${{ github.repository_owner }}/repopilot-${{ matrix.image }}`.

### C9. `worker` and `beat` bind-mount the repo on macOS/Windows — `docker-compose.yml:113-116, 134-137`  [M · M]
- **Stub:** move dev-only mounts to `docker-compose.override.yml`; prod-like run (`docker compose -f docker-compose.yml up`) bakes the image.

### C10. ~30 env vars duplicated across `api`/`worker`/`beat` in compose — `docker-compose.yml:29-69, 87-112, 128-133`  [M · L]
- **Stub:** YAML anchors or `env_file: .env` (`.env.example` is already present); `beat` is currently missing several critical vars (DATABASE_URL, REDIS_URL).

### C11. `web` service `depends_on: - api` doesn't wait for healthy — `docker-compose.yml:149-157`  [M · L]
- **Stub:** add `healthcheck` to api/worker/beat/web and use `condition: service_healthy`.

### C12. No `timeout-minutes` on any job in `ci.yml`  [M · L]
- **Stub:** set `timeout-minutes: 15` on each job.

### C13. `package-boundaries` reinstalls pydantic + 5 source builds with no cache — `ci.yml:73-113`  [M · L]
- **Stub:** add pip cache (C5); consider folding this job into `api-tests` to share the wheel cache.

### C14. Unpinned `pip install` in sandbox Dockerfile — `services/sandbox_runner/Dockerfile:10`  [M · L]
- **Stub:** create `services/sandbox_runner/requirements.txt` with `pytest==8.3.*`, `ruff==0.5.*`, `mypy==1.10.*` and `RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/requirements.txt`.

### C15. Sandbox image installs `nodejs npm` (~150 MB) but only runs Python — `services/sandbox_runner/Dockerfile:7`  [M · M]
- **Stub:** drop `nodejs npm` from line 7 unless a real validation command requires it; verify with `grep -r "node " services/ apps/api/`.

### C16. API Dockerfile has 5 separate `COPY packages/X` layers — `apps/api/Dockerfile:13-17`  [M · L]
- **Stub:** one `COPY packages/ ./packages/` (covered by C2).

### C17. Floating version ranges in `requirements.txt` and `pyproject.toml`s break pip cache  [M · L]
- **Stub:** generate `requirements.lock` via `pip-compile` or `uv pip compile`; commit; install `--no-deps -r requirements.lock` in Docker, plus local wheels.

### C18. `-e ./packages/shared_contracts` in prod requirements forces source-build mode — `apps/api/requirements.txt:1`  [M · L]
- **Stub:** build wheels in a builder stage (`pip wheel ./packages/* -w /wheels`) and `pip install --no-index --find-links=/wheels /wheels/*.whl` in the runtime stage.

### C19. `celerybeat-schedule` (16 KB binary) is committed to git and COPYed into the image — `apps/api/celerybeat-schedule`  [M · L]
- **Stub:** add `celerybeat-schedule*` to `.gitignore` and `.dockerignore`; run `git rm --cached apps/api/celerybeat-schedule`. Extend `.dockerignore`:
  ```gitignore
  tests
  apps/api/tests
  apps/api/celerybeat-schedule
  apps/api/celerybeat-schedule.*
  tmp
  data
  artifacts
  *.log
  htmlcov
  .coverage
  packages/*/build
  packages/*/*.egg-info
  apps/web/tsconfig.tsbuildinfo
  ```

### C20. `web` service `command` duplicates the image `CMD` — `docker-compose.yml:157` vs `apps/web/Dockerfile:17`  [S · L]
- **Stub:** drop `command:` in `docker-compose.yml:157` (or drop `CMD` from the Dockerfile).

### C21. No CPU/memory limits in compose  [S · L]
- **Stub:** add `deploy.resources.limits: { cpus: '1.0', memory: 1G }` to each service.

### C22. API image has no `HEALTHCHECK` — `apps/api/Dockerfile:29-30`  [S · L]
- **Covered by C2.**

### C23. `pre-commit` could combine `ruff` and `ruff-format` — `.pre-commit-config.yaml:2-6`  [S · L]
- **Stub:** one hook with `entry: ruff check --fix && ruff format`.

### C24. `Makefile` has no `up` (no `--build`) / `lint` / `format` / `test` / `shell` / `clean` targets  [S · L]
- **Stub:**
  ```make
  up:        ; $(COMPOSE) up
  up-build:  ; $(COMPOSE) up --build
  lint:      ; $(COMPOSE) exec api ruff check .
  format:    ; $(COMPOSE) exec api ruff format .
  web-lint:  ; $(COMPOSE) exec web npm run typecheck
  test:      ; $(COMPOSE) run --rm api pytest apps/api/tests -q
  shell:     ; $(COMPOSE) exec api bash
  clean:     ; docker system prune -f --volumes
  ```

### C25. `package.json` uses `^` for prod deps — `apps/web/package.json:12-22`  [S · L]
- **Stub:** pin exact versions for production deps; keep `^` only for devDeps.

### C26. Hygiene step uses `find` over the entire repo — `ci.yml:15-18`  [S · L]
- **Stub:** replace with `git ls-files | grep -E '(\.DS_Store|\.secrets|__pycache__|\.pyc$|\.egg-info|\.next|tsconfig\.tsbuildinfo$)'`.

### C27. Service container health-checks not awaited before test steps — `ci.yml:24-71`  [S · L]
- **Stub:** add explicit wait loops or use `actions/wait-for`.

### C28. `web-typecheck` only runs `tsc --noEmit`; no `next build` — `ci.yml:115-129`  [S · L]
- **Stub:** add `npm run build` to a `web-build` job sharing the npm cache.

---

## 6. Cross-cutting observations

- **Three places all share the same plumbing cost:** `effective_settings()` (B2), `db.session.engine` (B1), and `httpx.AsyncClient` (B11) are touched on the request hot path, the Celery hot path, and the model hot path. Fixing all three is the single biggest backend win.
- **Plan JSON is the hottest shared object.** `Plan.plan_json` is re-validated, re-dumped, re-hashed, and re-walked by planning, policy, approval, tool registry, run-implementation, draft PR, and revision planner. One parsed `ImplementationPlan` cache per Plan row saves a non-trivial amount of CPU on every approved run (B12, B21, B28).
- **The 4 000-line `"use client"` file is the biggest web win** (A1) and is also what unblocks A6, A14, and A18. Until it is split, every other web optimization is shadowed.
- **The vector-search hot path (B3) overlaps with B10 (incremental index) and B11 (HTTP client).** Fixing those three together is what makes the system "fast at the part that does the most work" — semantic search and indexing.
- **Image and CI wins are independent** of the app code, so they can be done in parallel with backend or web work.

## 7. Suggested order of execution (phased; each phase stands on its own)

1. **Phase 1 — quick infra + hot-path (1-2 days).** B1, B2, B11, C2, C3, C4, C5, C6, C7, C9, C19.
2. **Phase 2 — eliminate N+1 and re-hash loops (1 week).** B4-B8, B10, B12, B13, B16, B18, B19, B25, B26, B32, B35.
3. **Phase 3 — vector search + sandbox async (1 week).** B3, B9, B11 (full rollout), B27, B28, B29.
4. **Phase 4 — web monolith split + caching tier (1-2 weeks).** A1, A2, A3, A4, A5, A10, A14, A18, C1, C8.
5. **Phase 5 — render/state hygiene (1 week).** A6, A7, A8, A11, A12, A13, A15, A16, A17, A20-A28.
6. **Phase 6 — packages + leftover micro-opts (1-2 days).** B20, B22-B24, B30, B31, B33-B48.

If only three items are done, do **#1 (A1 monolith split), #2 (B1 engine.dispose), #3 (A2 fetch caching tier)**.

## 8. Non-goals / out of scope for this document

- No new features (e.g., SSE for live runs, webhooks for cache invalidation) — only efficiency.
- No security re-review — every change above should still be reviewed by the security owner.
- No product re-design — the dashboard layout, screens, and routes are unchanged in their public surface.

---

*End of document. All items above are proposed changes. **No source code was modified by this document.***
