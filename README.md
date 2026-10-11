# 🎯 Thai Lottery Quant Platform

> **⚠️ Experiment only.** This is a personal experiment / learning project. It is not
> financial, investment, or gambling advice, and it makes no guarantee of any outcome.

A production-architecture quantitative analysis system for Thai Government Lottery
3-digit (back-3) statistical ranking. **This is a statistical ranking tool, not a
prediction system — lottery draws are random events.**

## Architecture

```
                React (Vite + TS)
                      │
            REST API  +  WebSocket
                      │
              NestJS Backend
          ┌───────────┴───────────┐
          │                       │
     PostgreSQL            Python ML Service
     (Prisma ORM)            (FastAPI + sklearn)
          │                       │
          └───────────┬───────────┘
                      │
              Trained Model (ensemble.pkl)
```

Each layer has one job:

| Layer | Tech | Responsibility |
|-------|------|----------------|
| **Frontend** | React + Vite + socket.io-client | Thin client. Renders rankings, streams live progress. No ML math. |
| **Backend** | NestJS + Prisma + socket.io | Orchestration. Owns DB, calls ML service, broadcasts over WS. |
| **Database** | PostgreSQL | Stores draws, model versions, persisted predictions. |
| **ML Service** | FastAPI + scikit-learn | Trains LR + RF + GB ensemble, backtests, persists `.pkl`, scores. |

## The Models

The ensemble (in `ml-service/app/model.py`) combines three real scikit-learn models:

- **Logistic Regression** — `LogisticRegression(class_weight="balanced")`, linear baseline
- **Random Forest** — `RandomForestClassifier(n_estimators=200, max_depth=8)`, bagging
- **Gradient Boosting** — `GradientBoostingClassifier(n_estimators=150, lr=0.08)`, boosting

**38 engineered features** across 8 categories (frequency, gap, pair, transition/Markov,
pattern, sum, statistical, Bayesian/time) defined in `ml-service/app/features.py`.

Ensemble weights are **auto-optimized by rolling-window backtest** — each model's
top-20 hit rate across 60/40, 70/30, 80/20 splits determines its weight. The whole
bundle (scaler + 3 models + weights + metrics) is pickled to `ensemble.pkl`.

## Data flow: training

```
POST /api/predictions/train
  → NestJS pulls all draws from PostgreSQL
  → POSTs them to Python /train
  → Python builds training data, fits LR+RF+GB, runs backtest,
    optimizes weights, pickles ensemble.pkl
  → NestJS records a ModelVersion row, broadcasts model:trained over WS
```

## Data flow: self-improvement loop

```
POST /api/draws  (new official result)
  → DrawsService upserts into PostgreSQL
  → triggers PredictionsService.onNewDraw()
      → retrain → re-predict → broadcast prediction:new over WS
  → React updates rankings live, no refresh
```

## Quick start

```bash
# One command brings up all four services
docker compose up --build

# Then seed the database with real 2022–2026 data
docker compose exec backend npx prisma migrate deploy
docker compose exec backend npm run db:seed

# Train the first model
curl -X POST http://localhost:3001/api/predictions/train
curl -X POST http://localhost:3001/api/predictions/run

# Open the UI
open http://localhost:5173
```

## API reference (NestJS, prefix `/api`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/draws` | List all draws |
| POST | `/draws` | Add a draw (auto-retrains) |
| POST | `/draws/import` | Bulk import |
| POST | `/predictions/train` | Train ensemble, persist `.pkl` |
| POST | `/predictions/run?topN=20` | Score all 1000, return ranked top-N |
| GET | `/predictions/backtest` | Rolling-window validation report |
| GET | `/predictions/feature-importance` | Global feature importances |
| GET | `/predictions/latest` | Most recent persisted prediction |
| GET | `/predictions/history?limit=30` | Past prediction runs (newest first) with hit/miss/pending outcome |

WebSocket namespace `/live` emits: `training:progress`, `model:trained`, `prediction:new`.

## ML Service reference (FastAPI, internal :8000)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + model presence |
| POST | `/train` | Train + persist `ensemble.pkl` |
| POST | `/predict` | Score 1000 combos |
| POST | `/backtest` | Rolling-window backtest |
| GET | `/feature-importance` | Importances from persisted model |
| GET | `/model-info` | Model metadata |

## Project layout

```
thai-lottery-quant/
├── docker-compose.yml          # ties all 4 services together
├── frontend/                   # React + Vite
│   └── src/
│       ├── App.tsx             # thin client UI
│       ├── api/client.ts       # REST client
│       └── hooks/useLiveUpdates.ts  # socket.io subscription
├── backend/                    # NestJS
│   ├── prisma/
│   │   ├── schema.prisma       # PostgreSQL schema
│   │   └── seed.ts             # 234 real draws 2022–2026
│   └── src/
│       ├── draws/              # PostgreSQL CRUD
│       ├── predictions/        # orchestration pipeline
│       ├── ml/                 # HTTP client to Python service
│       └── websocket/          # live updates gateway
└── ml-service/                 # FastAPI + scikit-learn
    └── app/
        ├── features.py         # 38-feature engineering
        ├── model.py            # LR+RF+GB ensemble + backtest + pickle
        └── main.py             # FastAPI endpoints
```

## ⚠️ Disclaimer

Lottery draws are independent random events. Historical patterns are not causal and
provide no predictive certainty. Backtest "coverage" above the ~2% random baseline
reflects statistical fit on past data only. This software is for educational and
analytical purposes — **an experiment only**, never a basis for financial decisions.
