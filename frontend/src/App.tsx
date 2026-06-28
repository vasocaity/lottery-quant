import { useEffect, useState, useCallback } from "react";
import { api, type Draw, type PredictItem } from "./api/client";
import { useLiveUpdates } from "./hooks/useLiveUpdates";

/**
 * Frontend is now a THIN client.
 * - No ML math here. All scoring happens in the Python service.
 * - Data comes from PostgreSQL via the NestJS REST API.
 * - Live training progress + new predictions arrive over WebSocket.
 */
export default function App() {
  const [draws, setDraws] = useState<Draw[]>([]);
  const [top20, setTop20] = useState<PredictItem[]>([]);
  const [tab, setTab] = useState("rankings");
  const [busy, setBusy] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<any>(null);
  const [weights, setWeights] = useState({ lr: 0.25, rf: 0.4, gb: 0.35 });
  const [newDraw, setNewDraw] = useState({ date: "", back3: "", last2: "" });

  const { progress, livePrediction, connected } = useLiveUpdates();

  // Live prediction pushed over WS overrides local state
  useEffect(() => {
    if (livePrediction) setTop20(livePrediction);
  }, [livePrediction]);

  const loadDraws = useCallback(async () => {
    setDraws(await api.listDraws());
  }, []);

  const loadLatest = useCallback(async () => {
    const latest = await api.latest();
    if (latest?.items) setTop20(latest.items);
  }, []);

  useEffect(() => {
    loadDraws();
    loadLatest();
  }, [loadDraws, loadLatest]);

  const handleTrain = async () => {
    setBusy("Training models...");
    await api.trainModel();
    const res = await api.runPrediction(20);
    setTop20(res.items);
    const fi = await api.featureImportance();
    setWeights(fi.weights);
    setBusy(null);
  };

  const handleBacktest = async () => {
    setBusy("Running backtest...");
    const res = await api.backtest();
    setBacktest(res);
    setWeights(res.optimized_weights);
    setBusy(null);
  };

  const handleAddDraw = async () => {
    if (!newDraw.date || !newDraw.back3) return;
    setBusy("Adding draw + retraining...");
    await api.addDraw(newDraw);
    await loadDraws();
    // adding a draw triggers retrain server-side; refresh predictions
    await api.trainModel();
    const res = await api.runPrediction(20);
    setTop20(res.items);
    setNewDraw({ date: "", back3: "", last2: "" });
    setBusy(null);
  };

  const sc = (s: number) => (s >= 0.65 ? "#00ff88" : s >= 0.5 ? "#ffcc00" : "#ff9f43");
  const pct = (s: number) => (s * 100).toFixed(1);
  const last = draws[draws.length - 1];

  return (
    <div style={{ background: "#050a14", minHeight: "100vh", color: "#e0e8ff", fontFamily: "'Courier New',monospace" }}>
      <header style={{ background: "linear-gradient(135deg,#060e1e,#0a1830,#060e1e)", borderBottom: "1px solid #1a3a6b", padding: "16px 24px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: connected ? "#00ff88" : "#ff6b6b", boxShadow: `0 0 8px ${connected ? "#00ff88" : "#ff6b6b"}` }} />
            <span style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 3, textTransform: "uppercase" }}>
              React → NestJS → {`{PostgreSQL, Python ML}`} • WS {connected ? "live" : "offline"}
            </span>
          </div>
          <h1 style={{ margin: "4px 0", fontSize: 20, fontWeight: 700, color: "#fff" }}>🎯 Thai Lottery Quant Platform</h1>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 11, color: "#6a8ab8" }}>
            <span>Latest: <b style={{ color: "#ffcc00" }}>{last?.back3 ?? "—"}</b> {last?.date}</span>
            <span>{draws.length} draws in DB</span>
            <span>Ensemble: LR {pct(weights.lr)}% · RF {pct(weights.rf)}% · GB {pct(weights.gb)}%</span>
          </div>
        </div>
      </header>

      {(busy || progress) && (
        <div style={{ background: "#0a1628", borderBottom: "1px solid #1a3a6b", padding: "8px 24px" }}>
          <div style={{ maxWidth: 1100, margin: "0 auto" }}>
            <div style={{ color: "#ffcc00", fontSize: 11 }}>⚙️ {progress?.step ?? busy}</div>
            {progress && (
              <div style={{ background: "#050d1a", borderRadius: 3, height: 5, marginTop: 4, overflow: "hidden" }}>
                <div style={{ background: "linear-gradient(90deg,#4a9eff,#00ff88)", height: "100%", width: `${progress.pct}%`, transition: "width 0.3s" }} />
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "16px 24px" }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          <button onClick={handleTrain} style={btn("#00ff88")}>⚡ Train + Predict</button>
          <button onClick={handleBacktest} style={btn("#4a9eff")}>📈 Backtest + Optimize</button>
        </div>

        <nav style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid #1a3a6b" }}>
          {["rankings", "backtest", "history", "adddata"].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={tabBtn(tab === t)}>
              {{ rankings: "📊 Rankings", backtest: "📈 Backtest", history: "📋 History", adddata: "➕ Add Draw" }[t]}
            </button>
          ))}
        </nav>

        {tab === "rankings" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
            {top20.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>No predictions yet — click "Train + Predict".</div>}
            {top20.map((item, idx) => (
              <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 26, fontWeight: 900, color: sc(item.score), letterSpacing: 3 }}>{item.number}</span>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
                    <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
                  </div>
                </div>
                <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, marginTop: 8 }}>
                  {[["LR", item.lr_score], ["RF", item.rf_score], ["GB", item.gb_score]].map(([l, v]) => (
                    <div key={l as string} style={{ background: "#050d1a", borderRadius: 4, padding: "3px 0", textAlign: "center" }}>
                      <div style={{ color: "#6a8ab8", fontSize: 8 }}>{l}</div>
                      <div style={{ color: sc(v as number), fontSize: 11, fontWeight: 700 }}>{pct(v as number)}</div>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 8 }}>
                  {item.top_features.slice(0, 3).map((f) => (
                    <div key={f.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#6a8ab8" }}>
                      <span>▸ {f.name.replace("f_", "")}</span>
                      <span style={{ color: "#4a9eff" }}>{(f.importance * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "backtest" && (
          <div>
            {!backtest && <div style={{ color: "#6a8ab8", fontSize: 12 }}>Click "Backtest + Optimize" above.</div>}
            {backtest?.results?.map((r: any, i: number) => (
              <div key={i} style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10, padding: 14, marginBottom: 10 }}>
                <div style={{ color: "#4a9eff", fontWeight: 700, marginBottom: 8 }}>Split {r.split}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(110px,1fr))", gap: 8 }}>
                  {[["Train", r.train_size], ["Test", r.test_size], ["Top-1", r.top1], ["Top-5", r.top5], ["Top-10", r.top10], ["Top-20", r.top20], ["Prec@20", r.precision_at_20 + "%"], ["Coverage", r.coverage + "%"]].map(([l, v]) => (
                    <div key={l as string} style={{ background: "#050d1a", borderRadius: 6, padding: "6px 10px" }}>
                      <div style={{ color: "#6a8ab8", fontSize: 9 }}>{l}</div>
                      <div style={{ color: "#00ff88", fontSize: 16, fontWeight: 700 }}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "history" && (
          <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10, maxHeight: 520, overflowY: "auto" }}>
            {[...draws].reverse().map((d, i) => (
              <div key={d.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", padding: "6px 14px", fontSize: 11, borderTop: "1px solid #0d1f3c" }}>
                <span style={{ color: i === 0 ? "#00ff88" : "#6a8ab8" }}>{d.date?.slice(0, 10)}</span>
                <span style={{ fontWeight: 700, letterSpacing: 3, color: i === 0 ? "#ffcc00" : "#e0e8ff" }}>{d.back3}</span>
                <span style={{ color: "#6a8ab8" }}>{d.last2}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "adddata" && (
          <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10, padding: 14, maxWidth: 480 }}>
            <div style={{ display: "grid", gap: 10, marginBottom: 10 }}>
              <input type="date" value={newDraw.date} onChange={(e) => setNewDraw({ ...newDraw, date: e.target.value })} style={inp} />
              <input placeholder="3-digit (e.g. 523)" value={newDraw.back3} onChange={(e) => setNewDraw({ ...newDraw, back3: e.target.value })} style={inp} />
              <input placeholder="2-digit (e.g. 30)" value={newDraw.last2} onChange={(e) => setNewDraw({ ...newDraw, last2: e.target.value })} style={inp} />
            </div>
            <button onClick={handleAddDraw} style={btn("#00ff88")}>✓ Add & Retrain</button>
          </div>
        )}
      </div>
    </div>
  );
}

const btn = (c: string): React.CSSProperties => ({
  background: "#0d2444", border: `1px solid ${c}`, color: c, borderRadius: 6,
  padding: "7px 16px", cursor: "pointer", fontSize: 12, fontFamily: "inherit",
});
const tabBtn = (active: boolean): React.CSSProperties => ({
  background: active ? "#0d2444" : "transparent", border: "none",
  borderBottom: active ? "2px solid #4a9eff" : "2px solid transparent",
  color: active ? "#4a9eff" : "#6a8ab8", padding: "6px 12px",
  cursor: "pointer", fontSize: 11, fontFamily: "inherit", marginBottom: -1,
});
const inp: React.CSSProperties = {
  background: "#050d1a", border: "1px solid #1a3a6b", borderRadius: 5,
  color: "#e0e8ff", padding: "6px 10px", fontSize: 12, fontFamily: "inherit",
};
