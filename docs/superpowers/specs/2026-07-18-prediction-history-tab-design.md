# Prediction History Tab — Design

Supersedes `2026-07-18-history-frequency-ranking-design.md`: the user
redirected the "new tab to see histories ranking" request away from raw
draw-frequency stats and toward browsing each past **prediction run** the
model has made, with its outcome against the actual draw. The earlier spec
is removed since nothing was implemented from it.

## Purpose

Every call to `POST /predictions/run` already persists a `Prediction` row
(`items` JSON with `back3_items`/`last2_items`, `createdAt`,
`modelVersionId`) — see `backend/prisma/schema.prisma`. Nothing currently
lists them; the frontend only ever fetches the single latest one
(`/predictions/latest`). This adds a tab to browse that history and see,
per run, whether the numbers it predicted actually hit.

## Backend

`PredictionsService.history(limit = 30)`:

1. Fetch all `draws` ordered `date asc` and all `predictions` ordered
   `createdAt asc` (same shape of query already used in `hitRate()`).
2. Two-pointer walk: for each prediction, find the **target draw** — the
   first draw with `date > prediction.createdAt` (the next official result
   after that prediction was made). If none exists yet, the run is
   "pending".
3. For each prediction build:
   ```
   {
     id, createdAt, modelVersionId,
     back3Items: PredictItem[], last2Items: Last2Item[],   // full stored arrays, unchanged
     target: { date, back3, last2 } | null,
     back3Hit: boolean | null,   // null = pending (no target draw yet)
     last2Hit: boolean | null,
   }
   ```
   `back3Hit` = `back3Items.some(x => x.number === target.back3)`;
   `last2Hit` analogous, `null` if `target.last2` is missing.
4. Sort results `createdAt` desc (newest first), take the first `limit`.

`PredictionsController`: add `GET /predictions/history?limit=30` calling
`svc.history(limit ? parseInt(limit, 10) : 30)`.

No schema changes — `Prediction.items` already stores everything needed.

## Frontend data layer (`client.ts`)

```ts
export interface PredictionHistoryItem {
  id: number; createdAt: string; modelVersionId: number;
  back3Items: PredictItem[]; last2Items: Last2Item[];
  target: { date: string; back3: string; last2: string | null } | null;
  back3Hit: boolean | null; last2Hit: boolean | null;
}
```
`api.predictionHistory: (limit = 30) => req<PredictionHistoryItem[]>(`/predictions/history?limit=${limit}`)`

## Frontend UI (`App.tsx`)

- New tab `"predhistory"` added to the nav list, label `"🕘 Prediction History"`.
- New state `predHistory: PredictionHistoryItem[]`, loaded via a new
  `loadPredictionHistory` callback that runs:
  - once on mount, alongside the existing `loadDraws`/`loadLatest`/`loadHitRate`;
  - again after `handleTrain` and `handleAddDraw` complete, since both create
    a new `Prediction` row (same pattern already used for `loadHitRate`).
- New local state `expandedId: number | null` — only one run's detail open
  at a time.
- **Refactor**: extract the two card-grid blocks currently inlined in the
  `tab === "rankings"` section into two render helpers,
  `renderBack3Grid(items: PredictItem[])` and
  `renderLast2Grid(items: Last2Item[])`, returning the existing JSX
  unchanged. The Rankings tab calls them with `top20`/`last2Top10`; the new
  tab's expanded row calls them with `run.back3Items`/`run.last2Items`. This
  avoids duplicating the card markup.
- Row (collapsed), one per run, newest first:
  - run timestamp, target draw date or "pending",
  - a hit/miss/pending badge per mode (e.g. green "✓ hit", red "✗ miss",
    grey "… pending"), computed straight from `back3Hit`/`last2Hit`.
  - clicking the row toggles `expandedId` to show the full grids via the
    two render helpers described above.
- Empty state: "No prediction runs yet — click Train + Predict." when
  `predHistory.length === 0`.

## Out of scope

- No new DB fields/migration.
- No pagination beyond the `limit=30` cap (matches confirmed scope).
- No change to `/predictions/latest` or `/predictions/hit-rate` — this is
  additive.
