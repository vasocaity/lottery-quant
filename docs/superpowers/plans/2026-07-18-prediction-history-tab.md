# Prediction History Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Prediction History" tab that lists every persisted prediction run, newest first, with a hit/miss/pending badge against the actual draw that followed it, and an expandable full ranked list per run.

**Architecture:** Backend adds one read-only endpoint (`GET /predictions/history`) that reuses the existing `Prediction`/`Draw` tables — no schema change. Frontend adds one API client method, one new tab, and refactors the two existing prediction-card grids (currently inlined in the Rankings tab) into shared render helpers so the new tab reuses them instead of duplicating markup.

**Tech Stack:** NestJS + Prisma (backend), React + Vite + TS (frontend). No test framework exists anywhere in this repo (checked: no jest/vitest config, no `*.spec.ts`/`*.test.tsx` files, no test scripts in either `package.json`). Verification therefore follows the project's existing convention: `tsc` typechecking + `docker compose` + `curl` / manual browser check (same pattern as the README's "Quick start").

## Global Constraints

- No DB schema changes — everything is derived from the existing `Prediction.items` JSON and `Draw` rows (spec: "No schema changes").
- Cap the history list at `limit = 30` runs, newest first (spec: confirmed scope, no pagination).
- `back3Hit`/`last2Hit` must be `null` (not `false`) when no target draw exists yet ("pending") — never conflate pending with miss.
- Reuse the existing card markup for ranked-list display via extracted render helpers — do not duplicate the JSX (spec: avoid duplicating card markup).
- Follow existing `App.tsx` visual language: dark theme tokens (`#0a1628`, `#1a3a6b`, `#4a9eff`, `#6a8ab8`, `#00ff88`, `#ff6b6b`), monospace font, same grid breakpoints (`minmax(240px,1fr)` for back3, `minmax(160px,1fr)` for last2).

---

### Task 1: Backend — `GET /predictions/history` endpoint

**Files:**
- Modify: `backend/src/predictions/predictions.service.ts` (add `history` method after `hitRate()`, i.e. after line 135)
- Modify: `backend/src/predictions/predictions.controller.ts` (add `history` route after `hitRate()`, i.e. after line 36)
- Modify: `README.md` (add row to the API reference table, after the `/predictions/latest` row)

**Interfaces:**
- Consumes: `this.prisma.draw`, `this.prisma.prediction` (existing Prisma models, see `backend/prisma/schema.prisma`)
- Produces: `PredictionsService.history(limit = 30): Promise<Array<{ id: number; createdAt: Date; modelVersionId: number; back3Items: any[]; last2Items: any[]; target: { date: Date; back3: string; last2: string | null } | null; back3Hit: boolean | null; last2Hit: boolean | null }>>`, exposed at `GET /predictions/history?limit=30`. Task 2's frontend types must match this shape field-for-field.

- [ ] **Step 1: Add the `history` method to `PredictionsService`**

Open `backend/src/predictions/predictions.service.ts`. Insert this method immediately after the closing `}` of `hitRate()` (currently ends at line 135, right before the `onNewDraw` method's doc comment):

```ts
  /**
   * Lists past prediction runs, newest first, each paired with the actual
   * draw that followed it (the "target"). Two-pointer walk over both lists
   * (already sorted ascending) — draws never rewind as predictions advance,
   * same technique as hitRate() above but walking draws instead of preds.
   */
  async history(limit = 30) {
    const [draws, preds] = await Promise.all([
      this.prisma.draw.findMany({ orderBy: { date: 'asc' } }),
      this.prisma.prediction.findMany({ orderBy: { createdAt: 'asc' } }),
    ]);

    let i = 0;
    const results = preds.map((pred) => {
      while (i < draws.length && draws[i].date <= pred.createdAt) i++;
      const target = draws[i] ?? null;

      const stored = pred.items as any;
      const back3Items = stored?.back3_items ?? (Array.isArray(stored) ? stored : []);
      const last2Items = stored?.last2_items ?? [];

      return {
        id: pred.id,
        createdAt: pred.createdAt,
        modelVersionId: pred.modelVersionId,
        back3Items,
        last2Items,
        target: target ? { date: target.date, back3: target.back3, last2: target.last2 } : null,
        back3Hit: target ? back3Items.some((x: any) => x.number === target.back3) : null,
        last2Hit: target && target.last2 ? last2Items.some((x: any) => x.number === target.last2) : null,
      };
    });

    return results.reverse().slice(0, limit);
  }

```

- [ ] **Step 2: Add the route to `PredictionsController`**

Open `backend/src/predictions/predictions.controller.ts`. Insert this method immediately after the closing `}` of `hitRate()` (currently the last method, ending at line 36, before the class's final `}`):

```ts

  @Get('history')
  history(@Query('limit') limit?: string) {
    return this.svc.history(limit ? parseInt(limit, 10) : 30);
  }
```

- [ ] **Step 3: Document the endpoint in the README**

Open `README.md`. In the "API reference" table, add a row right after the `/predictions/latest` row:

```markdown
| GET | `/predictions/history?limit=30` | Past prediction runs (newest first) with hit/miss/pending outcome |
```

- [ ] **Step 4: Typecheck the backend**

Run: `cd backend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Start the stack and verify the endpoint manually**

Run: `docker compose up --build -d` (from repo root)
Then, once containers are healthy:
```bash
docker compose exec backend npx prisma migrate deploy
docker compose exec backend npm run db:seed
curl -X POST http://localhost:3001/api/predictions/train
curl -X POST http://localhost:3001/api/predictions/run
curl http://localhost:3001/api/predictions/history
```
Expected: the last `curl` returns a JSON array with at least one object containing `id`, `createdAt`, `back3Items` (array of 20), `last2Items` (array of 10), and `back3Hit`/`last2Hit` that are either `true`, `false`, or `null`. If only one prediction run has been made and no new draw has landed since, `target` should be `null` and both hit fields `null`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/predictions/predictions.service.ts backend/src/predictions/predictions.controller.ts README.md
git commit -m "feat: add GET /predictions/history endpoint"
```

---

### Task 2: Frontend — API client types and method

**Files:**
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: none new (existing `req<T>` helper, existing `PredictItem`/`Last2Item` interfaces at lines 13-21)
- Produces: `PredictionHistoryItem` interface and `api.predictionHistory(limit = 30): Promise<PredictionHistoryItem[]>`. Task 4's `App.tsx` imports `PredictionHistoryItem` and calls `api.predictionHistory()`.

- [ ] **Step 1: Add the `PredictionHistoryItem` interface**

In `frontend/src/api/client.ts`, insert after the `HitRateReport` interface (line 26):

```ts
export interface PredictionHistoryItem {
  id: number;
  createdAt: string;
  modelVersionId: number;
  back3Items: PredictItem[];
  last2Items: Last2Item[];
  target: { date: string; back3: string; last2: string | null } | null;
  back3Hit: boolean | null;
  last2Hit: boolean | null;
}
```

- [ ] **Step 2: Add the `predictionHistory` method to the `api` object**

In the same file, inside the `export const api = { ... }` object, add this line right after `hitRate: () => req<HitRateReport>('/predictions/hit-rate'),` (line 39):

```ts
  predictionHistory: (limit = 30) => req<PredictionHistoryItem[]>(`/predictions/history?limit=${limit}`),
```

- [ ] **Step 3: Typecheck the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add predictionHistory API client method"
```

---

### Task 3: Frontend — extract shared card-grid render helpers

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `sc(s: number): string` and `pct(s: number): string` (existing helpers at lines 87-88), `PredictItem`/`Last2Item` types (already imported at line 2)
- Produces: two functions in scope inside `App()`, `renderBack3Grid(items: PredictItem[], emptyMsg?: string): JSX.Element` and `renderLast2Grid(items: Last2Item[], emptyMsg?: string): JSX.Element`. Task 4's new tab calls both with per-run data.

This task is a pure refactor — the Rankings tab must render pixel-identical output before and after.

- [ ] **Step 1: Add the two render helper functions**

In `frontend/src/App.tsx`, insert the two functions below right before the `return (` statement (currently line 91), i.e. directly after the `const last = draws[draws.length - 1];` line:

```tsx
  const renderBack3Grid = (items: PredictItem[], emptyMsg = "No 3-digit predictions yet.") => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
      {items.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>{emptyMsg}</div>}
      {items.map((item, idx) => (
        <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 26, fontWeight: 900, color: sc(item.score), letterSpacing: 3 }}>{item.number}</span>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
              <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
            </div>
          </div>
          <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, marginTop: 8 }}>
            {[["LR", item.lr_score], ["RF", item.rf_score], ["GB", item.gb_score]].map(([l, v]) => (
              <div key={l as string} style={{ background: "#050d1a", borderRadius: 4, padding: "3px 0", textAlign: "center" }}>
                <div style={{ color: "#6a8ab8", fontSize: 8 }}>{l}</div>
                <div style={{ color: sc(v as number), fontSize: 11, fontWeight: 700 }}>{pct(v as number)}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8 }}>
            {item.top_features.slice(0, 3).map((f) => (
              <div key={f.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#6a8ab8" }}>
                <span>▸ {f.name.replace("f_", "")}</span>
                <span style={{ color: "#4a9eff" }}>{(f.importance * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );

  const renderLast2Grid = (items: Last2Item[], emptyMsg = "No 2-digit predictions yet.") => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))", gap: 10 }}>
      {items.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>{emptyMsg}</div>}
      {items.map((item, idx) => (
        <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 32, fontWeight: 900, color: sc(item.score), letterSpacing: 4 }}>{item.number}</span>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
              <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
            </div>
          </div>
          <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
            <span style={{ fontSize: 9, color: "#6a8ab8" }}>#{item.rank}</span>
          </div>
        </div>
      ))}
    </div>
  );

```

- [ ] **Step 2: Replace the inlined back3 grid in the Rankings tab with the helper call**

Find this block (currently lines 180-212):

```tsx
            {rankingMode === "back3" && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
                {top20.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>No predictions yet — click "Train + Predict".</div>}
                {top20.map((item, idx) => (
                  <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ fontSize: 26, fontWeight: 900, color: sc(item.score), letterSpacing: 3 }}>{item.number}</span>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
                        <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
                      </div>
                    </div>
                    <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, marginTop: 8 }}>
                      {[["LR", item.lr_score], ["RF", item.rf_score], ["GB", item.gb_score]].map(([l, v]) => (
                        <div key={l as string} style={{ background: "#050d1a", borderRadius: 4, padding: "3px 0", textAlign: "center" }}>
                          <div style={{ color: "#6a8ab8", fontSize: 8 }}>{l}</div>
                          <div style={{ color: sc(v as number), fontSize: 11, fontWeight: 700 }}>{pct(v as number)}</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      {item.top_features.slice(0, 3).map((f) => (
                        <div key={f.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#6a8ab8" }}>
                          <span>▸ {f.name.replace("f_", "")}</span>
                          <span style={{ color: "#4a9eff" }}>{(f.importance * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
```

Replace it with:

```tsx
            {rankingMode === "back3" && renderBack3Grid(top20, 'No predictions yet — click "Train + Predict".')}
```

- [ ] **Step 3: Replace the inlined last2 grid in the Rankings tab with the helper call**

Find this block (currently lines 214-233):

```tsx
            {rankingMode === "last2" && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))", gap: 10 }}>
                {last2Top10.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>No 2-digit predictions yet — click "Train + Predict".</div>}
                {last2Top10.map((item, idx) => (
                  <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 32, fontWeight: 900, color: sc(item.score), letterSpacing: 4 }}>{item.number}</span>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
                        <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
                      </div>
                    </div>
                    <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
                      <span style={{ fontSize: 9, color: "#6a8ab8" }}>#{item.rank}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
```

Replace it with:

```tsx
            {rankingMode === "last2" && renderLast2Grid(last2Top10, 'No 2-digit predictions yet — click "Train + Predict".')}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manually verify the Rankings tab is unchanged**

Run: `cd frontend && npm run dev`, open `http://localhost:5173`, click the "📊 Rankings" tab, toggle between "3-Digit (back3)" and "★ 2-Digit (last2)".
Expected: identical layout/content to before the refactor (same cards, same colors, same empty-state text when no predictions are loaded).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "refactor: extract renderBack3Grid/renderLast2Grid helpers"
```

---

### Task 4: Frontend — Prediction History tab

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api.predictionHistory` and `PredictionHistoryItem` from Task 2, `renderBack3Grid`/`renderLast2Grid` from Task 3
- Produces: new tab `"predhistory"` in the UI. No downstream consumers.

- [ ] **Step 1: Import `PredictionHistoryItem`**

In `frontend/src/App.tsx`, change line 2 from:

```tsx
import { api, type Draw, type PredictItem, type Last2Item, type HitRateReport } from "./api/client";
```

to:

```tsx
import { api, type Draw, type PredictItem, type Last2Item, type HitRateReport, type PredictionHistoryItem } from "./api/client";
```

- [ ] **Step 2: Add state for prediction history and the expanded row**

Find this line (currently line 17):

```tsx
  const [hitRate, setHitRate] = useState<HitRateReport | null>(null);
```

Add immediately after it:

```tsx
  const [predHistory, setPredHistory] = useState<PredictionHistoryItem[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
```

- [ ] **Step 3: Add the `loadPredictionHistory` callback**

Find this block (currently lines 43-45):

```tsx
  const loadHitRate = useCallback(async () => {
    try { setHitRate(await api.hitRate()); } catch { /* backend may be older */ }
  }, []);
```

Add immediately after it:

```tsx

  const loadPredictionHistory = useCallback(async () => {
    setPredHistory(await api.predictionHistory());
  }, []);
```

- [ ] **Step 4: Load prediction history on mount**

Find this block (currently lines 47-51):

```tsx
  useEffect(() => {
    loadDraws();
    loadLatest();
    loadHitRate();
  }, [loadDraws, loadLatest, loadHitRate]);
```

Replace with:

```tsx
  useEffect(() => {
    loadDraws();
    loadLatest();
    loadHitRate();
    loadPredictionHistory();
  }, [loadDraws, loadLatest, loadHitRate, loadPredictionHistory]);
```

- [ ] **Step 5: Refresh prediction history after training and after adding a draw**

In `handleTrain` (currently lines 53-63), find:

```tsx
    const fi = await api.featureImportance();
    setWeights(fi.weights);
    await loadHitRate();
    setBusy(null);
  };
```

Replace with:

```tsx
    const fi = await api.featureImportance();
    setWeights(fi.weights);
    await loadHitRate();
    await loadPredictionHistory();
    setBusy(null);
  };
```

In `handleAddDraw` (currently lines 73-85), find:

```tsx
    setNewDraw({ date: "", back3: "", last2: "", firstPrize: "" });
    await loadHitRate();
    setBusy(null);
  };
```

Replace with:

```tsx
    setNewDraw({ date: "", back3: "", last2: "", firstPrize: "" });
    await loadHitRate();
    await loadPredictionHistory();
    setBusy(null);
  };
```

- [ ] **Step 6: Add the tab to the nav strip**

Find this block (currently lines 129-135):

```tsx
        <nav style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid #1a3a6b" }}>
          {["rankings", "backtest", "history", "adddata"].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={tabBtn(tab === t)}>
              {{ rankings: "📊 Rankings", backtest: "📈 Backtest", history: "📋 History", adddata: "➕ Add Draw" }[t]}
            </button>
          ))}
        </nav>
```

Replace with:

```tsx
        <nav style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid #1a3a6b" }}>
          {["rankings", "backtest", "history", "predhistory", "adddata"].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={tabBtn(tab === t)}>
              {{ rankings: "📊 Rankings", backtest: "📈 Backtest", history: "📋 History", predhistory: "🕘 Prediction History", adddata: "➕ Add Draw" }[t]}
            </button>
          ))}
        </nav>
```

- [ ] **Step 7: Add the new tab body**

Find the `{tab === "adddata" && (` block (currently starting at line 268). Insert this new tab body immediately **before** it:

```tsx
        {tab === "predhistory" && (
          <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10 }}>
            {predHistory.length === 0 && (
              <div style={{ padding: 14, color: "#6a8ab8", fontSize: 12 }}>
                No prediction runs yet — click "Train + Predict".
              </div>
            )}
            {predHistory.map((run) => {
              const badge = (hit: boolean | null) =>
                hit === null
                  ? { text: "… pending", color: "#6a8ab8" }
                  : hit
                  ? { text: "✓ hit", color: "#00ff88" }
                  : { text: "✗ miss", color: "#ff6b6b" };
              const b3 = badge(run.back3Hit);
              const l2 = badge(run.last2Hit);
              const isOpen = expandedId === run.id;
              return (
                <div key={run.id} style={{ borderTop: "1px solid #0d1f3c" }}>
                  <div
                    onClick={() => setExpandedId(isOpen ? null : run.id)}
                    style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", alignItems: "center", gap: 10, padding: "8px 14px", fontSize: 11, cursor: "pointer" }}
                  >
                    <span style={{ color: "#e0e8ff" }}>{new Date(run.createdAt).toLocaleString()}</span>
                    <span style={{ color: "#6a8ab8" }}>
                      {run.target ? `→ ${run.target.date.slice(0, 10)} (${run.target.back3}/${run.target.last2 ?? "—"})` : "pending"}
                    </span>
                    <span style={{ color: b3.color }}>3D {b3.text}</span>
                    <span style={{ color: l2.color }}>2D {l2.text}</span>
                  </div>
                  {isOpen && (
                    <div style={{ padding: "0 14px 14px" }}>
                      <div style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", margin: "8px 0" }}>2-Digit</div>
                      {renderLast2Grid(run.last2Items)}
                      <div style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", margin: "12px 0 8px" }}>3-Digit</div>
                      {renderBack3Grid(run.back3Items)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

```

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 9: Manually verify end-to-end**

With the stack still running from Task 1 (`docker compose up`) and frontend dev server running (`npm run dev` in `frontend/`):
1. Open `http://localhost:5173`, click "🕘 Prediction History".
2. Confirm the run(s) created in Task 1's verification appear, newest first.
3. Click a row — confirm it expands to show the full 2-digit and 3-digit grids, and collapses again on a second click.
4. Click "⚡ Train + Predict" — confirm a new row appears at the top of the Prediction History tab after training finishes.
5. Add a draw via the "➕ Add Draw" tab with a date after the run's target — confirm the corresponding row's badge updates from "pending" to "hit"/"miss" on next load.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add Prediction History tab"
```

---

## Post-plan check

- [ ] Re-read `docs/superpowers/specs/2026-07-18-prediction-history-tab-design.md` end to end and confirm every section (Backend, Frontend data layer, Frontend UI) is covered by a task above.
