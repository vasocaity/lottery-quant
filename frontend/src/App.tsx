import { useEffect, useState, useCallback } from "react";
import { api, type Draw, type PredictItem, type Last2Item, type HitRateReport, type PredictionHistoryItem } from "./api/client";
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
  const [last2Top10, setLast2Top10] = useState<Last2Item[]>([]);
  const [tab, setTab] = useState("rankings");
  const [rankingMode, setRankingMode] = useState<"back3" | "last2">("last2");
  const [hitRate, setHitRate] = useState<HitRateReport | null>(null);
  const [predHistory, setPredHistory] = useState<PredictionHistoryItem[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<any>(null);
  const [weights, setWeights] = useState({ lr: 0.25, rf: 0.4, gb: 0.35 });
  const [newDraw, setNewDraw] = useState({ date: "", back3: "", last2: "", firstPrize: "" });

  const { progress, livePrediction, connected } = useLiveUpdates();

  // Live prediction pushed over WS overrides local state
  useEffect(() => {
    if (livePrediction) {
      setTop20(livePrediction.back3_items ?? []);
      setLast2Top10(livePrediction.last2_items ?? []);
    }
  }, [livePrediction]);

  const loadDraws = useCallback(async () => {
    setDraws(await api.listDraws());
  }, []);

  const loadLatest = useCallback(async () => {
    const latest = await api.latest();
    if (latest?.items) setTop20(latest.items);
    if (latest?.last2_items) setLast2Top10(latest.last2_items);
  }, []);

  const loadHitRate = useCallback(async () => {
    try { setHitRate(await api.hitRate()); } catch { /* backend may be older */ }
  }, []);

  const loadPredictionHistory = useCallback(async () => {
    setPredHistory(await api.predictionHistory());
  }, []);

  useEffect(() => {
    loadDraws();
    loadLatest();
    loadHitRate();
    loadPredictionHistory();
  }, [loadDraws, loadLatest, loadHitRate, loadPredictionHistory]);

  const handleTrain = async () => {
    setBusy("Training models...");
    await api.trainModel();
    const res = await api.runPrediction(20);
    setTop20(res.items);
    setLast2Top10(res.last2_items ?? []);
    const fi = await api.featureImportance();
    setWeights(fi.weights);
    await loadHitRate();
    await loadPredictionHistory();
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
    await api.addDraw({ ...newDraw, firstPrize: newDraw.firstPrize || undefined });
    await loadDraws();
    await api.trainModel();
    const res = await api.runPrediction(20);
    setTop20(res.items);
    setLast2Top10(res.last2_items ?? []);
    setNewDraw({ date: "", back3: "", last2: "", firstPrize: "" });
    await loadHitRate();
    await loadPredictionHistory();
    setBusy(null);
  };

  const sc = (s: number) => (s >= 0.65 ? "#00ff88" : s >= 0.5 ? "#ffcc00" : "#ff9f43");
  const pct = (s: number) => (s * 100).toFixed(1);
  const last = draws[draws.length - 1];

  const renderBack3Grid = (items: PredictItem[], emptyMsg = "No 3-digit predictions yet.") => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
      {items.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>{emptyMsg}</div>}
      {items.map((item, idx) => (
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
  );

  const renderLast2Grid = (items: Last2Item[], emptyMsg = "No 2-digit predictions yet.") => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))", gap: 10 }}>
      {items.length === 0 && <div style={{ color: "#6a8ab8", fontSize: 12 }}>{emptyMsg}</div>}
      {items.map((item, idx) => (
        <div key={item.number} style={{ background: "#0a1628", border: `1px solid ${idx < 3 ? "#2a5a8b" : "#1a3a6b"}`, borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 32, fontWeight: 900, color: sc(item.score), letterSpacing: 4 }}>{item.number}</span>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: sc(item.score), fontWeight: 700 }}>{pct(item.score)}</div>
              <div style={{ fontSize: 8, color: "#6a8ab8" }}>/100</div>
            </div>
          </div>
          <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 9, color: "#4a9eff" }}>{item.confidence}</span>
            <span style={{ fontSize: 9, color: "#6a8ab8" }}>#{item.rank}</span>
          </div>
        </div>
      ))}
    </div>
  );

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
            <span>Latest: 2D <b style={{ color: "#ffcc00" }}>{last?.last2 ?? "—"}</b> · 3D <b style={{ color: "#ffcc00" }}>{last?.back3 ?? "—"}</b> {last?.date?.slice(0, 10)}</span>
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
          {["rankings", "backtest", "history", "predhistory", "adddata"].map((t) => (
            <button key={t} onClick={() => setTab(t)} style={tabBtn(tab === t)}>
              {{ rankings: "📊 Rankings", backtest: "📈 Backtest", history: "📋 History", predhistory: "🕘 Prediction History", adddata: "➕ Add Draw" }[t]}
            </button>
          ))}
        </nav>

        {tab === "rankings" && (
          <div>
            {hitRate && (
              <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10, padding: "12px 14px", marginBottom: 14 }}>
                <div style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>
                  🎯 Scoreboard — actual hits vs pure chance
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10 }}>
                  {([["2-Digit top-10", hitRate.last2], ["3-Digit top-20", hitRate.back3]] as const).map(([label, s]) => (
                    <div key={label} style={{ background: "#050d1a", borderRadius: 6, padding: "8px 12px" }}>
                      <div style={{ color: "#6a8ab8", fontSize: 9 }}>{label}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: s.hits > s.expectedHits ? "#00ff88" : "#e0e8ff" }}>
                        {s.hits} hit{s.hits === 1 ? "" : "s"} / {s.evaluated} draws
                        <span style={{ color: "#6a8ab8", fontWeight: 400, fontSize: 11 }}>
                          {" "}({s.hitRate != null ? (s.hitRate * 100).toFixed(1) : "—"}%)
                        </span>
                      </div>
                      <div style={{ color: "#6a8ab8", fontSize: 9 }}>
                        chance would give ~{s.expectedHits} ({(s.expectedRate * 100).toFixed(0)}%)
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ color: "#6a8ab8", fontSize: 9, marginTop: 8 }}>
                  ⚠ Hits at or near the chance line mean the model has no edge — the walk-forward backtest confirms draws are random. Treat this as a tracked experiment, not investment advice.
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              {(["last2", "back3"] as const).map((mode) => (
                <button key={mode} onClick={() => setRankingMode(mode)} style={{
                  background: rankingMode === mode ? "#0d2444" : "transparent",
                  border: `1px solid ${rankingMode === mode ? "#4a9eff" : "#1a3a6b"}`,
                  color: rankingMode === mode ? "#4a9eff" : "#6a8ab8",
                  borderRadius: 5, padding: "4px 12px", cursor: "pointer",
                  fontSize: 11, fontFamily: "inherit",
                }}>
                  {mode === "back3" ? "3-Digit (back3)" : "★ 2-Digit (last2)"}
                </button>
              ))}
            </div>

            {rankingMode === "back3" && renderBack3Grid(top20, 'No predictions yet — click "Train + Predict".')}

            {rankingMode === "last2" && renderLast2Grid(last2Top10, 'No 2-digit predictions yet — click "Train + Predict".')}
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

        {tab === "predhistory" && (
          <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10 }}>
            {predHistory.length === 0 && (
              <div style={{ padding: 14, color: "#6a8ab8", fontSize: 12 }}>
                No prediction runs yet — click "Train + Predict".
              </div>
            )}
            {predHistory.map((run) => {
              const badge = (hit: boolean | null) =>
                hit === null
                  ? { text: "… pending", color: "#6a8ab8" }
                  : hit
                  ? { text: "✓ hit", color: "#00ff88" }
                  : { text: "✗ miss", color: "#ff6b6b" };
              const b3 = badge(run.back3Hit);
              const l2 = badge(run.last2Hit);
              const isOpen = expandedId === run.id;
              return (
                <div key={run.id} style={{ borderTop: "1px solid #0d1f3c" }}>
                  <div
                    onClick={() => setExpandedId(isOpen ? null : run.id)}
                    style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", alignItems: "center", gap: 10, padding: "8px 14px", fontSize: 11, cursor: "pointer" }}
                  >
                    <span style={{ color: "#e0e8ff" }}>{new Date(run.createdAt).toLocaleString()}</span>
                    <span style={{ color: "#6a8ab8" }}>
                      {run.target ? `→ ${run.target.date.slice(0, 10)} (${run.target.back3}/${run.target.last2 ?? "—"})` : "pending"}
                    </span>
                    <span style={{ color: b3.color }}>3D {b3.text}</span>
                    <span style={{ color: l2.color }}>2D {l2.text}</span>
                  </div>
                  {isOpen && (
                    <div style={{ padding: "0 14px 14px" }}>
                      <div style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", margin: "8px 0" }}>2-Digit</div>
                      {renderLast2Grid(run.last2Items)}
                      <div style={{ color: "#4a9eff", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", margin: "12px 0 8px" }}>3-Digit</div>
                      {renderBack3Grid(run.back3Items)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {tab === "adddata" && (
          <div style={{ background: "#0a1628", border: "1px solid #1a3a6b", borderRadius: 10, padding: 14, maxWidth: 480 }}>
            <div style={{ display: "grid", gap: 10, marginBottom: 10 }}>
              <input type="date" value={newDraw.date} onChange={(e) => setNewDraw({ ...newDraw, date: e.target.value })} style={inp} />
              <input placeholder="First prize 6-digit (e.g. 812523)" maxLength={6} value={newDraw.firstPrize} onChange={(e) => setNewDraw({ ...newDraw, firstPrize: e.target.value.replace(/\D/g, "") })} style={inp} />
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
