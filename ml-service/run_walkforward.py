#!/usr/bin/env python3
"""Offline walk-forward backtest runner.

Loads the historical draws and prints a baseline-relative, significance-tested
report. Run this directly (it can take minutes) instead of the HTTP endpoint:

    python3 run_walkforward.py
    python3 run_walkforward.py --start-frac 0.5 --retrain-every 10
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.model import walk_forward_backtest  # noqa: E402
from app.model_last2 import walk_forward_last2  # noqa: E402

DEFAULT_DATA = os.path.join(os.path.dirname(__file__), "app", "results.json")


def _print_report(title, rep):
    print(f"\n=== {title} ===")
    print(f"space={rep['space']}  out-of-sample predictions={rep['n_predictions']}  "
          f"(start_index={rep['start_index']}, retrain_every={rep['retrain_every']})")
    print(f"{'k':>4} {'hits':>6} {'expected':>9} {'hit%':>7} {'base%':>7} "
          f"{'lift':>6} {'p-value':>9}  signal")
    for row in rep["by_k"]:
        flag = "  *** beats random" if row["beats_random_p05"] else ""
        print(f"{row['k']:>4} {row['hits']:>6} {row['expected_hits']:>9} "
              f"{row['hit_rate_pct']:>7} {row['baseline_rate_pct']:>7} "
              f"{str(row['lift']):>6} {row['p_value']:>9}{flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--start-frac", type=float, default=0.6)
    ap.add_argument("--retrain-every", type=int, default=10)
    args = ap.parse_args()

    with open(args.data) as f:
        raw = json.load(f)
    draws = raw["draws"] if isinstance(raw, dict) else raw
    print(f"Loaded {len(draws)} draws from {args.data}")

    b3 = walk_forward_backtest(draws, args.start_frac, args.retrain_every)
    _print_report("back3 (3 digits, 1000 combos)", b3)

    l2 = walk_forward_last2(draws, args.start_frac, args.retrain_every)
    _print_report("last2 (2 digits, 100 combos)", l2)

    print("\nNull hypothesis: draws are uniform random. p < 0.05 in any row means "
          "the model's hit count is unlikely to be chance. lift = hit_rate / "
          "random_rate (1.0 = no edge).")


if __name__ == "__main__":
    main()
