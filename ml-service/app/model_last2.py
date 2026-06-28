"""
Trains a RandomForest model for Thai Lottery 2-digit (last2) prediction.
"""
from __future__ import annotations
import os
import pickle
from datetime import datetime
from typing import List, Dict, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from .features_2d import extract_features_2d, vectorize_2d, FEATURE_NAMES_2D

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
LAST2_MODEL_PATH = os.path.join(MODEL_DIR, "last2.pkl")


NEG_PER_DRAW = 8

def build_training_data_2d(draws: List[Dict], neg_per_draw: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """Point-in-time training data for the 2-digit model.

    For each draw i: the actual winner is a positive, and neg_per_draw random
    non-winners scored against the SAME context (series[:i]) are negatives.
    This works even when every 2-digit value has appeared at least once.
    """
    series = [d["last2"] for d in draws if d.get("last2")]
    dates = [d["date"] for d in draws if d.get("last2")]
    X, y = [], []

    if len(series) < 10:
        return np.array([]), np.array([])

    rng = np.random.default_rng(42)
    for i in range(5, len(series)):
        ctx_series = series[:i]
        ctx_dates = dates[:i]
        month = datetime.fromisoformat(dates[i]).month
        winner = series[i]

        # จุดที่ 1: ตรวจสอบและส่ง Argument ให้ตรงกับที่ฟังก์ชัน extract_features_2d ประกาศไว้
        # (อ้างอิงจากบรรทัดการเรียกในอดีต ฟังก์ชันต้องการค่า int(winner), ctx_series, ctx_dates, month)
        feat = extract_features_2d(int(winner), ctx_series, ctx_dates, month)
        X.append(vectorize_2d(feat))
        y.append(1)

        added = 0
        # จุดที่ 2: เปลี่ยน NEG_PER_DRAW เป็น neg_per_draw (ตัวพิมพ์เล็ก) ตามที่รับมาใน Parameter
        while added < neg_per_draw:
            n = int(rng.integers(0, 100))
            if str(n).zfill(2) == winner:
                continue
            # ส่ง Argument ให้สอดคล้องกันฝั่งลบด้วยเช่นกัน
            feat = extract_features_2d(n, ctx_series, ctx_dates, month)
            X.append(vectorize_2d(feat))
            y.append(0)
            added += 1

    return np.array(X), np.array(y)


class Last2Bundle:
    def __init__(self):
        self.scaler = StandardScaler()
        self.rf = RandomForestClassifier(
            n_estimators=200, max_depth=8, max_features=0.6,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        self.feature_names = FEATURE_NAMES_2D
        self.trained_at: str | None = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        Xs = self.scaler.fit_transform(X)
        self.rf.fit(Xs, y)
        self.trained_at = datetime.utcnow().isoformat()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xs = self.scaler.transform(X)
        return self.rf.predict_proba(Xs)[:, 1]


def train_last2(draws: List[Dict]) -> Last2Bundle | None:
    draws = sorted(draws, key=lambda d: d["date"])
    X, y = build_training_data_2d(draws)
    if len(X) == 0 or len(set(y)) < 2:
        return None
    bundle = Last2Bundle()
    bundle.fit(X, y)
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(LAST2_MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)
    return bundle


def _fit_last2(ctx_draws: List[Dict]) -> Last2Bundle | None:
    X, y = build_training_data_2d(ctx_draws)
    if len(X) == 0 or len(set(y)) < 2:
        return None
    bundle = Last2Bundle()
    bundle.fit(X, y)
    return bundle


def walk_forward_last2(draws: List[Dict], start_frac=0.6, retrain_every=10,
                       ks=(1, 5, 10, 20)) -> Dict:
    """Honest out-of-sample evaluation of the last2 model vs a random baseline."""
    from .model import _walk_forward_core

    draws = sorted(draws, key=lambda d: d["date"])
    draws = [d for d in draws if d.get("last2")]
    series = [d["last2"] for d in draws]
    dates = [d["date"] for d in draws]

    def score_fn(bundle, ctx_series, ctx_dates):
        rows = np.array([vectorize_2d(extract_features_2d(j, ctx_series, ctx_dates))
                         for j in range(100)])
        return bundle.predict_proba(rows)

    return _walk_forward_core(draws, series, dates, 100, _fit_last2, score_fn,
                              start_frac, retrain_every, ks)


def load_last2() -> Last2Bundle | None:
    if not os.path.exists(LAST2_MODEL_PATH):
        return None
    try:
        with open(LAST2_MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        if len(bundle.feature_names) != len(FEATURE_NAMES_2D):
            os.remove(LAST2_MODEL_PATH)
            return None
        return bundle
    except Exception:
        return None
