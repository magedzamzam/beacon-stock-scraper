"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart,
  RadarChart, PolarGrid, PolarAngleAxis, Radar, PolarRadiusAxis,
} from "recharts";
import { api } from "@/lib/api";
import { fmtNumber, fmtPercent, fmtMoney, fmtDate, changeColor } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import {
  RefreshCw, ExternalLink, Plus, Star, ThumbsUp, ThumbsDown, Newspaper, BarChart3,
} from "lucide-react";

export default function StockDetailPage() {
  const p = useParams<{ exchange: string; ticker: string }>();
  const exchange = p.exchange.toLowerCase();
  const ticker = p.ticker.toUpperCase();
  const [refreshing, setRefreshing] = useState(false);

  const { data: stock } = useSWR(["stock", exchange, ticker], () => api.stockDetail(exchange, ticker));
  const { data: score } = useSWR(["score", exchange, ticker], () => api.stockScore(exchange, ticker));
  const { data: history } = useSWR(["history", exchange, ticker], () => api.priceHistory(exchange, ticker, 180));
  const { data: news } = useSWR(["news", exchange, ticker], () => api.stockNews(exchange, ticker, 10));
  const { data: watchlists } = useSWR("watchlists", api.listWatchlists);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.refreshStock(exchange, ticker);
      setTimeout(() => {
        mutate(["stock", exchange, ticker]);
        mutate(["score", exchange, ticker]);
        mutate(["history", exchange, ticker]);
        mutate(["news", exchange, ticker]);
        setRefreshing(false);
      }, 4000);
    } catch (e: any) {
      alert(e.message);
      setRefreshing(false);
    }
  }

  async function addToWatchlist(wid: number) {
    if (!stock) return;
    try {
      await api.addWatchlistItem(wid, stock.id);
      alert("Added to watchlist");
    } catch (e: any) { alert(e.message); }
  }

  async function addPosition() {
    if (!stock) return;
    const qtyStr = prompt(`Quantity of ${stock.ticker}?`);
    if (!qtyStr) return;
    const priceStr = prompt(`Average entry price (${stock.currency || ""})?`);
    if (!priceStr) return;
    try {
      await api.addPosition(stock.id, Number(qtyStr), Number(priceStr));
      alert("Position added");
    } catch (e: any) { alert(e.message); }
  }

  if (!stock) return <div className="text-ink-muted">Loading…</div>;

  const radarData = score ? [
    { axis: "Fundamental", value: score.fundamental_score },
    { axis: "Valuation", value: score.valuation_score },
    { axis: "Momentum", value: score.momentum_score },
    { axis: "Technical", value: score.technical_score },
    { axis: "Analyst", value: score.analyst_score },
    { axis: "Quality", value: score.quality_score },
    { axis: "Risk", value: 100 - score.risk_score },
  ] : [];

  const chartData = (history ?? []).map((p) => ({ date: p.trading_date, close: p.close }));

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-ink-dim uppercase tracking-wider">
            <span>{stock.exchange_code}</span>
            {stock.sector && <><span>·</span><span>{stock.sector}</span></>}
            {stock.industry && <><span>·</span><span>{stock.industry}</span></>}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {stock.ticker} <span className="text-ink-muted text-base font-normal">— {stock.company_name}</span>
          </h1>
          <div className="mt-2 flex items-baseline gap-3">
            <div className="text-3xl font-semibold font-mono">{fmtNumber(stock.last_close)}</div>
            <div className={`text-sm font-mono ${changeColor(stock.last_change_pct)}`}>{fmtPercent(stock.last_change_pct)}</div>
            {score && <VerdictBadge verdict={score.verdict} size="md" />}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </button>
          <div className="relative group">
            <button className="btn-ghost"><Star className="size-4" /> Watchlist</button>
            <div className="absolute right-0 mt-1 w-56 card p-1.5 hidden group-hover:block z-10">
              {watchlists?.map((w) => (
                <button key={w.id} onClick={() => addToWatchlist(w.id)}
                        className="w-full text-left px-3 py-1.5 text-sm rounded-md hover:bg-bg-elevated">
                  + {w.name}
                </button>
              ))}
              {!watchlists?.length && <div className="px-3 py-2 text-xs text-ink-muted">No watchlists</div>}
            </div>
          </div>
          <button className="btn-primary" onClick={addPosition}><Plus className="size-4" /> Add Position</button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr,360px] gap-5">
        {/* Left column - chart + news */}
        <div className="space-y-5">
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold flex items-center gap-2"><BarChart3 className="size-4" /> 6-month price</h3>
              <div className="text-xs text-ink-muted">
                52w: {fmtNumber(stock.week_52_low)} – {fmtNumber(stock.week_52_high)}
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1f2a3d" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={11}
                         tickFormatter={(v) => new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" })} />
                  <YAxis stroke="#64748b" fontSize={11} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ background: "#111826", border: "1px solid #1f2a3d", borderRadius: 8, fontSize: 12 }}
                    labelFormatter={(v) => fmtDate(String(v))}
                    formatter={(v: any) => [fmtNumber(v), "Close"]}
                  />
                  <Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#priceGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {score && (
            <div className="card p-4">
              <h3 className="text-sm font-semibold mb-3">Why this verdict?</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="label flex items-center gap-1 mb-2"><ThumbsUp className="size-3 text-verdict-buy" /> Pros</div>
                  <ul className="space-y-1 text-sm">
                    {score.pros.map((p, i) => <li key={i} className="text-ink">• {p}</li>)}
                    {!score.pros.length && <li className="text-ink-muted">—</li>}
                  </ul>
                </div>
                <div>
                  <div className="label flex items-center gap-1 mb-2"><ThumbsDown className="size-3 text-verdict-avoid" /> Cons</div>
                  <ul className="space-y-1 text-sm">
                    {score.cons.map((c, i) => <li key={i} className="text-ink">• {c}</li>)}
                    {!score.cons.length && <li className="text-ink-muted">—</li>}
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div className="card p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Newspaper className="size-4" /> News & disclosures</h3>
            <div className="space-y-3">
              {(news ?? []).map((n) => (
                <a key={n.id} href={n.url || "#"} target="_blank" rel="noreferrer"
                   className="block p-3 rounded-lg bg-bg-subtle hover:bg-bg-elevated transition-colors">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm">{n.headline}</div>
                    {n.url && <ExternalLink className="size-3 text-ink-dim shrink-0 mt-1" />}
                  </div>
                  <div className="text-xs text-ink-dim mt-1 flex items-center gap-2">
                    <span>{fmtDate(n.news_date)}</span>
                    {n.source_code && <><span>·</span><span>{n.source_code}</span></>}
                    {n.sentiment_label && <><span>·</span><span className="capitalize">{n.sentiment_label}</span></>}
                  </div>
                </a>
              ))}
              {!news?.length && <div className="text-sm text-ink-muted">No recent news.</div>}
            </div>
          </div>
        </div>

        {/* Right column - score radar + key stats */}
        <div className="space-y-5">
          {score && (
            <div className="card p-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-sm font-semibold">Score breakdown</h3>
                <div className="text-2xl font-bold font-mono">{score.composite_score.toFixed(0)}</div>
              </div>
              <div className="text-xs text-ink-dim mb-2">Model {score.model_version} · {fmtDate(score.score_date)}</div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#1f2a3d" />
                    <PolarAngleAxis dataKey="axis" tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} stroke="#1f2a3d" />
                    <Radar dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.35} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div className="grid grid-cols-2 gap-1.5 text-xs mt-2">
                <Sub label="Fundamental" value={score.fundamental_score} />
                <Sub label="Valuation" value={score.valuation_score} />
                <Sub label="Momentum" value={score.momentum_score} />
                <Sub label="Technical" value={score.technical_score} />
                <Sub label="Analyst" value={score.analyst_score} />
                <Sub label="Quality" value={score.quality_score} />
                <Sub label="Risk" value={score.risk_score} invert />
              </div>
            </div>
          )}

          <div className="card p-4">
            <h3 className="text-sm font-semibold mb-3">Key stats</h3>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <Stat label="Mkt cap" value={fmtMoney(stock.market_cap, stock.currency || "", true)} />
              <Stat label="Revenue TTM" value={fmtMoney(stock.revenue_ttm, stock.currency || "", true)} />
              <Stat label="P/E" value={fmtNumber(stock.pe_ratio)} />
              <Stat label="Fwd P/E" value={fmtNumber(stock.forward_pe)} />
              <Stat label="Beta" value={fmtNumber(stock.beta)} />
              <Stat label="Div yield" value={stock.dividend_yield_pct != null ? `${stock.dividend_yield_pct.toFixed(2)}%` : "—"} />
              <Stat label="RSI(14)" value={fmtNumber(stock.rsi_14, { digits: 1 })} />
              <Stat label="50d SMA" value={fmtNumber(stock.sma_50)} />
              <Stat label="200d SMA" value={fmtNumber(stock.sma_200)} />
              <Stat label="Analyst tgt" value={fmtNumber(stock.analyst_target)} />
              <Stat label="Upside" value={stock.analyst_upside_pct != null ? fmtPercent(stock.analyst_upside_pct) : "—"} />
              <Stat label="Analysts" value={fmtNumber(stock.analyst_count, { digits: 0 })} />
            </dl>
          </div>

          <div className="card p-4">
            <h3 className="text-sm font-semibold mb-3">Company</h3>
            <dl className="space-y-2 text-sm">
              <Stat label="Country" value={stock.country || "—"} />
              <Stat label="Founded" value={stock.founded_year || "—"} />
              <Stat label="Employees" value={fmtNumber(stock.employees, { digits: 0 })} />
              {stock.website && (
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Website</dt>
                  <dd><a href={stock.website} target="_blank" rel="noreferrer" className="text-brand hover:underline inline-flex items-center gap-1">Visit <ExternalLink className="size-3" /></a></dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right font-mono">{value}</dd>
    </>
  );
}

function Sub({ label, value, invert = false }: { label: string; value: number; invert?: boolean }) {
  const v = invert ? 100 - value : value;
  const color = v >= 70 ? "bg-verdict-buy" : v >= 45 ? "bg-verdict-watch" : "bg-verdict-avoid";
  return (
    <div className="bg-bg-subtle rounded p-2">
      <div className="flex justify-between text-ink-muted">
        <span>{label}</span>
        <span className="font-mono">{value.toFixed(0)}</span>
      </div>
      <div className="mt-1 h-1 bg-bg-elevated rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${Math.max(2, Math.min(100, v))}%` }} />
      </div>
    </div>
  );
}
