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
export interface Last2Item {
  rank: number; number: string; score: number; confidence: string;
}
export interface HitRateStat {
  evaluated: number; hits: number; hitRate: number | null;
  expectedRate: number; expectedHits: number;
}
export interface HitRateReport { last2: HitRateStat; back3: HitRateStat; }
export interface PredictionHistoryItem {
  id: number;
  createdAt: string;
  modelVersionId: number;
  back3Items: PredictItem[];
  last2Items: Last2Item[];
  target: { date: string; back3: string; last2: string | null } | null;
  back3Hit: boolean | null;
  last2Hit: boolean | null;
}

export const api = {
  listDraws: () => req<Draw[]>('/draws'),
  addDraw: (d: { date: string; back3: string; last2?: string; firstPrize?: string }) =>
    req<Draw>('/draws', { method: 'POST', body: JSON.stringify(d) }),
  trainModel: () => req('/predictions/train', { method: 'POST' }),
  runPrediction: (topN = 20) =>
    req<{ id: number; items: PredictItem[]; last2_items: Last2Item[] }>(`/predictions/run?topN=${topN}`, { method: 'POST' }),
  backtest: () => req<{ results: any[]; optimized_weights: any }>('/predictions/backtest'),
  featureImportance: () =>
    req<{ importances: Record<string, number>; weights: any }>('/predictions/feature-importance'),
  latest: () => req<{ id: number; items: PredictItem[]; last2_items: Last2Item[] } | null>('/predictions/latest'),
  hitRate: () => req<HitRateReport>('/predictions/hit-rate'),
  predictionHistory: (limit = 30) => req<PredictionHistoryItem[]>(`/predictions/history?limit=${limit}`),
};
