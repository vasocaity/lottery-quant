# History Frequency Ranking Tab — Design

## Purpose

Add a new frontend tab that ranks lottery numbers by how often they have
actually appeared in the historical `draws` table — pure descriptive
statistics, distinct from the existing ML-driven "Rankings" tab. This gives
the user a way to sanity-check the ML predictions against raw historical
frequency, consistent with the project's existing "no edge" framing
(see hit-rate disclaimer already shown on the Rankings tab).

## Scope

- Frontend-only change (`frontend/src/App.tsx`). No backend or API changes —
  the full `draws` list is already loaded client-side via
  `api.listDraws()`.
- Covers both `last2` (2-digit) and `back3` (3-digit) numbers, toggled the
  same way the Rankings tab toggles `rankingMode`.
- Shows the top 20 numbers by historical hit count, per mode.

## Data model / computation

New tab key `"freqrank"` added to the existing `tab` state alongside
`rankings | backtest | history | adddata`. New local state `histMode:
"last2" | "back3"` (independent of `rankingMode`, so switching tabs doesn't
disturb the ML rankings view).

Frequency table is derived (via `useMemo`, keyed on `draws` and `histMode`)
from the already-loaded `draws` array, which the backend returns ordered
ascending by date (`DrawsService.findAll` — `orderBy: { date: 'asc' }`):

1. Iterate `draws` in order, keyed by `histMode` (`d.back3` or `d.last2`).
   Skip empty/missing values (e.g. `last2` can be undefined on older rows).
2. For each number, accumulate `count` and the `lastIndex` (array index) of
   its most recent occurrence.
3. `drawsSinceLastSeen = draws.length - 1 - lastIndex`.
4. `lastSeenDate = draws[lastIndex].date`.
5. `pct = count / draws.length`.
6. Sort by `count` desc, tie-break by `lastIndex` desc (more recent first).
7. Take the top 20 entries.

This is pure derived state — no new component state beyond `histMode`, no
new API calls.

## UI

- Nav strip: add `"freqrank"` to the tab list with label `"🏆 Freq Rank"`.
- Tab body follows the existing visual language (dark cards, monospace,
  same color tokens used elsewhere in `App.tsx`):
  - Same `last2`/`back3` toggle buttons as used in the Rankings tab
    (extracted styling reused, not duplicated markup).
  - Card grid (`repeat(auto-fill,minmax(160px,1fr))` for last2,
    `minmax(240px,1fr)` for back3 — matching existing grid breakpoints).
  - Each card shows: rank (`#N`), the number (large, bold), hit count,
    percentage of all draws, and "last seen: N draws ago (YYYY-MM-DD)".
  - Empty state ("No draws loaded yet") when `draws.length === 0`.
  - A small disclaimer note under the toggle, consistent with the existing
    hit-rate scoreboard note: this is raw historical frequency, not a
    prediction — past frequency does not imply future probability.

## Out of scope

- No backend endpoint — everything is derived from data already in memory.
- No persistence of the ranking (it's recomputed on the fly).
- No pagination/"show all" option (top 20 confirmed with user).
