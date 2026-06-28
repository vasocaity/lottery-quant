const API = import.meta.env.VITE_API_URL ?? 'http://localhost:3001/api';

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface Draw { id: number; date: string; back3: string; last2?: string; }
export interface PredictItem {
  rank: number; number: string; score: number;
  lr_score: number; rf_score: number; gb_score: number;
  confidence: string;
  top_features: Array<{ name: string; value: number; importance: number }>;
}

export const api = {
  listDraws: () => req<Draw[]>('/draws'),
  addDraw: (d: { date: string; back3: string; last2?: string }) =>
    req<Draw>('/draws', { method: 'POST', body: JSON.stringify(d) }),
  trainModel: () => req('/predictions/train', { method: 'POST' }),
  runPrediction: (topN = 20) =>
    req<{ id: number; items: PredictItem[] }>(`/predictions/run?topN=${topN}`, { method: 'POST' }),
  backtest: () => req<{ results: any[]; optimized_weights: any }>('/predictions/backtest'),
  featureImportance: () =>
    req<{ importances: Record<string, number>; weights: any }>('/predictions/feature-importance'),
  latest: () => req<{ items: PredictItem[] } | null>('/predictions/latest'),
};
