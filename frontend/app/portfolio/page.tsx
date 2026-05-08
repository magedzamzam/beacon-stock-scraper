"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, type Portfolio } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtPercent, fmtPrice, changeColor, fmtDate } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import { Plus, Trash2, Briefcase, TrendingUp, Wallet, RefreshCw, X } from "lucide-react";

export default function PortfolioPage() {
  const { data: portfolio, isLoading } = useSWR("portfolio", api.portfolio);
  const { data: accounts } = useSWR("accounts", () => api.listAccounts());
  const [adding, setAdding] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<number | null>(null);

  async function close(id: number) {
    if (!confirm("Close this position?")) return;
    await api.closePosition(id);
    mutate("portfolio");
  }

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Portfolio</h1>
          <p className="text-ink-muted text-sm mt-1">
            {selectedAccount === null
              ? "Live verdicts on every open position."
              : "Single-account view: live broker positions or manual records."}
          </p>
        </div>
        <button onClick={() => setAdding(true)} className="btn-primary">
          <Plus className="size-4" /> Add position
        </button>
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedAccount(null)}
          className={`badge ${selectedAccount === null
            ? "bg-brand/15 text-brand ring-1 ring-brand/40"
            : "bg-bg-subtle text-ink-muted hover:bg-bg-elevated"}`}
        >
          All (aggregated)
        </button>
        {accounts?.map(a => (
          <button
            key={a.id}
            onClick={() => setSelectedAccount(a.id)}
            className={`badge ${selectedAccount === a.id
              ? "bg-brand/15 text-brand ring-1 ring-brand/40"
              : "bg-bg-subtle text-ink-muted hover:bg-bg-elevated"}`}
          >
            {a.label}
            <span className="text-[10px] opacity-70 ml-1">· {a.broker_name}</span>
          </button>
        ))}
        {!accounts?.length && (
          <span className="text-xs text-ink-dim self-center">
            No trading accounts yet. <Link href="/profile" className="underline">Add one</Link>.
          </span>
        )}
      </div>

      {selectedAccount !== null ? (
        <AccountView accountId={selectedAccount}
                     account={accounts?.find(a => a.id === selectedAccount)} />
      ) : (
        <PortfolioAggregateView portfolio={portfolio} isLoading={isLoading} onClose={close} />
      )}

      {adding && (
        <AddPositionModal
          onClose={() => setAdding(false)}
          defaultAccountId={selectedAccount}
        />
      )}
    </div>
  );
}

function PortfolioAggregateView({
  portfolio, isLoading, onClose,
}: {
  portfolio: Portfolio | undefined;
  isLoading: boolean;
  onClose: (id: number) => void;
}) {
	return (
    <>
      {portfolio && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <SummaryCard icon={<Wallet className="size-4" />} label="Cost basis" value={fmtMoney(portfolio.total_cost)} />
          <SummaryCard icon={<Briefcase className="size-4" />} label="Market value" value={fmtMoney(portfolio.total_value)} />
          <SummaryCard
            icon={<TrendingUp className="size-4" />}
            label="Unrealized P/L"
            value={fmtMoney(portfolio.total_pl)}
            sub={fmtPercent(portfolio.total_pl_pct)}
            color={portfolio.total_pl >= 0 ? "text-verdict-buy" : "text-verdict-avoid"}
          />
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Stock</th>
                <th className="text-right p-3">Qty</th>
                <th className="text-right p-3">Entry</th>
                <th className="text-right p-3">Current</th>
                <th className="text-right p-3">P/L</th>
                <th className="text-right p-3">Stock</th>
                <th className="text-right p-3">Action</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={8} className="p-10 text-center text-ink-muted">Loading…</td></tr>
              )}
              {portfolio?.positions.map((p) => (
                <tr key={p.id} className="table-row">
                  <td className="p-3">
                    <Link href={`/stock/${p.stock.exchange_code}/${p.stock.ticker}`} className="hover:text-brand">
                      <div className="font-medium">{p.stock.ticker} <span className="text-ink-dim text-xs">·{p.stock.exchange_code.toUpperCase()}</span></div>
                      <div className="text-xs text-ink-muted truncate max-w-[260px]">{p.stock.company_name}</div>
                    </Link>
                  </td>
                  <td className="p-3 text-right font-mono">{fmtNumber(p.quantity, { digits: 0 })}</td>
                  <td className="p-3 text-right font-mono">{fmtPrice(p.avg_entry_price, p.stock.currency)}</td>
                  <td className="p-3 text-right font-mono">{fmtPrice(p.stock.last_close, p.stock.currency)}</td>
                  <td className={`p-3 text-right font-mono ${changeColor(p.unrealized_pl_pct)}`}>
                    <div>{fmtPrice(p.unrealized_pl, p.stock.currency)}</div>
                    <div className="text-xs">{fmtPercent(p.unrealized_pl_pct)}</div>
                  </td>
                  <td className="p-3 text-right"><VerdictBadge verdict={p.stock.verdict} size="xs" /></td>
                  <td className="p-3 text-right">
                    <VerdictBadge verdict={p.position_verdict} size="xs" />
                    {p.position_reasoning && p.position_reasoning.length > 0 && (
                      <div className="text-[10px] text-ink-dim mt-1 max-w-[180px] ml-auto">
                        {p.position_reasoning[0]}
                      </div>
                    )}
                  </td>
                  <td className="p-3 text-right">
                    <button onClick={() => onClose(p.id)} title="Close" className="text-ink-muted hover:text-verdict-avoid">
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {portfolio && portfolio.positions.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-10 text-center text-ink-muted text-sm">
                    No positions yet. Click <strong className="text-ink">Add position</strong> to start tracking.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function SummaryCard({ icon, label, value, sub, color }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-xs text-ink-muted flex items-center gap-2">{icon} {label}</div>
      <div className={`text-xl font-semibold font-mono mt-1 ${color || ""}`}>{value}</div>
      {sub && <div className={`text-xs font-mono mt-0.5 ${color || ""}`}>{sub}</div>}
    </div>
  );
}

function AddPositionModal({
  onClose, defaultAccountId,
}: {
  onClose: () => void;
  defaultAccountId: number | null;
}) {
  const { data: accounts } = useSWR("accounts", () => api.listAccounts());
  // Only manual accounts can hold portfolio_positions rows.
  const manualAccounts = (accounts || []).filter(a => a.broker_kind === "manual");

  // If the user opened the modal from a per-account view that's manual,
  // pre-select it. Otherwise default to "no account" (legacy).
  const initialAcct =
    defaultAccountId && manualAccounts.some(a => a.id === defaultAccountId)
      ? defaultAccountId
      : "";
  const [accountId, setAccountId] = useState<number | "">(initialAcct);

  const [q, setQ] = useState("");
  const { data: search } = useSWR(q.length >= 2 ? ["search", q] : null, () => api.screener({ q, limit: 8 }));
  const [picked, setPicked] = useState<any>(null);
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!picked || !qty || !price) return;
    setSubmitting(true);
    try {
      await api.addPosition(
        picked.id, Number(qty), Number(price),
        date || undefined, undefined,
        accountId ? Number(accountId) : undefined,
      );
      mutate("portfolio");
      // Refresh per-account positions if this position was attached to one.
      if (accountId) mutate(["account-positions", Number(accountId)]);
      onClose();
    } catch (e: any) {
      setError(e.message || "Failed to add position");
    } finally { setSubmitting(false); }
  }

  // Caller informed us the user is on an automated-account chip — not legal here.
  const onAutomatedChip =
    defaultAccountId !== null
    && (accounts || []).some(a => a.id === defaultAccountId && a.broker_kind === "automated");

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-4">Add position</h3>
        <div className="space-y-3">
          <div>
            <label className="label">Account (optional)</label>
            <select className="input mt-1"
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">— No account (legacy) —</option>
              {manualAccounts.map(a => (
                <option key={a.id} value={a.id}>
                  {a.label} ({a.broker_name})
                </option>
              ))}
            </select>
            {onAutomatedChip && (
              <p className="text-[11px] text-verdict-avoid mt-1">
                Automated accounts are populated live from the broker. Pick a manual account or
                place an order from a stock page instead.
              </p>
            )}
            {!onAutomatedChip && manualAccounts.length === 0 && (
              <p className="text-[11px] text-ink-dim mt-1">
                No manual accounts yet. <a href="/profile" className="underline">Add one</a> if you want to attach this position.
              </p>
            )}
          </div>
          <div>
            <label className="label">Search ticker or company</label>
            <input className="input mt-1" autoFocus value={q} onChange={(e) => { setQ(e.target.value); setPicked(null); }} />
            {!picked && search && search.items.length > 0 && (
              <div className="card p-1.5 mt-1 max-h-48 overflow-y-auto">
                {search.items.map((s) => (
                  <button key={s.id} onClick={() => { setPicked(s); setQ(`${s.ticker} — ${s.company_name}`); }}
                          className="w-full text-left px-2 py-1.5 text-sm rounded hover:bg-bg-elevated">
                    <div className="font-medium">{s.ticker} <span className="text-ink-dim text-xs">·{s.exchange_code.toUpperCase()}</span></div>
                    <div className="text-xs text-ink-muted truncate">{s.company_name}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Quantity</label>
              <input type="number" className="input mt-1" value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div>
              <label className="label">Avg entry price</label>
              <input type="number" step="0.0001" className="input mt-1" value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label">Entry date (optional)</label>
            <input type="date" className="input mt-1" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          {error && <div className="text-sm text-verdict-avoid">{error}</div>}
          <div className="flex gap-2 justify-end pt-2">
            <button className="btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn-primary" onClick={submit} disabled={!picked || !qty || !price || submitting}>
              {submitting ? "Adding…" : "Add position"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


/* ----------------------------------------------------------------------------
   AccountView — single-account portfolio.

   For automated accounts: positions come from broker_positions_snapshot
   (refreshed via /accounts/:id/positions). For manual accounts: positions
   come from portfolio_positions filtered by account_id.
   ----------------------------------------------------------------------------*/
function AccountView({ accountId, account }: { accountId: number; account: any }) {
  const [refreshing, setRefreshing] = useState(false);
  const { data: positions, mutate: reloadPositions, isLoading: posLoading } = useSWR(
    ["account-positions", accountId], () => api.accountPositions(accountId),
  );
  const { data: orders, mutate: reloadOrders } = useSWR(
    ["account-orders", accountId], () => api.listOrders(accountId),
  );
  const { data: stats, mutate: reloadStats } = useSWR(
    ["account-stats", accountId], () => api.accountStats(accountId),
  );
  const { data: history } = useSWR(
    ["account-stats-history", accountId], () => api.accountStatsHistory(accountId, 30),
  );

  async function refresh() {
    setRefreshing(true);
    try {
      await api.accountPositions(accountId, true);
      await api.accountStats(accountId, true);
      reloadPositions();
      reloadOrders();
      reloadStats();
    } catch (e) {
      // tolerate — show stale data rather than crash
    } finally {
      setRefreshing(false);
    }
  }

  async function cancelOrder(id: number) {
    if (!confirm("Cancel this order?")) return;
    try {
      await api.cancelOrder(id);
      reloadOrders();
    } catch (e: any) {
      alert(e.message || "Cancel failed");
    }
  }

  const isAutomated = account?.broker_kind === "automated";

  return (
    <div className="space-y-5">
      <div className="card p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim">{account?.broker_name}</div>
          <div className="font-semibold">{account?.label}</div>
        </div>
        <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
          <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          {isAutomated ? " from broker" : ""}
        </button>
      </div>

      {/* Stats card: balance / equity / unrealized P/L + 30-day mini chart */}
      <AccountStatsCard stats={stats} history={history} isAutomated={isAutomated} />

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-border text-xs uppercase tracking-wider text-ink-dim">
          Positions {isAutomated ? "(broker-reported)" : "(manual)"}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Instrument</th>
                <th className="text-right p-3">Qty</th>
                <th className="text-right p-3">Avg open</th>
                <th className="text-right p-3">Current</th>
                <th className="text-right p-3">P/L</th>
                <th className="text-right p-3">Direction</th>
              </tr>
            </thead>
            <tbody>
              {posLoading && <tr><td colSpan={6} className="p-8 text-center text-ink-muted">Loading…</td></tr>}
              {(positions || []).map((p: any, i: number) => (
                <tr key={`${p.broker_symbol}-${i}`} className="table-row">
                  <td className="p-3">
                    {p.ticker ? (
                      <Link href={`/stock/${p.exchange}/${p.ticker}`} className="hover:text-brand">
                        <div className="font-medium">{p.ticker}</div>
                        <div className="text-xs text-ink-muted truncate max-w-[260px]">
                          {p.company_name || p.broker_symbol}
                        </div>
                      </Link>
                    ) : (
                      <>
                        <div className="font-medium">{p.broker_symbol}</div>
                        <div className="text-xs text-ink-dim">Not in screener</div>
                      </>
                    )}
                  </td>
                  <td className="p-3 text-right font-mono">{p.quantity}</td>
                  <td className="p-3 text-right font-mono">{fmtPrice(p.avg_open_price ? Number(p.avg_open_price) : null, p.currency)}</td>
                  <td className="p-3 text-right font-mono">{fmtPrice(p.current_price ? Number(p.current_price) : null, p.currency)}</td>
                  <td className={`p-3 text-right font-mono ${p.unrealized_pl !== null && Number(p.unrealized_pl) < 0 ? "text-verdict-avoid" : "text-verdict-buy"}`}>
                    {fmtPrice(p.unrealized_pl ? Number(p.unrealized_pl) : null, p.currency)}
                  </td>
                  <td className="p-3 text-right text-xs">{p.direction || "—"}</td>
                </tr>
              ))}
              {!posLoading && (positions || []).length === 0 && (
                <tr><td colSpan={6} className="p-8 text-center text-ink-muted text-sm">No open positions on this account.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-border text-xs uppercase tracking-wider text-ink-dim">
          Order history
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Placed</th>
                <th className="text-left p-3">Symbol</th>
                <th className="text-left p-3">Side</th>
                <th className="text-left p-3">Type</th>
                <th className="text-right p-3">Qty</th>
                <th className="text-right p-3">Price</th>
                <th className="text-left p-3">Status</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {(orders || []).map((o: any) => (
                <tr key={o.id} className="table-row">
                  <td className="p-3 text-ink-muted">{fmtDate(o.placed_at)}</td>
                  <td className="p-3 font-mono">{o.broker_symbol || "—"}</td>
                  <td className={`p-3 font-medium ${o.side === "BUY" ? "text-verdict-buy" : "text-verdict-avoid"}`}>{o.side}</td>
                  <td className="p-3 text-ink-muted">{o.order_type}</td>
                  <td className="p-3 text-right font-mono">{o.quantity}</td>
                  <td className="p-3 text-right font-mono">
                    {o.fill_price ?? o.limit_price ?? "—"}
                    {o.currency && <span className="text-ink-dim text-xs ml-1">{o.currency}</span>}
                  </td>
                  <td className="p-3">
                    <OrderStatusBadge status={o.status} reason={o.rejection_reason} />
                  </td>
                  <td className="p-3 text-right">
                    {(o.status === "PENDING" || o.status === "WORKING") && (
                      <button className="text-ink-muted hover:text-verdict-avoid" onClick={() => cancelOrder(o.id)}>
                        <X className="size-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(orders || []).length === 0 && (
                <tr><td colSpan={8} className="p-8 text-center text-ink-muted text-sm">No orders yet on this account.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function OrderStatusBadge({ status, reason }: { status: string; reason: string | null }) {
  const tone =
    status === "FILLED"    ? "bg-verdict-buy/15 text-verdict-buy ring-1 ring-verdict-buy/30" :
    status === "WORKING"   ? "bg-bg-elevated text-ink ring-1 ring-border" :
    status === "PENDING"   ? "bg-bg-elevated text-ink-muted ring-1 ring-border" :
    status === "CANCELLED" ? "bg-bg-elevated text-ink-muted ring-1 ring-border" :
                             "bg-verdict-avoid/15 text-verdict-avoid ring-1 ring-verdict-avoid/30";
  return (
    <span className={`badge ${tone}`} title={reason || undefined}>
      {status}
    </span>
  );
}


/* ----------------------------------------------------------------------------
   AccountStatsCard — balance / equity / unrealized P/L + sparkline.

   The sparkline is a tiny inline SVG (no chart library) plotting equity over
   the last 30 days. It rescales to its own min/max so a small account looks
   the same shape as a large one.
   ----------------------------------------------------------------------------*/
function AccountStatsCard({
  stats, history, isAutomated,
}: {
  stats: any | undefined;
  history: any[] | undefined;
  isAutomated: boolean;
}) {
  if (!stats) {
    return <div className="card p-4 text-sm text-ink-muted">Loading stats…</div>;
  }

  const balance = stats.balance ? Number(stats.balance) : null;
  const equity = stats.equity ? Number(stats.equity) : null;
  const unrealized = stats.unrealized_pl ? Number(stats.unrealized_pl) : null;
  const cur = stats.currency || "";

  // Build the spark from `history` (oldest → newest), preferring equity.
  const points = (history || [])
    .map(h => h.equity ? Number(h.equity) : null)
    .filter((v): v is number => v !== null);

  return (
    <div className="card p-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Metric
          label={isAutomated ? "Balance" : "Balance"}
          value={balance !== null ? fmtMoneyVal(balance, cur) : "—"}
          hint={isAutomated ? "Cash held at broker" : "Manual accounts have no cash balance"}
        />
        <Metric
          label="Equity"
          value={equity !== null ? fmtMoneyVal(equity, cur) : "—"}
          hint="Mark-to-market value"
        />
        <Metric
          label="Unrealized P/L"
          value={unrealized !== null ? fmtMoneyVal(unrealized, cur) : "—"}
          tone={unrealized !== null ? (unrealized >= 0 ? "buy" : "avoid") : undefined}
          hint={`${stats.open_position_count ?? 0} open position${stats.open_position_count === 1 ? "" : "s"}`}
        />
        <div className="md:border-l md:border-border md:pl-4">
          <div className="text-[10px] uppercase tracking-wider text-ink-dim">Equity (30d)</div>
          {points.length >= 2
            ? <Sparkline values={points} className="mt-2" />
            : <div className="text-xs text-ink-muted mt-2">No history yet — re-check after the next snapshot.</div>}
        </div>
      </div>
      <div className="text-[10px] text-ink-dim mt-3">
        Last updated: {fmtDate(stats.fetched_at)} · source {stats.source}
      </div>
    </div>
  );
}


function Metric({
  label, value, hint, tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "buy" | "avoid";
}) {
  const cls =
    tone === "buy"   ? "text-verdict-buy" :
    tone === "avoid" ? "text-verdict-avoid" :
                       "text-ink";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-dim">{label}</div>
      <div className={`text-2xl font-semibold mt-1 font-mono ${cls}`}>{value}</div>
      {hint && <div className="text-[11px] text-ink-dim mt-1">{hint}</div>}
    </div>
  );
}


function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const w = 200, h = 44, pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = (w - 2 * pad) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = values[values.length - 1];
  const first = values[0];
  const stroke = last >= first ? "rgb(34,197,94)" : "rgb(239,68,68)";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={className} preserveAspectRatio="none" style={{ width: "100%", height: 44 }}>
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}


function fmtMoneyVal(n: number, cur: string): string {
  // Compact display: two decimals if small, no decimals if >=1000.
  const opts: Intl.NumberFormatOptions = Math.abs(n) >= 1000
    ? { maximumFractionDigits: 0 }
    : { maximumFractionDigits: 2 };
  return `${cur ? cur + " " : ""}${n.toLocaleString(undefined, opts)}`;
}
