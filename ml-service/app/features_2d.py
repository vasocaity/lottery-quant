"""
Feature engineering for Thai Lottery 2-digit (last2 / 2 ตัวล่าง) combinations.
"""
from __future__ import annotations
import math
from datetime import datetime
from typing import List, Dict
import numpy as np

FEATURE_NAMES_2D: List[str] = [
    "f2_freq", "f2_freq10", "f2_freq30",
    "f2_pos_freq0", "f2_pos_freq1",
    "f2_gap_since", "f2_overdue_ratio", "f2_avg_gap", "f2_gap_zscore",
    "f2_mirror_freq",
    "f2_trans0", "f2_trans1",
    "f2_is_double", "f2_is_cons",
    "f2_digit_sum", "f2_digital_root",
    "f2_month_freq",
    "f2_is_hot", "f2_is_cold",
]


def _d2(s: str):
    return [int(c) for c in s]


def extract_features_2d(
    candidate: int,
    series: List[str],
    dates: List[str],
    target_month: int | None = None,
) -> Dict[str, float]:
    s = str(candidate).zfill(2)
    n = len(series)
    d0, d1 = _d2(s)

    freq = series.count(s) / max(n, 1)
    r10, r30 = series[-10:], series[-30:]
    freq10 = r10.count(s) / max(len(r10), 1)
    freq30 = r30.count(s) / max(len(r30), 1)
    pos_freq = [
        sum(1 for x in series if len(x) >= 2 and x[p] == s[p]) / max(n, 1)
        for p in range(2)
    ]

    idxs = [i for i, x in enumerate(series) if x == s]
    gap_since = (n - idxs[-1]) if idxs else n
    gaps = [idxs[i] - idxs[i - 1] for i in range(1, len(idxs))] or [n]
    avg_gap = sum(gaps) / len(gaps)
    overdue = (gap_since / avg_gap) if avg_gap > 0 else 1.0
    if len(gaps) > 1:
        std = math.sqrt(sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)) or 1.0
        gap_z = (gap_since - avg_gap) / std
    else:
        gap_z = 0.0

    mirror_freq = series.count(s[::-1]) / max(n, 1)

    pos_trans = []
    for pos in range(2):
        counts: Dict[str, int] = {}
        for i in range(1, n):
            if len(series[i - 1]) >= 2 and len(series[i]) >= 2:
                k = f"{series[i-1][pos]}->{series[i][pos]}"
                counts[k] = counts.get(k, 0) + 1
        last_d = series[-1][pos] if n and len(series[-1]) >= 2 else "0"
        total = sum(v for k, v in counts.items() if k.startswith(last_d + "->"))
        hit = counts.get(f"{last_d}->{s[pos]}", 0)
        pos_trans.append(hit / total if total else 0.1)

    is_double = 1.0 if d0 == d1 else 0.0
    is_cons = 1.0 if abs(d0 - d1) == 1 else 0.0
    digit_sum = d0 + d1
    digital_root = (digit_sum - 1) % 9 + 1 if digit_sum else 0

    if target_month is None:
        target_month = datetime.utcnow().month
    same_month = [series[i] for i in range(n) if datetime.fromisoformat(dates[i]).month == target_month]
    month_freq = same_month.count(s) / max(len(same_month), 1)

    return {
        "f2_freq": freq,
        "f2_freq10": freq10,
        "f2_freq30": freq30,
        "f2_pos_freq0": pos_freq[0],
        "f2_pos_freq1": pos_freq[1],
        "f2_gap_since": gap_since / max(n, 1),
        "f2_overdue_ratio": min(overdue, 5) / 5,
        "f2_avg_gap": min(avg_gap, n) / max(n, 1),
        "f2_gap_zscore": math.tanh(gap_z / 3),
        "f2_mirror_freq": mirror_freq,
        "f2_trans0": pos_trans[0],
        "f2_trans1": pos_trans[1],
        "f2_is_double": is_double,
        "f2_is_cons": is_cons,
        "f2_digit_sum": digit_sum / 18,
        "f2_digital_root": digital_root / 9,
        "f2_month_freq": month_freq,
        "f2_is_hot": 1.0 if s in series[-10:] else 0.0,
        "f2_is_cold": 1.0 if s not in series[-30:] else 0.0,
    }


def vectorize_2d(feat: Dict[str, float]) -> np.ndarray:
    return np.array([feat[name] for name in FEATURE_NAMES_2D], dtype=float)
