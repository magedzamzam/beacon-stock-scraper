"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart,
  RadarChart, PolarGrid, PolarAngleAxis, Radar, PolarRadiusAxis,
} from "recharts";
import { api, type BrokerQuoteRow as BrokerQuoteData } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { fmtNumber, fmtPercent, fmtMoney, fmtPrice, fmtDate, changeColor, sentimentBadgeClass } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import AIAnalysisModal from "@/components/AIAnalysisModal";
import {
  RefreshCw, ExternalLink, Plus, Star, ThumbsUp, ThumbsDown, Newspaper, BarChart3, Settings2, ShoppingCart, Link2, Sparkles,
  Radio, Wifi, WifiOff, TrendingUp, TrendingDown,
} from "lucide-react";

export default function StockDetailPage() {
  const p = useParams<{ exchange: string; ticker: string }>();
  const exchange = p.exchange.toLowerCase();
  const ticker = p.ticker.toUpperCase();
  const [refreshing, setRefreshing] = useState(false);
  const [overriding, setOverriding] = useState(false);
  const [ordering, setOrdering] = useState(false);
  const [mapping, setMapping] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const { user } = useAuth();

  const { data: stock } = useSWR(
    ["stock", exchange, ticker],
    () => api.stockDetail(exchange, ticker),
    { refreshInterval: 60_000 },
  );
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
          <div className="mt-2 flex items-baseline gap-3 flex-wrap">
            <div className="text-3xl font-semibold font-mono">
              {fmtPrice(stock.current_price ?? stock.last_close, stock.currency)}
            </div>
            <div className={`text-sm font-mono ${changeColor(stock.change_pct ?? stock.last_change_pct)}`}>
              {fmtPercent(stock.change_pct ?? stock.last_change_pct)}
            </div>
            {stock.price_source === "broker" && (
              <span className="badge bg-brand/15 text-brand text-[10px] uppercase tracking-wider">
                <Radio className="size-2.5 mr-1 inline" /> Live
              </span>
            )}
            {score && <VerdictBadge verdict={score.verdict} size="md" />}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </button>
          {user?.is_admin && (
            <button className="btn-ghost" onClick={() => setOverriding(true)}>
              <Settings2 className="size-4" /> Override
            </button>
          )}
          {user?.is_admin && (
            <button className="btn-ghost" onClick={() => setMapping(true)}>
              <Link2 className="size-4" /> Map symbol
            </button>
          )}
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
          <button className="btn-ghost" onClick={() => setAnalyzing(true)}>
            <Sparkles className="size-4" /> Analyze stock
          </button>
          <button className="btn-primary" onClick={() => setOrdering(true)}>
            <ShoppingCart className="size-4" /> Place order
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr,360px] gap-5">
        {/* Left column - chart + news */}
        <div className="space-y-5">
          <BrokerQuoteCard
            stockId={stock.id}
            currency={stock.currency}
            exchange={exchange}
            ticker={ticker}
          />
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold flex items-center gap-2"><BarChart3 className="size-4" /> 6-month price</h3>
              <div className="text-xs text-ink-muted">
                52w: {fmtPrice(stock.week_52_low, stock.currency)} – {fmtPrice(stock.week_52_high, stock.currency)}
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
                    formatter={(v: any) => [fmtPrice(Number(v), stock.currency), "Close"]}
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
                    <div className="flex items-center gap-2 shrink-0">
                      {n.sentiment_label && (
                        <span className={sentimentBadgeClass(n.sentiment_label)} title={
                          n.sentiment_score != null ? `Confidence: ${n.sentiment_score.toFixed(2)}` : undefined
                        }>
                          {n.sentiment_label}
                        </span>
                      )}
                      {n.url && <ExternalLink className="size-3 text-ink-dim mt-1" />}
                    </div>
                  </div>
                  <div className="text-xs text-ink-dim mt-1 flex items-center gap-2">
                    <span>{fmtDate(n.news_date)}</span>
                    {n.source_code && <><span>·</span><span>{n.source_code}</span></>}
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
              <Stat label="50d SMA" value={fmtPrice(stock.sma_50, stock.currency)} />
              <Stat label="200d SMA" value={fmtPrice(stock.sma_200, stock.currency)} />
              <Stat label="Analyst tgt" value={fmtPrice(stock.analyst_target, stock.currency)} />
              <Stat label="Upside" value={stock.analyst_upside_pct != null ? fmtPercent(stock.analyst_upside_pct) : "—"} />
              <Stat label="Analysts" value={fmtNumber(stock.analyst_count, { digits: 0 })} />
              <Stat label="Rating" value={stock.analyst_rating || "—"} />
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

      {overriding && stock && user?.is_admin && (
        <OverrideModal
          exchange={exchange}
          ticker={ticker}
          currency={stock.currency || ""}
          currentPrice={stock.last_close}
          currentTarget={stock.analyst_target}
          currentRating={stock.analyst_rating}
          currentCount={stock.analyst_count}
          onClose={() => setOverriding(false)}
          onSaved={() => {
            mutate(["stock", exchange, ticker]);
            mutate(["score", exchange, ticker]);
            setOverriding(false);
          }}
        />
      )}

      {ordering && stock && (
        <PlaceOrderModal
          stockId={stock.id}
          ticker={stock.ticker}
          companyName={stock.company_name}
          currency={stock.currency || ""}
          lastClose={stock.last_close}
          onClose={() => setOrdering(false)}
          onSaved={() => { setOrdering(false); }}
        />
      )}

      {mapping && stock && user?.is_admin && (
        <InstrumentMapModal
          stockId={stock.id}
          ticker={stock.ticker}
          companyName={stock.company_name}
          onClose={() => setMapping(false)}
        />
      )}
      <AIAnalysisModal
        open={analyzing}
        onClose={() => setAnalyzing(false)}
        scope="stock"
        stock={stock as any}
      />
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

function OverrideModal({
  exchange, ticker, currency, currentPrice, currentTarget, currentRating, currentCount,
  onClose, onSaved,
}: {
  exchange: string; ticker: string;
  currency: string;
  currentPrice: number | null;
  currentTarget: number | null;
  currentRating: string | null;
  currentCount: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [price, setPrice] = useState<string>(currentPrice?.toString() ?? "");
  const [cur, setCur] = useState<string>(currency);
  const [target, setTarget] = useState<string>(currentTarget?.toString() ?? "");
  const [count, setCount] = useState<string>(currentCount?.toString() ?? "");
  const [rating, setRating] = useState<string>(currentRating ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    const payload: any = {};
    if (price && price !== currentPrice?.toString()) payload.last_close = Number(price);
    if (cur && cur !== currency) payload.currency = cur.toUpperCase();
    if (target && target !== currentTarget?.toString()) payload.analyst_target = Number(target);
    if (count !== "" && count !== (currentCount?.toString() ?? "")) payload.analyst_count = Number(count);
    if (rating && rating !== (currentRating ?? "")) payload.analyst_rating = rating;

    if (Object.keys(payload).length === 0) {
      setError("No changes to save");
      return;
    }
    setSubmitting(true);
    try {
      await api.adminOverrideStock(exchange, ticker, payload);
      onSaved();
    } catch (e: any) {
      setError(e.message || "Failed to save");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-1">Manual override · {ticker}</h3>
        <p className="text-xs text-ink-dim mb-4">
          Admin-only. The stock will be re-scored automatically after saving.
        </p>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Current price</label>
              <input type="number" step="0.0001" className="input mt-1"
                     value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
            <div>
              <label className="label">Currency</label>
              <input type="text" maxLength={8} className="input mt-1 uppercase"
                     value={cur} onChange={(e) => setCur(e.target.value)} placeholder="AED" />
            </div>
          </div>
          <div className="border-t border-border pt-3 mt-1">
            <div className="text-xs text-ink-dim mb-2 uppercase tracking-wider">Analyst consensus</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Target price</label>
                <input type="number" step="0.0001" className="input mt-1"
                       value={target} onChange={(e) => setTarget(e.target.value)} />
              </div>
              <div>
                <label className="label"># of analysts</label>
                <input type="number" min="0" step="1" className="input mt-1"
                       value={count} onChange={(e) => setCount(e.target.value)} />
              </div>
              <div className="col-span-2">
                <label className="label">Rating</label>
                <select className="input mt-1" value={rating} onChange={(e) => setRating(e.target.value)}>
                  <option value="">— unchanged —</option>
                  <option value="Strong Buy">Strong Buy</option>
                  <option value="Buy">Buy</option>
                  <option value="Hold">Hold</option>
                  <option value="Sell">Sell</option>
                  <option value="Strong Sell">Strong Sell</option>
                </select>
              </div>
            </div>
          </div>
          {error && <div className="text-sm text-verdict-avoid">{error}</div>}
          <div className="flex gap-2 justify-end pt-2">
            <button className="btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
            <button className="btn-primary" onClick={submit} disabled={submitting}>
              {submitting ? "Saving…" : "Save & rescore"}
            </button>
          </div>
        </div>
      </div>
    </div>
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


/* ============================================================================
   PlaceOrderModal — order placement for any account, manual or automated.
   ============================================================================ */
function PlaceOrderModal({
  stockId, ticker, companyName, currency, lastClose, onClose, onSaved,
}: {
  stockId: number;
  ticker: string;
  companyName: string;
  currency: string;
  lastClose: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { data: accounts } = useSWR("accounts", () => api.listAccounts());
  const { data: instruments } = useSWR(["instruments", stockId], () => api.instrumentsForStock(stockId));

  const [accountId, setAccountId] = useState<number | "">("");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "STOP">("MARKET");
  const [quantity, setQuantity] = useState<string>("");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultPrice = lastClose ? String(lastClose) : "";

  const tradeableMap = new Map<number, { tradeable: boolean; brokerSymbol: string | null }>();
  (accounts || []).forEach(acct => {
    if (acct.broker_kind === "manual") {
      tradeableMap.set(acct.id, { tradeable: true, brokerSymbol: null });
      return;
    }
    const match = (instruments || []).find(i => i.broker_code === acct.broker_code);
    tradeableMap.set(acct.id, {
      tradeable: !!match,
      brokerSymbol: match ? match.broker_symbol : null,
    });
  });

  const selectedAcct = accounts?.find(a => a.id === accountId);
  const selectedTradeable = accountId ? tradeableMap.get(Number(accountId)) : null;

  async function submit() {
    setError(null);
    if (!accountId) { setError("Pick an account"); return; }
    if (!quantity || Number(quantity) <= 0) { setError("Quantity must be > 0"); return; }
    if ((orderType === "LIMIT" || orderType === "STOP") && !limitPrice) {
      setError(`${orderType} order needs a price`);
      return;
    }
    setSubmitting(true);
    try {
      await api.placeOrder({
        account_id: Number(accountId),
        stock_id: stockId,
        broker_symbol: selectedTradeable?.brokerSymbol || undefined,
        side, order_type: orderType,
        quantity: Number(quantity),
        limit_price: limitPrice ? Number(limitPrice) : undefined,
        stop_loss: stopLoss ? Number(stopLoss) : undefined,
        take_profit: takeProfit ? Number(takeProfit) : undefined,
        notes: notes.trim() || undefined,
      });
      onSaved();
    } catch (e: any) {
      setError(e.message || "Order failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold mb-1">Place order · {ticker}</h3>
        <p className="text-xs text-ink-dim mb-4">{companyName}</p>

        <div className="space-y-3">
          <div>
            <label className="label">Account</label>
            {!accounts?.length ? (
              <div className="text-sm text-ink-muted mt-1">
                No accounts yet. Add one in <a href="/profile" className="underline">Profile</a>.
              </div>
            ) : (
              <select className="input mt-1" value={accountId}
                      onChange={e => setAccountId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— Select an account —</option>
                {accounts.map(a => {
                  const m = tradeableMap.get(a.id);
                  const ok = m?.tradeable;
                  return (
                    <option key={a.id} value={a.id} disabled={!ok}>
                      {a.label} ({a.broker_name}) {!ok ? "— not tradeable here" : ""}
                    </option>
                  );
                })}
              </select>
            )}
            {selectedAcct && selectedTradeable && (
              <div className="text-xs text-ink-dim mt-1">
                {selectedAcct.broker_kind === "manual"
                  ? "Manual account — this order will be recorded as filled."
                  : (selectedTradeable.brokerSymbol
                      ? <>Will route as <code className="px-1 rounded bg-bg-elevated">{selectedTradeable.brokerSymbol}</code> on {selectedAcct.broker_name}.</>
                      : "This stock isn't mapped to a broker symbol on this account.")
                }
              </div>
            )}
          </div>

          <div>
            <label className="label">Side</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <button type="button"
                      className={`btn-ghost justify-center ${side === "BUY" ? "ring-2 ring-verdict-buy" : ""}`}
                      onClick={() => setSide("BUY")}>BUY</button>
              <button type="button"
                      className={`btn-ghost justify-center ${side === "SELL" ? "ring-2 ring-verdict-avoid" : ""}`}
                      onClick={() => setSide("SELL")}>SELL</button>
            </div>
          </div>

          <div>
            <label className="label">Order type</label>
            <div className="grid grid-cols-3 gap-2 mt-1">
              {(["MARKET", "LIMIT", "STOP"] as const).map(t => (
                <button key={t} type="button"
                        className={`btn-ghost justify-center ${orderType === t ? "ring-2 ring-brand" : ""}`}
                        onClick={() => {
                          setOrderType(t);
                          if (t !== "MARKET" && !limitPrice) setLimitPrice(defaultPrice);
                        }}>{t}</button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Quantity</label>
              <input type="number" min="0" step="0.0001" className="input mt-1"
                     value={quantity} onChange={e => setQuantity(e.target.value)} />
            </div>
            {orderType !== "MARKET" && (
              <div>
                <label className="label">{orderType} price{currency && ` (${currency})`}</label>
                <input type="number" step="0.0001" className="input mt-1"
                       value={limitPrice} onChange={e => setLimitPrice(e.target.value)} />
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Stop loss (optional)</label>
              <input type="number" step="0.0001" className="input mt-1"
                     value={stopLoss} onChange={e => setStopLoss(e.target.value)} />
            </div>
            <div>
              <label className="label">Take profit (optional)</label>
              <input type="number" step="0.0001" className="input mt-1"
                     value={takeProfit} onChange={e => setTakeProfit(e.target.value)} />
            </div>
          </div>

          <div>
            <label className="label">Notes (optional)</label>
            <input type="text" className="input mt-1" maxLength={200}
                   value={notes} onChange={e => setNotes(e.target.value)} />
          </div>

          {error && <div className="text-sm text-verdict-avoid">{error}</div>}
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <button className="btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={submitting || !accountId}>
            {submitting ? "Placing…" : `Place ${side} order`}
          </button>
        </div>
      </div>
    </div>
  );
}


/* ============================================================================
   InstrumentMapModal — admin: map this stock to a broker symbol.
   ============================================================================ */
function InstrumentMapModal({
  stockId, ticker, companyName, onClose,
}: { stockId: number; ticker: string; companyName: string; onClose: () => void }) {
  const { data: brokers } = useSWR("brokers", () => api.listBrokers());
  const { data: existing, mutate: refreshExisting } = useSWR(
    ["instruments", stockId], () => api.instrumentsForStock(stockId),
  );

  const [brokerCode, setBrokerCode] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("");
  const [searchQ, setSearchQ] = useState<string>(companyName.split(" ")[0] || ticker);
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosenBroker = brokers?.find(b => b.code === brokerCode);

  async function runSearch() {
    if (!brokerCode || chosenBroker?.kind !== "automated") {
      setSearchResults([]);
      return;
    }
    setSearching(true); setError(null);
    try {
      const r = await api.searchBrokerInstruments(brokerCode, searchQ);
      setSearchResults(r);
    } catch (e: any) {
      setError(e.message || "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function save(useSymbol?: string) {
    setError(null);
    const sym = (useSymbol || symbol).trim();
    if (!brokerCode || !sym) { setError("Broker and symbol are required"); return; }
    setSubmitting(true);
    try {
      await api.upsertInstrument({
        broker_code: brokerCode,
        broker_symbol: sym,
        stock_id: stockId,
        is_tradeable: true,
      });
      setSymbol("");
      refreshExisting();
    } catch (e: any) {
      setError(e.message || "Save failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(broker_code: string, broker_symbol: string) {
    if (!confirm(`Remove ${broker_code}:${broker_symbol} mapping?`)) return;
    await api.deleteInstrument(broker_code, broker_symbol);
    refreshExisting();
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold mb-1">Broker symbol mapping · {ticker}</h3>
        <p className="text-xs text-ink-dim mb-4">
          Map this stock to a broker's instrument so users can place orders on it.
        </p>

        <div className="mb-5">
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-2">Current mappings</div>
          {existing?.length === 0 ? (
            <div className="text-sm text-ink-muted">No mappings yet — add one below.</div>
          ) : (
            <div className="space-y-1">
              {existing?.map(m => (
                <div key={`${m.broker_code}-${m.broker_symbol}`}
                     className="flex items-center justify-between rounded-md bg-bg-subtle px-3 py-2">
                  <div className="text-sm">
                    <span className="font-medium">{m.broker_name}</span>
                    {" → "}
                    <code className="px-1.5 py-0.5 rounded bg-bg-elevated text-xs">{m.broker_symbol}</code>
                    {m.currency && <span className="text-ink-dim ml-2 text-xs">{m.currency}</span>}
                  </div>
                  <button className="btn-ghost" onClick={() => remove(m.broker_code, m.broker_symbol)}>Remove</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-border pt-4">
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-2">Add mapping</div>
          <div className="space-y-3">
            <div>
              <label className="label">Broker</label>
              <select className="input mt-1" value={brokerCode}
                      onChange={e => { setBrokerCode(e.target.value); setSearchResults([]); }}>
                <option value="">— Select broker —</option>
                {brokers?.map(b => (
                  <option key={b.code} value={b.code}>{b.name} ({b.kind})</option>
                ))}
              </select>
            </div>

            {chosenBroker?.kind === "automated" && (
              <div>
                <label className="label">Search broker catalog</label>
                <div className="flex gap-2 mt-1">
                  <input type="text" className="input flex-1" value={searchQ}
                         onChange={e => setSearchQ(e.target.value)}
                         placeholder="Company name or ticker" />
                  <button className="btn-ghost" onClick={runSearch} disabled={searching}>
                    {searching ? "…" : "Search"}
                  </button>
                </div>
                {searchResults.length > 0 && (
                  <div className="mt-2 max-h-44 overflow-y-auto rounded-md border border-border">
                    {searchResults.map(r => (
                      <button key={r.broker_symbol} type="button"
                              className="w-full text-left px-3 py-2 text-sm hover:bg-bg-elevated border-b border-border last:border-0"
                              onClick={() => save(r.broker_symbol)}
                              disabled={submitting}>
                        <div className="flex items-center justify-between">
                          <span><code className="text-xs px-1 rounded bg-bg-elevated">{r.broker_symbol}</code> · {r.name}</span>
                          <span className="text-xs text-ink-dim">{r.instrument_type} {r.currency && `· ${r.currency}`}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="label">Or enter symbol manually</label>
              <div className="flex gap-2 mt-1">
                <input type="text" className="input flex-1" value={symbol}
                       onChange={e => setSymbol(e.target.value)}
                       placeholder="e.g. AAPL, GOLD" />
                <button className="btn-primary" onClick={() => save()} disabled={submitting}>Save</button>
              </div>
            </div>

            {error && <div className="text-sm text-verdict-avoid">{error}</div>}
          </div>
        </div>

        <div className="flex justify-end mt-5">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}


/* ----------------------------------------------------------------------------
   BrokerQuoteCard — live bid/offer/OHLC from connected brokers (Capital.com).

   Hidden entirely if the stock has no broker mapping (most stocks won't, by
   design — only stocks the admin has explicitly mapped). Auto-refresh every
   60s. Manual refresh button hits POST /stocks/{id}/broker_quotes/refresh.
   ----------------------------------------------------------------------------*/
function BrokerQuoteCard({
  stockId, currency, exchange, ticker,
}: {
  stockId: number;
  currency: string | null;
  exchange: string;
  ticker: string;
}) {
  const { data: quotes, isLoading, mutate: reload } = useSWR(
    ["broker-quotes", stockId],
    () => api.listBrokerQuotes(stockId),
    { refreshInterval: 60_000 },
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  async function refresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const result = await api.refreshBrokerQuotes(stockId);
      if (result.refreshed.length === 0 && result.failed.length > 0) {
        setRefreshError("Broker reachable but no fresh data — try again in a minute.");
      }
      reload();
      // The header reads the unified price (which uses the broker quote when
      // available), so invalidate the parent stock query too.
      mutate(["stock", exchange, ticker]);
    } catch (e: any) {
      const msg = String(e.message || e);
      if (msg.includes("409") || msg.toLowerCase().includes("mapping")) {
        setRefreshError("This stock isn't mapped to any broker yet. Use 'Map symbol' to link it.");
      } else {
        setRefreshError(msg);
      }
    } finally {
      setRefreshing(false);
    }
  }

  // Loading first time: render a slim skeleton card so layout doesn't pop.
  if (isLoading) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="h-4 w-32 bg-bg-elevated rounded" />
      </div>
    );
  }

  // No mapping at all: don't render the card. Hidden gracefully.
  if (!quotes || quotes.length === 0) {
    return null;
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Radio className="size-4 text-brand" /> Live broker quote
        </h3>
        <button onClick={refresh} disabled={refreshing} className="btn-ghost text-xs">
          <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {refreshError && (
        <div className="text-xs text-verdict-avoid mb-2">{refreshError}</div>
      )}

      <div className="space-y-3">
        {quotes.map(q => (
          <BrokerQuoteRow key={`${q.broker_id}-${q.broker_symbol}`} q={q} stockCurrency={currency} />
        ))}
      </div>
    </div>
  );
}


function BrokerQuoteRow({ q, stockCurrency }: { q: BrokerQuoteData; stockCurrency: string | null }) {
  const isOpen = (q.market_status || "").toUpperCase().includes("TRADEABLE")
              || (q.market_status || "").toUpperCase() === "OPEN"
              || (q.market_status || "").toUpperCase() === "TRADEABLE_ALL";
  const cur = q.currency || stockCurrency || "";

  // Spread (offer - bid). Useful for traders.
  const bid = q.bid ? Number(q.bid) : null;
  const offer = q.offer ? Number(q.offer) : null;
  const spread = (bid !== null && offer !== null) ? offer - bid : null;

  return (
    <div className="border border-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{q.broker_name || `Broker #${q.broker_id}`}</span>
          <span className="text-[10px] uppercase tracking-wider text-ink-dim font-mono">{q.broker_symbol}</span>
          <span className={`badge ${isOpen
            ? "bg-verdict-buy/15 text-verdict-buy"
            : "bg-bg-elevated text-ink-muted"}`}>
            {isOpen ? <Wifi className="size-2.5 mr-1 inline" /> : <WifiOff className="size-2.5 mr-1 inline" />}
            {q.market_status || "—"}
          </span>
        </div>
        <span className="text-[10px] text-ink-dim">{fmtDate(q.fetched_at)}</span>
      </div>

      {/* Trading details only — header above shows the unified price.
          The broker quote's own change %/absolute is intentionally NOT shown
          here because Capital.com's percentageChange/netChange can be measured
          against day-open (not prev close), causing display inconsistencies
          with the header's prev-close-based change. The header is canonical. */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Cell label="Bid" value={bid !== null ? fmtPrice(bid, cur) : "—"} />
        <Cell label="Offer" value={offer !== null ? fmtPrice(offer, cur) : "—"} />
        <Cell label="Day high" value={q.high_price ? fmtPrice(Number(q.high_price), cur) : "—"} />
        <Cell label="Day low" value={q.low_price ? fmtPrice(Number(q.low_price), cur) : "—"} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 pt-3 border-t border-border">
        {q.last_price && <Cell label="Last (broker)" value={fmtPrice(Number(q.last_price), cur)} />}
        {spread !== null && <Cell label="Spread" value={spread.toFixed(4)} />}
        {q.open_price && <Cell label="Open" value={fmtPrice(Number(q.open_price), cur)} />}
        {q.volume && <Cell label="Volume" value={Number(q.volume).toLocaleString()} />}
      </div>
    </div>
  );
}


function Cell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-dim">{label}</div>
      <div className="font-mono text-sm mt-0.5">{value}</div>
    </div>
  );
}
