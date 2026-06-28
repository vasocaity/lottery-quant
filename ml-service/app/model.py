"""
Trains the ensemble (LogisticRegression + RandomForest + GradientBoosting),
optimizes ensemble weights via rolling-window backtest, and persists the whole
bundle to a single .pkl artifact.
"""
from __future__ import annotations
import os
import pickle
from datetime import datetime
from typing import List, Dict, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from .features import extract_features, vectorize, FEATURE_NAMES

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "ensemble.pkl")


# ----------------------------------------------------------------------------
# training-data construction
# ----------------------------------------------------------------------------
NEG_PER_DRAW = 6


def build_training_data(draws: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
    series = [d["back3"] for d in draws]
    dates = [d["date"] for d in draws]
    X, y = [], []

    appeared = set(series)
    seen = set()
    
    for i, num in enumerate(series):
        if num in seen or i < 5:
            seen.add(num)
            continue
        seen.add(num)
        
        ctx_series = series[:i]
        ctx_dates = dates[:i]
        month = datetime.fromisoformat(dates[i]).month
        
        # 1. Positive class (เลขที่ออกในงวดนั้น)
        feat = extract_features(int(num), ctx_series, ctx_dates, month)
        X.append(vectorize(feat))
        y.append(1)

        # 2. Negative class (สร้างเลขที่สุ่มไม่ถูกรางวัล ณ งวด i นั้น ๆ ด้วย เพื่อให้ context เท่ากัน)
        # สุ่มเลขที่ไม่ได้ออกในงวดนี้มาเป็นตัวอย่างฝั่ง Negative แทนการดึง Full History นอกลูป
        rng = np.random.default_rng(42 + i) # เปลี่ยน seed ตามงวดเพื่อความหลากหลาย
        neg_count = 0
        while neg_count < 2: # สุ่มเลขลบมา 2 ตัวต่องวดเพื่อ Balance
            rand_num = int(rng.integers(0, 1000))
            rand_num_str = str(rand_num).zfill(3)
            if rand_num_str != num: # ต้องไม่ใช่เลขที่ออกรางวัลในงวดนี้
                feat_neg = extract_features(rand_num, ctx_series, ctx_dates, month)
                X.append(vectorize(feat_neg))
                y.append(0)
                neg_count += 1

    return np.array(X), np.array(y)

# ----------------------------------------------------------------------------
# ensemble bundle
# ----------------------------------------------------------------------------
class EnsembleBundle:
    def __init__(self):
        self.scaler = StandardScaler()
        self.lr = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
        self.rf = RandomForestClassifier(
            n_estimators=200, max_depth=8, max_features=0.6,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        self.gb = GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.08, max_depth=3, random_state=42,
        )
        self.weights = {"lr": 0.25, "rf": 0.40, "gb": 0.35}
        self.feature_names = FEATURE_NAMES
        self.trained_at: str | None = None
        self.metrics: Dict = {}

    def fit(self, X: np.ndarray, y: np.ndarray):
        Xs = self.scaler.fit_transform(X)
        self.lr.fit(Xs, y)
        self.rf.fit(Xs, y)
        self.gb.fit(Xs, y)
        self.trained_at = datetime.utcnow().isoformat()

    def _proba(self, model, Xs):
        return model.predict_proba(Xs)[:, 1]

    def predict_proba_all(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        Xs = self.scaler.transform(X)
        return {
            "lr": self._proba(self.lr, Xs),
            "rf": self._proba(self.rf, Xs),
            "gb": self._proba(self.gb, Xs),
        }

    def predict_ensemble(self, X: np.ndarray) -> np.ndarray:
        p = self.predict_proba_all(X)
        return (self.weights["lr"] * p["lr"]
                + self.weights["rf"] * p["rf"]
                + self.weights["gb"] * p["gb"])

    def feature_importance(self) -> Dict[str, float]:
        # blend RF + GB impurity importance with |LR coef|
        rf_imp = self.rf.feature_importances_
        gb_imp = self.gb.feature_importances_
        lr_imp = np.abs(self.lr.coef_[0])
        lr_imp = lr_imp / (lr_imp.sum() or 1)
        blend = (self.weights["rf"] * rf_imp
                 + self.weights["gb"] * gb_imp
                 + self.weights["lr"] * lr_imp)
        blend = blend / (blend.sum() or 1)
        return dict(sorted(zip(self.feature_names, blend.tolist()),
                           key=lambda kv: kv[1], reverse=True))


# ----------------------------------------------------------------------------
# rolling-window backtest + weight optimization
# ----------------------------------------------------------------------------
def rolling_backtest(draws: List[Dict]) -> Dict:
    series = [d["back3"] for d in draws]
    dates = [d["date"] for d in draws]
    n = len(series)
    splits = [0.60, 0.70, 0.80]
    results = []
    tot_lr = tot_rf = tot_gb = 0

    for frac in splits:
        cut = int(n * frac)
        train = draws[:cut]
        test_nums = series[cut:]
        if len(train) < 20 or not test_nums:
            continue

        X, y = build_training_data(train)
        if len(set(y)) < 2:
            continue
        bundle = EnsembleBundle()
        bundle.fit(X, y)

        ctx_series, ctx_dates = series[:cut], dates[:cut]
        rows = np.array([vectorize(extract_features(i, ctx_series, ctx_dates))
                         for i in range(1000)])
        probs = bundle.predict_proba_all(rows)
        nums = [str(i).zfill(3) for i in range(1000)]

        def top_hits(score_arr, k):
            order = np.argsort(score_arr)[::-1][:k]
            top = {nums[i] for i in order}
            return sum(1 for t in test_nums if t in top)

        ens = (bundle.weights["lr"] * probs["lr"]
               + bundle.weights["rf"] * probs["rf"]
               + bundle.weights["gb"] * probs["gb"])
        lr_h = top_hits(probs["lr"], 20)
        rf_h = top_hits(probs["rf"], 20)
        gb_h = top_hits(probs["gb"], 20)
        tot_lr += lr_h; tot_rf += rf_h; tot_gb += gb_h

        results.append({
            "split": f"{int(frac*100)}/{int((1-frac)*100)}",
            "train_size": cut, "test_size": n - cut,
            "top1": top_hits(ens, 1), "top5": top_hits(ens, 5),
            "top10": top_hits(ens, 10), "top20": top_hits(ens, 20),
            "precision_at_20": round(top_hits(ens, 20) / 20 * 100, 1),
            "coverage": round(top_hits(ens, 20) / max(len(test_nums), 1) * 100, 1),
            "lr_hits": lr_h, "rf_hits": rf_h, "gb_hits": gb_h,
        })

    tot = tot_lr + tot_rf + tot_gb or 1
    optimized = {"lr": tot_lr / tot, "rf": tot_rf / tot, "gb": tot_gb / tot}
    return {"results": results, "optimized_weights": optimized}


# ----------------------------------------------------------------------------
# walk-forward backtest with a uniform-random baseline + significance test
# ----------------------------------------------------------------------------
def binom_p_value(observed: int, n: int, p: float) -> float:
    """One-sided P(Binomial(n, p) >= observed): probability of getting at least
    `observed` hits by pure chance. Small => the result is unlikely under random."""
    if n <= 0:
        return 1.0
    observed = max(0, min(observed, n))
    try:
        from scipy.stats import binom
        return float(binom.sf(observed - 1, n, p))
    except Exception:
        # normal approximation fallback (no scipy)
        import math as _m
        mean = n * p
        var = n * p * (1 - p) or 1e-9
        z = (observed - 0.5 - mean) / _m.sqrt(var)  # continuity correction
        return 0.5 * _m.erfc(z / _m.sqrt(2))


def summarize_walk_forward(hits: Dict[int, int], n_pred: int, space: int) -> Dict:
    """Turn raw per-k hit counts into a baseline-relative, significance-tested report.

    For a uniform-random draw, a fixed top-k list contains the winner with
    probability k/space, so the null model is Binomial(n_pred, k/space).
    """
    per_k = []
    for k in sorted(hits):
        h = hits[k]
        baseline_rate = k / space
        expected = n_pred * baseline_rate
        hit_rate = (h / n_pred) if n_pred else 0.0
        per_k.append({
            "k": k,
            "hits": h,
            "n_predictions": n_pred,
            "hit_rate_pct": round(hit_rate * 100, 2),
            "baseline_rate_pct": round(baseline_rate * 100, 2),
            "expected_hits": round(expected, 2),
            "lift": round(hit_rate / baseline_rate, 3) if baseline_rate else None,
            "p_value": round(binom_p_value(h, n_pred, baseline_rate), 4),
            "beats_random_p05": bool(binom_p_value(h, n_pred, baseline_rate) < 0.05),
        })
    return {"space": space, "n_predictions": n_pred, "by_k": per_k}


def _walk_forward_core(draws, series, dates, space, fit_fn, score_fn,
                       start_frac=0.6, retrain_every=10, ks=(1, 5, 10, 20)) -> Dict:
    """Expanding-window, one-step-ahead backtest.

    For each draw i (from start onward) the model is trained only on draws[:i]
    (refit every `retrain_every` steps to keep it tractable) and used to rank all
    `space` combinations; we record whether the actual winner landed in the top-k.
    Every prediction is strictly out-of-sample.
    """
    n = len(series)
    start = max(10, int(n * start_frac))
    hits = {k: 0 for k in ks}
    n_pred = 0
    model = None
    steps_since_fit = 0

    for i in range(start, n):
        if model is None or steps_since_fit >= retrain_every:
            model = fit_fn(draws[:i])
            steps_since_fit = 0
        steps_since_fit += 1
        if model is None:
            continue

        ctx_series, ctx_dates = series[:i], dates[:i]
        scores = score_fn(model, ctx_series, ctx_dates)
        order = np.argsort(scores)[::-1]
        winner = int(series[i])
        # rank of the winner (0-based); cheaper than building k sets
        winner_rank = int(np.where(order == winner)[0][0])
        for k in ks:
            if winner_rank < k:
                hits[k] += 1
        n_pred += 1

    report = summarize_walk_forward(hits, n_pred, space)
    report["start_index"] = start
    report["retrain_every"] = retrain_every
    return report


def _fit_ensemble(ctx_draws: List[Dict]) -> "EnsembleBundle | None":
    X, y = build_training_data(ctx_draws)
    if len(X) == 0 or len(set(y)) < 2:
        return None
    bundle = EnsembleBundle()  # default weights; no nested reweighting
    bundle.fit(X, y)
    return bundle


def walk_forward_backtest(draws: List[Dict], start_frac=0.6, retrain_every=10,
                          ks=(1, 5, 10, 20)) -> Dict:
    """Honest out-of-sample evaluation of the back3 ensemble vs a random baseline."""
    draws = sorted(draws, key=lambda d: d["date"])
    series = [d["back3"] for d in draws]
    dates = [d["date"] for d in draws]

    def score_fn(bundle, ctx_series, ctx_dates):
        rows = np.array([vectorize(extract_features(j, ctx_series, ctx_dates))
                         for j in range(1000)])
        return bundle.predict_ensemble(rows)

    return _walk_forward_core(draws, series, dates, 1000, _fit_ensemble, score_fn,
                              start_frac, retrain_every, ks)


# ----------------------------------------------------------------------------
# orchestration: train -> backtest -> reweight -> persist
# ----------------------------------------------------------------------------
def train_and_persist(draws: List[Dict]) -> EnsembleBundle:
    draws = sorted(draws, key=lambda d: d["date"])
    X, y = build_training_data(draws)
    bundle = EnsembleBundle()
    bundle.fit(X, y)

    bt = rolling_backtest(draws)
    if bt["results"]:
        bundle.weights = bt["optimized_weights"]
    bundle.metrics = bt

    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)
    return bundle


def load_bundle() -> EnsembleBundle | None:
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)
