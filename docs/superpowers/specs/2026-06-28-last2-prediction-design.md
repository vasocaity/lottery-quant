# Last2 (2 ตัวล่าง) Prediction — Design Spec

**Date:** 2026-06-28  
**Status:** Approved

## Goal

Add ML prediction for the 2-digit bottom prize (`last2` / 2 ตัวล่าง) alongside the existing 3-digit (`back3`) prediction. Display the top-10 `last2` predictions in a new "2-Digit" sub-tab inside the Rankings view.

---

## Architecture

```
DB (draws: date, back3, last2)
  └─ forMl() → [{ date, back3, last2 }]
       └─ ML /train  → trains back3 ensemble + last2 RF → persists ensemble.pkl + last2.pkl
       └─ ML /predict → scores 1000 back3 + 100 last2 candidates
            └─ { items: PredictItem[], last2_items: Last2Item[] }
                 └─ stored in Prediction.items (JSON)
                 └─ broadcast over WebSocket
                 └─ React Rankings → "3-Digit" sub-tab | "2-Digit" sub-tab
```

---

## ML Service

### New file: `ml-service/app/features_2d.py`

Feature extraction for two-digit candidates (00–99). Features:

| Group | Features |
|---|---|
| Frequency | overall freq, last-10 freq, last-30 freq, per-position digit freq |
| Gap | draws-since-last, overdue ratio, avg gap, gap z-score |
| Pair | the one digit-pair (d0+d1), mirror (reverse), transition d0→d0′, d1→d1′ |
| Pattern | is_double (d0==d1), is_consecutive, digit sum, digital root |
| Time | month frequency, draw_seq |
| Hot/Cold | is_hot (appeared in last 10), is_cold (not in last 30) |

Single `FEATURE_NAMES_2D` list in canonical order. `vectorize_2d(feat)` converts dict → numpy row.

### New file: `ml-service/app/model_last2.py`

- **Model:** `RandomForestClassifier(n_estimators=200, max_depth=8, max_features=0.6, class_weight="balanced", random_state=42, n_jobs=-1)` wrapped in a `Last2Bundle` class with a `StandardScaler`.
- **Training data:** positives = two-digit numbers that appeared in `last2` history (with features computed just before each appearance); negatives = numbers that never appeared + hard negatives (2× positives count).
- **Persistence:** `models/last2.pkl` — same `models/` volume as `ensemble.pkl`.
- **Exports:** `train_last2(draws)`, `load_last2()`, `Last2Bundle`.

### Changes to `ml-service/app/main.py`

- `Draw` schema already has `last2: str` (already added).
- `/train`: call `train_last2(draws)` after the existing `train_and_persist(draws)`; response adds `last2_status: "trained"`.
- `/predict`: after scoring 1000 back3 candidates, score 100 two-digit candidates (00–99) with `load_last2()`; append `last2_items: List[Last2Item]` (top `top_n`, default 10) to the response. `Last2Item` = `{rank, number, score, confidence}`.

---

## Backend

### `draws.service.ts` — `forMl()`

Add `last2` to the returned objects:

```ts
return rows.map((r) => ({
  date: r.date.toISOString().slice(0, 10),
  back3: r.back3,
  last2: r.last2 ?? '',
}));
```

### `ml.service.ts` — `DrawDto`

```ts
export interface DrawDto { date: string; back3: string; last2?: string; }
```

### `predictions.service.ts` — `predict()`

The ML response now contains both `items` (back3) and `last2_items`. Store the prediction as:

```json
{ "back3_items": [...], "last2_items": [...] }
```

in `Prediction.items`. The `latest` endpoint and WebSocket `emitPrediction` broadcast both arrays. No Prisma migration needed — `items` is already `Json`.

---

## Frontend

### `api/client.ts`

Add:
```ts
export interface Last2Item {
  rank: number; number: string; score: number; confidence: string;
}
```

Update `runPrediction` and `latest` responses to carry `last2_items: Last2Item[]`.

### `App.tsx`

- Add `last2Top10` state: `useState<Last2Item[]>([])`.
- Populate from `res.last2_items` in `handleTrain`, `loadLatest`, and `livePrediction` effect.
- In the Rankings tab: add a secondary toggle (`rankingMode: "back3" | "last2"`) rendered as two small buttons above the grid.
  - `back3` mode: existing 20-card grid (unchanged).
  - `last2` mode: 10-card grid, same dark card style, showing 2-digit number, score %, and confidence. No LR/GB breakdown (RF-only model).

---

## What Does NOT Change

- Prisma schema — no migration needed
- Backtest endpoint — back3 only (last2 backtest not in scope)
- Feature importance endpoint — back3 only
- Add Draw form — already has `last2` input
- History tab — already shows `last2`

---

## File Checklist

| File | Change |
|---|---|
| `ml-service/app/features_2d.py` | New — 2-digit feature extraction |
| `ml-service/app/model_last2.py` | New — RF training + persistence for last2 |
| `ml-service/app/main.py` | Update `/train` + `/predict` |
| `backend/src/draws/draws.service.ts` | `forMl()` adds `last2` |
| `backend/src/ml/ml.service.ts` | `DrawDto` adds `last2?` |
| `backend/src/predictions/predictions.service.ts` | Store + broadcast `last2_items` |
| `frontend/src/api/client.ts` | Add `Last2Item`, update response types |
| `frontend/src/App.tsx` | `last2Top10` state + 2-Digit sub-tab |
| `backend/src/websocket/predictions.gateway.ts` | `emitPrediction` carries `{ back3_items, last2_items }` |
