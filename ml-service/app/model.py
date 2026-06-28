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
def build_training_data(draws: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
    """draws: list of {date, back3} sorted oldest->newest.
    Positive = a number that actually appeared (features as of just before it
    appeared). Negative = numbers that never appeared + random hard negatives.
    """
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
        feat = extract_features(int(num), ctx_series, ctx_dates, month)
        X.append(vectorize(feat))
        y.append(1)

    # negatives: never appeared
    for i in range(1000):
        ns = str(i).zfill(3)
        if ns not in appeared:
            feat = extract_features(i, series, dates)
            X.append(vectorize(feat))
            y.append(0)

    # hard negatives: random non-winners (balances class ratio a bit)
    rng = np.random.default_rng(42)
    for _ in range(len(appeared) * 2):
        n = int(rng.integers(0, 1000))
        if str(n).zfill(3) not in appeared:
            feat = extract_features(n, series, dates)
            X.append(vectorize(feat))
            y.append(0)

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
