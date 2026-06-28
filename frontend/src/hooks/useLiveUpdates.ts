import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import type { PredictItem } from '../api/client';

const WS = import.meta.env.VITE_WS_URL ?? 'http://localhost:3001/live';

export interface Progress { step: string; pct: number; }

/** Subscribes to live training progress + new predictions via socket.io. */
export function useLiveUpdates() {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [livePrediction, setLivePrediction] = useState<PredictItem[] | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket: Socket = io(WS, { transports: ['websocket'] });
    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    socket.on('training:progress', (p: Progress) => setProgress(p));
    socket.on('prediction:new', (items: PredictItem[]) => setLivePrediction(items));
    socket.on('model:trained', () => setProgress({ step: 'Model trained', pct: 100 }));
    return () => { socket.disconnect(); };
  }, []);

  return { progress, livePrediction, connected };
}
