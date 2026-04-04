import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Cell } from "recharts";

// ===== CONFIGURATION =====
const API_BASE = "http://localhost:8000/api";
const USE_MOCK = true; // true: mock data로 렌더링, false: FastAPI 연동

// ===== MOCK DATA =====
const MOCK = {
  score: {
    date: "2026-03-24", total_score: 62.4, regime: "late_cycle",
    regime_description: "후기 확장 — 수요는 견조하나 매크로 환경 악화 조짐",
    investment_action: "선별적 포지션 유지 (Neutral → Underweight 준비)|밸류에이션 높은 종목 차익실현 검토|방어적 전환: 장비/소재 → 팹리스, 서비스 쪽으로 이동|수익률곡선 역전 심화 시 즉각 비중 축소",
    confidence_level: "medium", data_coverage: 0.68, signal_count: 15,
    dimensions: {
      demand_cycle: { score: 68.2, weight: 0.3, confidence: 0.75, contributing_signals: [
        { indicator_id: "HYPERSCALER_CAPEX", signal_type: "bullish", strength: 0.8, score: 90, weight: 1.5, description: "Hyperscaler CapEx 평균 YoY +38.2%" },
        { indicator_id: "ISM_MFG", signal_type: "bullish", strength: 0.45, score: 72.5, weight: 1.3, description: "PMI 52.3 | New Orders-Inventories spread +4.2" },
        { indicator_id: "DGORDER", signal_type: "bullish", strength: 0.3, score: 65, weight: 1.2, description: "비국방자본재 2개월 연속 증가 | MoM +1.2%, YoY +4.8%" },
        { indicator_id: "SOX", signal_type: "bullish", strength: 0.35, score: 67.5, weight: 1.0, description: "SOX 5142 | 200일선 위 (+8.3%)" },
        { indicator_id: "RETAIL", signal_type: "neutral", strength: 0.1, score: 55, weight: 0.8, description: "전자/가전 소매 YoY +1.2%" },
        { indicator_id: "CONSUMER_CONF", signal_type: "bearish", strength: 0.2, score: 40, weight: 0.7, description: "소비심리 64.2 (5년 백분위 32%)" },
      ]},
      supply_cycle: { score: 58.5, weight: 0.2, confidence: 0.67, contributing_signals: [
        { indicator_id: "INDPRO", signal_type: "neutral", strength: 0.15, score: 57.5, weight: 1.0, description: "가동률 77.8% | 산업생산 MoM +0.2%" },
        { indicator_id: "SEMI_BB", signal_type: "bullish", strength: 0.3, score: 65, weight: 1.3, description: "B/B Ratio 1.04 | 확장" },
      ]},
      price_cycle: { score: 64.8, weight: 0.2, confidence: 0.67, contributing_signals: [
        { indicator_id: "DRAM_SPOT", signal_type: "bullish", strength: 0.5, score: 75, weight: 1.5, description: "DRAM 가격 $3.62 | MoM +6.8%" },
        { indicator_id: "CPI", signal_type: "neutral", strength: 0.15, score: 57.5, weight: 0.8, description: "Core CPI YoY 3.1% | 하락 추세" },
      ]},
      macro_regime: { score: 48.3, weight: 0.2, confidence: 0.8, contributing_signals: [
        { indicator_id: "GDP", signal_type: "neutral", strength: 0.1, score: 55, weight: 1.0, description: "GDP QoQ +1.8% | IT투자 YoY +8.2%" },
        { indicator_id: "YIELD_CURVE", signal_type: "bearish", strength: 0.35, score: 32.5, weight: 1.2, description: "10Y-2Y spread -0.22% (역전)" },
        { indicator_id: "FOMC", signal_type: "bearish", strength: 0.2, score: 40, weight: 1.1, description: "Fed Funds Rate 4.75% | 동결 기조" },
        { indicator_id: "LEI", signal_type: "bearish", strength: 0.3, score: 35, weight: 1.0, description: "LEI -3개월 연속 | MoM -0.4%" },
      ]},
      global_demand: { score: 55.0, weight: 0.1, confidence: 0.5, contributing_signals: [
        { indicator_id: "CHINA_PMI", signal_type: "neutral", strength: 0.1, score: 55, weight: 1.2, description: "중국 제조업 PMI 50.4 | 확장" },
      ]},
    },
  },
  scenarios: {
    base_score: 62.4,
    scenarios: [
      { scenario: { id: "ai_capex_surge", name: "AI CapEx 급증", probability: 0.25, time_horizon: "6m" }, delta: 18.2, adjusted_score: 80.6, adjusted_regime: "expansion", regime_changed: true },
      { scenario: { id: "fed_pivot_dovish", name: "Fed 비둘기파 전환", probability: 0.30, time_horizon: "6m" }, delta: 10.5, adjusted_score: 72.9, adjusted_regime: "expansion", regime_changed: true },
      { scenario: { id: "china_recovery", name: "중국 경기 회복", probability: 0.20, time_horizon: "6m" }, delta: 7.8, adjusted_score: 70.2, adjusted_regime: "expansion", regime_changed: true },
      { scenario: { id: "trade_war_escalation", name: "미중 기술전쟁 격화", probability: 0.20, time_horizon: "6m" }, delta: -9.2, adjusted_score: 53.2, adjusted_regime: "late_cycle", regime_changed: false },
      { scenario: { id: "recession_hard", name: "경기 침체", probability: 0.15, time_horizon: "12m" }, delta: -26.8, adjusted_score: 35.6, adjusted_regime: "contraction", regime_changed: true },
      { scenario: { id: "ai_bubble_burst", name: "AI 버블 붕괴", probability: 0.10, time_horizon: "12m" }, delta: -22.4, adjusted_score: 40.0, adjusted_regime: "contraction", regime_changed: true },
    ],
  },
  scoreHistory: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-${String(Math.floor(i / 30 * 3) + 1).padStart(2, "0")}-${String((i % 28) + 1).padStart(2, "0")}`,
    total: 55 + Math.sin(i * 0.3) * 12 + i * 0.25,
    demand: 60 + Math.sin(i * 0.25) * 10 + i * 0.3,
    supply: 50 + Math.cos(i * 0.2) * 8,
    price: 45 + Math.sin(i * 0.35) * 15 + i * 0.5,
    macro: 52 - i * 0.15 + Math.sin(i * 0.4) * 6,
    global: 50 + Math.cos(i * 0.3) * 5,
  })),
};

// ===== THEME =====
const T = {
  bg: "#06080d", surface: "#0c1018", elevated: "#121822", border: "#1c2638",
  text: "#c8d6e5", textDim: "#5a6d84", textMuted: "#3a4a5e",
  accent1: "#00d4aa", accent2: "#f0b429", accent3: "#4dabf7", accent4: "#e64980",
  bullish: "#00d4aa", bearish: "#ff6b6b", neutral: "#5a6d84",
  expansion: "#00d4aa", late_cycle: "#f0b429", contraction: "#ff6b6b", recovery: "#4dabf7",
  font: "'IBM Plex Mono', 'Menlo', monospace",
  fontSans: "'IBM Plex Sans', -apple-system, sans-serif",
};

const regimeLabel = { expansion: "EXPANSION", late_cycle: "LATE CYCLE", contraction: "CONTRACTION", recovery: "RECOVERY" };
const dimLabel = { demand_cycle: "DEMAND", supply_cycle: "SUPPLY", price_cycle: "PRICE", macro_regime: "MACRO", global_demand: "GLOBAL" };

// ===== GAUGE COMPONENT =====
function ScoreGauge({ score, regime }) {
  const r = 90, cx = 110, cy = 105;
  const startAngle = -225, endAngle = 45;
  const range = endAngle - startAngle;
  const scoreAngle = startAngle + (score / 100) * range;

  const polarToCart = (angle, radius) => ({
    x: cx + radius * Math.cos((angle * Math.PI) / 180),
    y: cy + radius * Math.sin((angle * Math.PI) / 180),
  });

  const arcPath = (start, end, radius) => {
    const s = polarToCart(start, radius);
    const e = polarToCart(end, radius);
    const large = end - start > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${large} 1 ${e.x} ${e.y}`;
  };

  const needle = polarToCart(scoreAngle, r - 12);
  const color = T[regime] || T.neutral;

  return (
    <svg viewBox="0 0 220 140" style={{ width: "100%", maxWidth: 260 }}>
      <defs>
        <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={T.bearish} />
          <stop offset="35%" stopColor={T.accent2} />
          <stop offset="65%" stopColor={T.accent2} />
          <stop offset="100%" stopColor={T.bullish} />
        </linearGradient>
        <filter id="glow"><feGaussianBlur stdDeviation="3" result="g" /><feMerge><feMergeNode in="g" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <path d={arcPath(startAngle, endAngle, r)} fill="none" stroke={T.border} strokeWidth="8" strokeLinecap="round" />
      <path d={arcPath(startAngle, scoreAngle, r)} fill="none" stroke="url(#gaugeGrad)" strokeWidth="8" strokeLinecap="round" filter="url(#glow)" />
      {[0, 25, 50, 75, 100].map(v => {
        const a = startAngle + (v / 100) * range;
        const p = polarToCart(a, r + 12);
        return <text key={v} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="middle" fill={T.textDim} fontSize="8" fontFamily={T.font}>{v}</text>;
      })}
      <line x1={cx} y1={cy} x2={needle.x} y2={needle.y} stroke={color} strokeWidth="2.5" strokeLinecap="round" filter="url(#glow)" />
      <circle cx={cx} cy={cy} r="4" fill={color} />
      <text x={cx} y={cy + 22} textAnchor="middle" fill={color} fontSize="28" fontWeight="700" fontFamily={T.font}>{score.toFixed(1)}</text>
      <text x={cx} y={cy + 35} textAnchor="middle" fill={color} fontSize="9" fontFamily={T.font} letterSpacing="2">{regimeLabel[regime]}</text>
    </svg>
  );
}

// ===== DIMENSION BAR =====
function DimBar({ name, score, weight, signals }) {
  const color = score >= 60 ? T.bullish : score < 40 ? T.bearish : T.accent2;
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginBottom: 6 }}>
      <div onClick={() => setExpanded(!expanded)} style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "6px 0" }}>
        <span style={{ width: 60, fontSize: 10, color: T.textDim, fontFamily: T.font }}>{dimLabel[name]}</span>
        <div style={{ flex: 1, height: 6, background: T.border, borderRadius: 3, overflow: "hidden" }}>
          <div style={{ width: `${score}%`, height: "100%", background: `linear-gradient(90deg, ${color}88, ${color})`, borderRadius: 3, transition: "width 0.8s ease" }} />
        </div>
        <span style={{ width: 36, textAlign: "right", fontSize: 12, fontWeight: 600, color, fontFamily: T.font }}>{score.toFixed(0)}</span>
        <span style={{ width: 30, textAlign: "right", fontSize: 9, color: T.textDim }}>{(weight * 100).toFixed(0)}%</span>
        <span style={{ fontSize: 9, color: T.textMuted, width: 12 }}>{expanded ? "▾" : "▸"}</span>
      </div>
      {expanded && signals && (
        <div style={{ marginLeft: 70, marginBottom: 8 }}>
          {signals.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", fontSize: 10, borderLeft: `2px solid ${T[s.signal_type]}33`, paddingLeft: 8, marginBottom: 2 }}>
              <span style={{ color: T[s.signal_type], width: 14, textAlign: "center" }}>{s.signal_type === "bullish" ? "▲" : s.signal_type === "bearish" ? "▼" : "●"}</span>
              <span style={{ color: T.textDim, width: 120 }}>{s.indicator_id}</span>
              <span style={{ color: T.text, flex: 1 }}>{s.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ===== SIGNAL CARD =====
function SignalCard({ sig, type }) {
  const color = T[type];
  return (
    <div style={{ padding: "8px 10px", background: `${color}08`, borderLeft: `2px solid ${color}44`, marginBottom: 4, borderRadius: "0 4px 4px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, color, fontWeight: 600, fontFamily: T.font }}>{sig.indicator_id}</span>
        <span style={{ fontSize: 9, color: T.textDim, fontFamily: T.font }}>{(sig.strength * 100).toFixed(0)}%</span>
      </div>
      <div style={{ fontSize: 10, color: T.text, marginTop: 3, lineHeight: 1.5 }}>{sig.description}</div>
    </div>
  );
}

// ===== SCENARIO ROW =====
function ScenarioRow({ sc, baseScore }) {
  const isPositive = sc.delta > 0;
  const color = isPositive ? T.bullish : T.bearish;
  const barWidth = Math.min(Math.abs(sc.delta) / 30 * 100, 100);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "140px 40px 50px 1fr 50px 70px", gap: 8, alignItems: "center", padding: "7px 0", borderBottom: `1px solid ${T.border}`, fontSize: 10, fontFamily: T.font }}>
      <span style={{ color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sc.scenario.name}</span>
      <span style={{ color: T.textDim, textAlign: "right" }}>{(sc.scenario.probability * 100).toFixed(0)}%</span>
      <span style={{ color, textAlign: "right", fontWeight: 600 }}>{sc.delta > 0 ? "+" : ""}{sc.delta.toFixed(1)}</span>
      <div style={{ height: 4, background: T.border, borderRadius: 2, overflow: "hidden", position: "relative" }}>
        <div style={{
          position: "absolute", height: "100%", borderRadius: 2, background: color,
          ...(isPositive ? { left: "50%", width: `${barWidth / 2}%` } : { right: "50%", width: `${barWidth / 2}%` }),
        }} />
        <div style={{ position: "absolute", left: "50%", top: -2, width: 1, height: 8, background: T.textDim }} />
      </div>
      <span style={{ textAlign: "right", color: T.text }}>{sc.adjusted_score.toFixed(1)}</span>
      <span style={{ textAlign: "right", color: T[sc.adjusted_regime] || T.textDim, fontSize: 9 }}>
        {regimeLabel[sc.adjusted_regime]}
        {sc.regime_changed && <span style={{ color: T.accent2, marginLeft: 3 }}>⚠</span>}
      </span>
    </div>
  );
}

// ===== CUSTOM TOOLTIP =====
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: T.elevated, border: `1px solid ${T.border}`, borderRadius: 4, padding: "8px 12px", fontSize: 10, fontFamily: T.font }}>
      <div style={{ color: T.textDim, marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, display: "flex", gap: 8 }}>
          <span>{p.name}</span><span style={{ fontWeight: 600 }}>{Number(p.value).toFixed(1)}</span>
        </div>
      ))}
    </div>
  );
}

// ===== MAIN DASHBOARD =====
export default function Dashboard() {
  const [data, setData] = useState({ score: MOCK.score, scenarios: MOCK.scenarios, history: MOCK.scoreHistory });
  const [tab, setTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toISOString());

  const fetchData = useCallback(async () => {
    if (USE_MOCK) return;
    setLoading(true);
    try {
      const [scoreRes, scenRes] = await Promise.all([
        fetch(`${API_BASE}/score`).then(r => r.json()),
        fetch(`${API_BASE}/scenarios/compare`).then(r => r.json()),
      ]);
      setData({ score: scoreRes, scenarios: scenRes, history: MOCK.scoreHistory });
      setLastUpdate(new Date().toISOString());
    } catch (e) { console.error("Fetch failed:", e); }
    setLoading(false);
  }, []);

  const sc = data.score;
  const dims = sc.dimensions;
  const scenarios = data.scenarios;

  // Collect all signals
  const allSignals = Object.values(dims).flatMap(d => d.contributing_signals || []);
  const bullish = allSignals.filter(s => s.signal_type === "bullish").sort((a, b) => b.strength - a.strength);
  const bearish = allSignals.filter(s => s.signal_type === "bearish").sort((a, b) => b.strength - a.strength);

  // Radar data
  const radarData = Object.entries(dims).map(([k, v]) => ({ dim: dimLabel[k], score: v.score, fullMark: 100 }));

  const tabs = [
    { id: "overview", label: "OVERVIEW" },
    { id: "signals", label: "SIGNALS" },
    { id: "scenarios", label: "SCENARIOS" },
    { id: "trends", label: "TRENDS" },
  ];

  return (
    <div style={{ fontFamily: T.fontSans, background: T.bg, color: T.text, minHeight: "100vh", padding: 0 }}>
      {/* === HEADER === */}
      <header style={{ background: "linear-gradient(180deg, #0c1220 0%, #06080d 100%)", borderBottom: `1px solid ${T.border}`, padding: "14px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 9, letterSpacing: 3, color: T.accent1, textTransform: "uppercase", fontFamily: T.font }}>Semi-Intel v0.2</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: T.text, marginTop: 2, letterSpacing: -0.5 }}>Semiconductor Cycle Command Center</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 10, fontFamily: T.font }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: T.textDim }}>CONFIDENCE</div>
              <div style={{ color: sc.confidence_level === "high" ? T.bullish : sc.confidence_level === "medium" ? T.accent2 : T.bearish }}>{sc.confidence_level?.toUpperCase()}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: T.textDim }}>COVERAGE</div>
              <div style={{ color: T.text }}>{((sc.data_coverage || 0) * 100).toFixed(0)}%</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: T.textDim }}>SIGNALS</div>
              <div style={{ color: T.text }}>{sc.signal_count || allSignals.length}</div>
            </div>
            {!USE_MOCK && (
              <button onClick={fetchData} style={{ padding: "5px 12px", background: T.elevated, border: `1px solid ${T.border}`, borderRadius: 4, color: T.accent1, fontSize: 10, fontFamily: T.font, cursor: "pointer" }}>
                {loading ? "..." : "REFRESH"}
              </button>
            )}
          </div>
        </div>
        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, marginTop: 14 }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: "7px 16px", fontSize: 10, fontFamily: T.font, letterSpacing: 1, cursor: "pointer",
              background: tab === t.id ? T.elevated : "transparent",
              color: tab === t.id ? T.accent1 : T.textDim,
              border: "none", borderBottom: tab === t.id ? `2px solid ${T.accent1}` : "2px solid transparent",
              transition: "all 0.2s",
            }}>{t.label}</button>
          ))}
        </div>
      </header>

      <div style={{ padding: "16px 20px" }}>

        {/* ===== OVERVIEW TAB ===== */}
        {tab === "overview" && (
          <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 260px", gap: 16, alignItems: "start" }}>
            {/* Left: Score Gauge + Actions */}
            <div>
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16, textAlign: "center" }}>
                <div style={{ fontSize: 9, color: T.textDim, letterSpacing: 2, fontFamily: T.font, marginBottom: 8 }}>SEMICONDUCTOR CYCLE SCORE</div>
                <ScoreGauge score={sc.total_score} regime={sc.regime} />
                <div style={{ fontSize: 10, color: T.textDim, marginTop: 8, lineHeight: 1.6, textAlign: "left" }}>{sc.regime_description}</div>
              </div>

              {/* Investment Actions */}
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 14, marginTop: 12 }}>
                <div style={{ fontSize: 9, color: T.accent2, letterSpacing: 2, fontFamily: T.font, marginBottom: 10 }}>INVESTMENT ACTION</div>
                {(sc.investment_action || "").split("|").map((a, i) => (
                  <div key={i} style={{ fontSize: 10, color: T.text, padding: "5px 0", borderBottom: i < 3 ? `1px solid ${T.border}` : "none", lineHeight: 1.5 }}>
                    <span style={{ color: T.accent1, marginRight: 6 }}>→</span>{a.trim()}
                  </div>
                ))}
              </div>
            </div>

            {/* Center: Dimensions + Radar */}
            <div>
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16 }}>
                <div style={{ fontSize: 9, color: T.textDim, letterSpacing: 2, fontFamily: T.font, marginBottom: 14 }}>DIMENSION BREAKDOWN</div>
                {Object.entries(dims).map(([name, dim]) => (
                  <DimBar key={name} name={name} score={dim.score} weight={dim.weight} signals={dim.contributing_signals} />
                ))}
              </div>

              {/* Radar */}
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16, marginTop: 12 }}>
                <div style={{ fontSize: 9, color: T.textDim, letterSpacing: 2, fontFamily: T.font, marginBottom: 8 }}>DIMENSIONAL PROFILE</div>
                <ResponsiveContainer width="100%" height={200}>
                  <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                    <PolarGrid stroke={T.border} />
                    <PolarAngleAxis dataKey="dim" tick={{ fill: T.textDim, fontSize: 9, fontFamily: T.font }} />
                    <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
                    <Radar dataKey="score" stroke={T.accent1} fill={T.accent1} fillOpacity={0.15} strokeWidth={2} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Right: Key Signals */}
            <div>
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 9, color: T.bullish, letterSpacing: 2, fontFamily: T.font, marginBottom: 10 }}>▲ BULLISH ({bullish.length})</div>
                {bullish.slice(0, 5).map((s, i) => <SignalCard key={i} sig={s} type="bullish" />)}
              </div>
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 14, marginTop: 12 }}>
                <div style={{ fontSize: 9, color: T.bearish, letterSpacing: 2, fontFamily: T.font, marginBottom: 10 }}>▼ BEARISH ({bearish.length})</div>
                {bearish.slice(0, 5).map((s, i) => <SignalCard key={i} sig={s} type="bearish" />)}
              </div>
            </div>
          </div>
        )}

        {/* ===== SIGNALS TAB ===== */}
        {tab === "signals" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {Object.entries(dims).map(([dimName, dim]) => (
              <div key={dimName} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 9, letterSpacing: 2, color: T.textDim, fontFamily: T.font }}>{dimLabel[dimName]}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: dim.score >= 60 ? T.bullish : dim.score < 40 ? T.bearish : T.accent2, fontFamily: T.font }}>{dim.score.toFixed(1)}</div>
                  </div>
                  <div style={{ textAlign: "right", fontSize: 10, fontFamily: T.font }}>
                    <div style={{ color: T.textDim }}>Weight {(dim.weight * 100).toFixed(0)}%</div>
                    <div style={{ color: T.textDim }}>Coverage {(dim.confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>
                {(dim.contributing_signals || []).map((s, i) => (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "14px 100px 1fr 40px", gap: 6, alignItems: "center",
                    padding: "6px 8px", marginBottom: 3, borderRadius: 4,
                    background: `${T[s.signal_type]}06`, borderLeft: `2px solid ${T[s.signal_type]}44`,
                    fontSize: 10,
                  }}>
                    <span style={{ color: T[s.signal_type] }}>{s.signal_type === "bullish" ? "▲" : s.signal_type === "bearish" ? "▼" : "●"}</span>
                    <span style={{ fontFamily: T.font, color: T.text }}>{s.indicator_id}</span>
                    <span style={{ color: T.textDim }}>{s.description}</span>
                    <span style={{ textAlign: "right", fontFamily: T.font, color: T[s.signal_type] }}>{s.score?.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* ===== SCENARIOS TAB ===== */}
        {tab === "scenarios" && (
          <div>
            <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 9, letterSpacing: 2, color: T.textDim, fontFamily: T.font }}>SCENARIO COMPARISON</div>
                  <div style={{ fontSize: 12, color: T.text, marginTop: 4 }}>Base Score: <span style={{ color: T.accent1, fontWeight: 700, fontFamily: T.font }}>{scenarios.base_score}</span></div>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "140px 40px 50px 1fr 50px 70px", gap: 8, padding: "6px 0", borderBottom: `1px solid ${T.border}`, fontSize: 9, color: T.textDim, fontFamily: T.font }}>
                <span>SCENARIO</span><span style={{ textAlign: "right" }}>PROB</span><span style={{ textAlign: "right" }}>DELTA</span><span style={{ textAlign: "center" }}>IMPACT</span><span style={{ textAlign: "right" }}>SCORE</span><span style={{ textAlign: "right" }}>REGIME</span>
              </div>
              {scenarios.scenarios.map((sc, i) => <ScenarioRow key={i} sc={sc} baseScore={scenarios.base_score} />)}
            </div>

            {/* Scenario Impact Chart */}
            <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16, marginTop: 16 }}>
              <div style={{ fontSize: 9, letterSpacing: 2, color: T.textDim, fontFamily: T.font, marginBottom: 12 }}>SCORE IMPACT BY SCENARIO</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={scenarios.scenarios.map(s => ({ name: s.scenario.name.substring(0, 12), delta: s.delta, score: s.adjusted_score }))} layout="vertical" margin={{ left: 80, right: 20 }}>
                  <XAxis type="number" tick={{ fill: T.textDim, fontSize: 9 }} axisLine={{ stroke: T.border }} domain={[-30, 30]} />
                  <YAxis type="category" dataKey="name" tick={{ fill: T.textDim, fontSize: 10, fontFamily: T.font }} axisLine={false} tickLine={false} width={80} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="delta" radius={[0, 3, 3, 0]}>
                    {scenarios.scenarios.map((s, i) => (
                      <Cell key={i} fill={s.delta > 0 ? T.bullish : T.bearish} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Regime Zones */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 16 }}>
              {[
                { regime: "expansion", range: "65-100", desc: "반도체 비중 확대, AI/HBM 집중" },
                { regime: "late_cycle", range: "50-65", desc: "선별적 유지, 차익실현 준비" },
                { regime: "contraction", range: "35-50", desc: "비중 축소, 바닥 모니터링" },
                { regime: "recovery", range: "0-35↑", desc: "바닥 매수 시작, 장비/소재 선행" },
              ].map(z => (
                <div key={z.regime} style={{
                  background: T.surface, border: `1px solid ${sc.regime === z.regime ? T[z.regime] + "66" : T.border}`,
                  borderRadius: 8, padding: 14, borderTop: `3px solid ${T[z.regime]}`,
                  opacity: sc.regime === z.regime ? 1 : 0.5,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T[z.regime], fontFamily: T.font }}>{regimeLabel[z.regime]}</div>
                  <div style={{ fontSize: 9, color: T.textDim, marginTop: 2, fontFamily: T.font }}>{z.range}</div>
                  <div style={{ fontSize: 10, color: T.text, marginTop: 8, lineHeight: 1.5 }}>{z.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ===== TRENDS TAB ===== */}
        {tab === "trends" && (
          <div>
            {/* Total Score Trend */}
            <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 9, letterSpacing: 2, color: T.textDim, fontFamily: T.font, marginBottom: 12 }}>COMPOSITE SCORE TREND</div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={data.history}>
                  <defs>
                    <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={T.accent1} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={T.accent1} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fill: T.textDim, fontSize: 8 }} axisLine={{ stroke: T.border }} interval="preserveStartEnd" />
                  <YAxis domain={[30, 90]} tick={{ fill: T.textDim, fontSize: 9 }} axisLine={{ stroke: T.border }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="total" stroke={T.accent1} fill="url(#totalGrad)" strokeWidth={2} name="Total" dot={false} />
                  {/* Regime zones */}
                  <Area type="monotone" dataKey={() => 65} stroke={T.textMuted} strokeDasharray="4 4" fill="none" strokeWidth={1} />
                  <Area type="monotone" dataKey={() => 50} stroke={T.textMuted} strokeDasharray="4 4" fill="none" strokeWidth={1} />
                  <Area type="monotone" dataKey={() => 35} stroke={T.textMuted} strokeDasharray="4 4" fill="none" strokeWidth={1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Dimension Trends */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
              {[
                { key: "demand", label: "DEMAND CYCLE", color: T.accent1 },
                { key: "supply", label: "SUPPLY CYCLE", color: T.accent3 },
                { key: "price", label: "PRICE CYCLE", color: T.accent2 },
                { key: "macro", label: "MACRO REGIME", color: T.accent4 },
              ].map(dim => (
                <div key={dim.key} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 14 }}>
                  <div style={{ fontSize: 9, letterSpacing: 2, color: dim.color, fontFamily: T.font, marginBottom: 8 }}>{dim.label}</div>
                  <ResponsiveContainer width="100%" height={120}>
                    <LineChart data={data.history}>
                      <XAxis dataKey="date" tick={false} axisLine={{ stroke: T.border }} />
                      <YAxis domain={[20, 90]} tick={{ fill: T.textDim, fontSize: 8 }} axisLine={{ stroke: T.border }} width={25} />
                      <Tooltip content={<ChartTooltip />} />
                      <Line type="monotone" dataKey={dim.key} stroke={dim.color} strokeWidth={1.5} dot={false} name={dim.label} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>

            {/* Correlation hint */}
            <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, padding: 16, marginTop: 16 }}>
              <div style={{ fontSize: 9, letterSpacing: 2, color: T.textDim, fontFamily: T.font, marginBottom: 12 }}>ALL DIMENSIONS OVERLAY</div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.history}>
                  <XAxis dataKey="date" tick={{ fill: T.textDim, fontSize: 8 }} axisLine={{ stroke: T.border }} interval="preserveStartEnd" />
                  <YAxis domain={[20, 90]} tick={{ fill: T.textDim, fontSize: 9 }} axisLine={{ stroke: T.border }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="demand" stroke={T.accent1} strokeWidth={1.5} dot={false} name="Demand" />
                  <Line type="monotone" dataKey="supply" stroke={T.accent3} strokeWidth={1.5} dot={false} name="Supply" />
                  <Line type="monotone" dataKey="price" stroke={T.accent2} strokeWidth={1.5} dot={false} name="Price" />
                  <Line type="monotone" dataKey="macro" stroke={T.accent4} strokeWidth={1.5} dot={false} name="Macro" />
                  <Line type="monotone" dataKey="global" stroke="#9775fa" strokeWidth={1} dot={false} name="Global" strokeDasharray="4 4" />
                </LineChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 8 }}>
                {[
                  { label: "Demand", color: T.accent1 }, { label: "Supply", color: T.accent3 },
                  { label: "Price", color: T.accent2 }, { label: "Macro", color: T.accent4 },
                  { label: "Global", color: "#9775fa" },
                ].map(l => (
                  <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, color: T.textDim }}>
                    <div style={{ width: 8, height: 2, background: l.color, borderRadius: 1 }} />
                    {l.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer style={{ borderTop: `1px solid ${T.border}`, padding: "10px 20px", display: "flex", justifyContent: "space-between", fontSize: 9, color: T.textMuted, fontFamily: T.font }}>
        <span>Semi-Intel v0.2 — Based on "The Secrets of Economic Indicators" by B. Baumohl + Sector Extensions</span>
        <span>{USE_MOCK ? "MOCK DATA" : `Last update: ${lastUpdate.substring(0, 19)}`}</span>
      </footer>
    </div>
  );
}
