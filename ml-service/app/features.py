"""
Feature engineering for Thai Lottery 3-digit (back3) combinations.
Produces a fixed-length numeric vector per candidate, computed against a
given historical context (so it can be used both for training-at-draw-time
and for live scoring).
"""
from __future__ import annotations
import math
from datetime import datetime
from typing import List, Dict
import numpy as np

# Canonical, ordered feature names. Order MUST stay stable so the persisted
# .pkl model and the live scorer agree on column meaning.
FEATURE_NAMES: List[str] = [
    # frequency
    "f_freq", "f_freq10", "f_freq30",
    "f_pos_freq0", "f_pos_freq1", "f_pos_freq2",
    # gap
    "f_gap_since", "f_overdue_ratio", "f_avg_gap", "f_gap_zscore",
    # pair
    "f_pair01", "f_pair12", "f_pair02", "f_mirror_freq", "f_reverse_freq",
    # transition / markov
    "f_trans0", "f_trans1", "f_trans2", "f_markov_prob",
    # pattern
    "f_is_asc", "f_is_desc", "f_has_rep", "f_is_palin", "f_is_cons", "f_is_allsame",
    "f_hist_asc", "f_hist_rep", "f_hist_palin",
    # sum
    "f_digit_sum", "f_digital_root", "f_variance", "f_sum_delta", "f_dr_freq",
    # statistical
    "f_entropy", "f_is_hot", "f_is_cold", "f_hotness_trend",
    # bayesian / time
    "f_bayes_post", "f_month_freq", "f_draw_seq",
]


def _digits(s: str):
    return [int(c) for c in s]


def extract_features(
    candidate: int,
    series: List[str],
    dates: List[str],
    target_month: int | None = None,
) -> Dict[str, float]:
    """series: ordered list of historical back3 strings (oldest -> newest).
    dates:  parallel list of ISO date strings for the same draws.
    """
    s = str(candidate).zfill(3)
    n = len(series)
    d0, d1, d2 = _digits(s)

    # ---------- 1. frequency ----------
    freq = series.count(s) / max(n, 1)
    r10, r30 = series[-10:], series[-30:]
    freq10 = r10.count(s) / max(len(r10), 1)
    freq30 = r30.count(s) / max(len(r30), 1)
    pos_freq = [sum(1 for x in series if x[p] == s[p]) / max(n, 1) for p in range(3)]

    # ---------- 2. gap ----------
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

    # ---------- 3. pair ----------
    all_pairs = []
    for x in series:
        all_pairs += [x[0:2], x[1:3], x[0] + x[2]]
    my_pairs = [s[0:2], s[1:3], s[0] + s[2]]
    pair_freqs = [all_pairs.count(p) / max(len(all_pairs), 1) for p in my_pairs]
    mirror = s[::-1]
    mirror_freq = series.count(mirror) / max(n, 1)
    reverse_freq = sum(1 for x in series if x[0] == s[2] and x[2] == s[0]) / max(n, 1)

    # ---------- 4. transition (position-level) ----------
    pos_trans = []
    for pos in range(3):
        counts: Dict[str, int] = {}
        for i in range(1, n):
            k = f"{series[i-1][pos]}->{series[i][pos]}"
            counts[k] = counts.get(k, 0) + 1
        last_digit = series[-1][pos] if n else "0"
        total = sum(v for k, v in counts.items() if k.startswith(last_digit + "->"))
        hit = counts.get(f"{last_digit}->{s[pos]}", 0)
        pos_trans.append(hit / total if total else 0.1)

    # ---------- 5. markov chain (full 3-digit, 1st order) ----------
    mk: Dict[str, Dict[str, int]] = {}
    for i in range(1, n):
        frm, to = series[i - 1], series[i]
        mk.setdefault(frm, {})
        mk[frm][to] = mk[frm].get(to, 0) + 1
    last_num = series[-1] if n else "000"
    from_last = mk.get(last_num, {})
    mk_total = sum(from_last.values())
    markov_prob = (from_last.get(s, 0) / mk_total) if mk_total else 1 / 1000

    # ---------- 6. pattern ----------
    is_asc = 1.0 if d0 < d1 < d2 else 0.0
    is_desc = 1.0 if d0 > d1 > d2 else 0.0
    has_rep = 1.0 if (d0 == d1 or d1 == d2 or d0 == d2) else 0.0
    is_palin = 1.0 if d0 == d2 else 0.0
    is_cons = 1.0 if ((d1 - d0 == 1 and d2 - d1 == 1) or (d0 - d1 == 1 and d1 - d2 == 1)) else 0.0
    is_allsame = 1.0 if d0 == d1 == d2 else 0.0

    def _rate(pred):
        return sum(1 for x in series if pred(_digits(x))) / max(n, 1)

    hist_asc = _rate(lambda d: d[0] < d[1] < d[2])
    hist_rep = _rate(lambda d: d[0] == d[1] or d[1] == d[2] or d[0] == d[2])
    hist_palin = sum(1 for x in series if x[0] == x[2]) / max(n, 1)

    # ---------- 7. sum ----------
    digit_sum = d0 + d1 + d2
    digital_root = (digit_sum - 1) % 9 + 1 if digit_sum else 0
    mean = digit_sum / 3
    variance = ((d0 - mean) ** 2 + (d1 - mean) ** 2 + (d2 - mean) ** 2) / 3
    hist_sums = [sum(_digits(x)) for x in series]
    avg_hist_sum = sum(hist_sums) / max(len(hist_sums), 1)
    sum_delta = abs(digit_sum - avg_hist_sum)

    def _dr(x):
        ss = sum(_digits(x))
        return (ss - 1) % 9 + 1 if ss else 0
    dr_freq = sum(1 for x in series if _dr(x) == digital_root) / max(n, 1)

    # ---------- 8. entropy ----------
    cnt: Dict[int, int] = {}
    for d in (d0, d1, d2):
        cnt[d] = cnt.get(d, 0) + 1
    entropy = -sum((c / 3) * math.log2(c / 3) for c in cnt.values())

    # ---------- 9. hot/cold ----------
    is_hot = 1.0 if s in series[-10:] else 0.0
    is_cold = 1.0 if s not in series[-50:] else 0.0
    hotness_trend = freq30 - freq

    # ---------- 10. time ----------
    if target_month is None:
        target_month = datetime.utcnow().month
    same_month = [series[i] for i in range(n) if datetime.fromisoformat(dates[i]).month == target_month]
    month_freq = same_month.count(s) / max(len(same_month), 1)
    draw_seq = n / 300.0

    # ---------- 11. bayesian ----------
    prior = 1 / 1000
    likelihood = max(freq, 1e-6)
    bayes_post = (likelihood * prior) / (likelihood * prior + (1 - likelihood) * (1 - prior))

    return {
        "f_freq": freq, "f_freq10": freq10, "f_freq30": freq30,
        "f_pos_freq0": pos_freq[0], "f_pos_freq1": pos_freq[1], "f_pos_freq2": pos_freq[2],
        "f_gap_since": gap_since / max(n, 1), "f_overdue_ratio": min(overdue, 5) / 5,
        "f_avg_gap": min(avg_gap, n) / max(n, 1), "f_gap_zscore": math.tanh(gap_z / 3),
        "f_pair01": pair_freqs[0], "f_pair12": pair_freqs[1], "f_pair02": pair_freqs[2],
        "f_mirror_freq": mirror_freq, "f_reverse_freq": reverse_freq,
        "f_trans0": pos_trans[0], "f_trans1": pos_trans[1], "f_trans2": pos_trans[2],
        "f_markov_prob": min(markov_prob * 1000, 1),
        "f_is_asc": is_asc, "f_is_desc": is_desc, "f_has_rep": has_rep,
        "f_is_palin": is_palin, "f_is_cons": is_cons, "f_is_allsame": is_allsame,
        "f_hist_asc": hist_asc, "f_hist_rep": hist_rep, "f_hist_palin": hist_palin,
        "f_digit_sum": digit_sum / 27, "f_digital_root": digital_root / 9,
        "f_variance": min(variance, 27) / 27, "f_sum_delta": max(0, 1 - sum_delta / 10),
        "f_dr_freq": dr_freq,
        "f_entropy": max(0, min(entropy, 1.585)) / 1.585,
        "f_is_hot": is_hot, "f_is_cold": is_cold, "f_hotness_trend": math.tanh(hotness_trend * 100),
        "f_bayes_post": min(bayes_post * 10000, 1),
        "f_month_freq": month_freq, "f_draw_seq": draw_seq,
    }


def vectorize(feat: Dict[str, float]) -> np.ndarray:
    """Convert a feature dict to an ordered numpy row using FEATURE_NAMES."""
    return np.array([feat[name] for name in FEATURE_NAMES], dtype=float)
