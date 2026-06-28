"""
FastAPI ML microservice.

Endpoints (called by the NestJS backend, never directly by the browser):
  GET  /health                  -> liveness
  POST /train                   -> train ensemble on supplied draws, persist .pkl
  POST /predict                 -> score all 1000 combos, return ranked top-N
  POST /backtest                -> rolling-window validation report
  GET  /feature-importance      -> global importances from the persisted model
  GET  /model-info              -> metadata about the persisted model
"""
from __future__ import annotations
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .features import extract_features, vectorize
from .model import (
    train_and_persist, load_bundle, rolling_backtest, MODEL_PATH,
)

app = FastAPI(title="Thai Lottery ML Service", version="1.0.0")


# ----------------------------- schemas -----------------------------
class Draw(BaseModel):
    date: str = Field(..., examples=["2026-06-26"])
    back3: str = Field(..., examples=["523"])


class TrainRequest(BaseModel):
    draws: List[Draw]


class PredictRequest(BaseModel):
    draws: List[Draw]
    top_n: int = 20


class PredictItem(BaseModel):
    rank: int
    number: str
    score: float
    lr_score: float
    rf_score: float
    gb_score: float
    confidence: str
    top_features: List[dict]


# ----------------------------- helpers -----------------------------
def _confidence(score: float) -> str:
    if score >= 0.65:
        return "Medium-High"
    if score >= 0.50:
        return "Medium"
    return "Low-Medium"


def _require_bundle():
    bundle = load_bundle()
    if bundle is None:
        raise HTTPException(503, "No trained model. Call /train first.")
    return bundle


# ----------------------------- routes ------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "model_present": load_bundle() is not None}


@app.post("/train")
def train(req: TrainRequest):
    draws = [d.model_dump() for d in req.draws]
    if len(draws) < 20:
        raise HTTPException(400, "Need at least 20 draws to train.")
    bundle = train_and_persist(draws)
    return {
        "status": "trained",
        "trained_at": bundle.trained_at,
        "weights": bundle.weights,
        "n_draws": len(draws),
        "metrics": bundle.metrics,
        "artifact": MODEL_PATH,
    }


@app.post("/predict", response_model=List[PredictItem])
def predict(req: PredictRequest):
    bundle = _require_bundle()
    draws = sorted([d.model_dump() for d in req.draws], key=lambda d: d["date"])
    series = [d["back3"] for d in draws]
    dates = [d["date"] for d in draws]

    rows = np.array([vectorize(extract_features(i, series, dates)) for i in range(1000)])
    probs = bundle.predict_proba_all(rows)
    ens = bundle.predict_ensemble(rows)

    global_imp = bundle.feature_importance()
    top_feat_names = list(global_imp.keys())[:6]

    order = np.argsort(ens)[::-1][: req.top_n]
    out: List[PredictItem] = []
    for rank, idx in enumerate(order, start=1):
        num = str(idx).zfill(3)
        feat = extract_features(idx, series, dates)
        contributions = sorted(
            ({"name": fn, "value": round(feat[fn], 4),
              "importance": round(global_imp[fn], 4)} for fn in top_feat_names),
            key=lambda c: c["importance"], reverse=True,
        )
        out.append(PredictItem(
            rank=rank, number=num, score=round(float(ens[idx]), 4),
            lr_score=round(float(probs["lr"][idx]), 4),
            rf_score=round(float(probs["rf"][idx]), 4),
            gb_score=round(float(probs["gb"][idx]), 4),
            confidence=_confidence(float(ens[idx])),
            top_features=contributions,
        ))
    return out


@app.post("/backtest")
def backtest(req: TrainRequest):
    draws = sorted([d.model_dump() for d in req.draws], key=lambda d: d["date"])
    if len(draws) < 30:
        raise HTTPException(400, "Need at least 30 draws to backtest.")
    return rolling_backtest(draws)


@app.get("/feature-importance")
def feature_importance():
    bundle = _require_bundle()
    imp = bundle.feature_importance()
    return {"importances": imp, "weights": bundle.weights}


@app.get("/model-info")
def model_info():
    bundle = _require_bundle()
    return {
        "trained_at": bundle.trained_at,
        "weights": bundle.weights,
        "n_features": len(bundle.feature_names),
        "feature_names": bundle.feature_names,
        "metrics": bundle.metrics,
    }
