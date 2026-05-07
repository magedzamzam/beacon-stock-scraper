"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { fmtMoney, fmtNumber, fmtPercent, fmtPrice, changeColor } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import { Plus, Trash2, Briefcase, TrendingUp, Wallet } from "lucide-react";

export default function PortfolioPage() {
  const { data: portfolio, isLoading } = useSWR("portfolio", api.portfolio);
  const [adding, setAdding] = useState(false);

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
          <p className="text-ink-muted text-sm mt-1">Live verdicts on every open position.</p>
        </div>
        <button onClick={() => setAdding(true)} className="btn-primary">
          <Plus className="size-4" /> Add position
        </button>
      </header>

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
                    <button onClick={() => close(p.id)} title="Close" className="text-ink-muted hover:text-verdict-avoid">
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

      {adding && <AddPositionModal onClose={() => setAdding(false)} />}
    </div>
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

function AddPositionModal({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const { data: search } = useSWR(q.length >= 2 ? ["search", q] : null, () => api.screener({ q, limit: 8 }));
  const [picked, setPicked] = useState<any>(null);
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!picked || !qty || !price) return;
    setSubmitting(true);
    try {
      await api.addPosition(picked.id, Number(qty), Number(price), date || undefined);
      mutate("portfolio");
      onClose();
    } catch (e: any) {
      alert(e.message);
    } finally { setSubmitting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-4">Add position</h3>
        <div className="space-y-3">
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
