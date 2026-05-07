"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { fmtNumber, fmtPercent, fmtPrice, changeColor } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import { Plus, Trash2, Star, X } from "lucide-react";

export default function WatchlistsPage() {
  const { data: lists, isLoading } = useSWR("watchlists", api.listWatchlists);
  const [adding, setAdding] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);

  const active = lists?.find((l) => l.id === (activeId ?? lists?.[0]?.id));

  async function createList() {
    const name = prompt("Watchlist name:");
    if (!name) return;
    await api.createWatchlist(name);
    mutate("watchlists");
  }

  async function removeItem(itemId: number) {
    if (!active) return;
    await api.removeWatchlistItem(active.id, itemId);
    mutate("watchlists");
  }

  async function deleteList(id: number) {
    if (!confirm("Delete this watchlist?")) return;
    await api.deleteWatchlist(id);
    setActiveId(null);
    mutate("watchlists");
  }

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Watchlists</h1>
          <p className="text-ink-muted text-sm mt-1">Group ideas to track daily without owning them.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={createList} className="btn-ghost"><Plus className="size-4" /> New list</button>
          <button onClick={() => setAdding(true)} className="btn-primary" disabled={!active}>
            <Plus className="size-4" /> Add stock
          </button>
        </div>
      </header>

      {isLoading && <div className="text-ink-muted">Loading…</div>}

      {lists && lists.length === 0 && (
        <div className="card p-10 text-center text-ink-muted text-sm">
          No watchlists yet. Click <strong className="text-ink">New list</strong> to create one.
        </div>
      )}

      {lists && lists.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2">
            {lists.map((l) => (
              <button key={l.id} onClick={() => setActiveId(l.id)}
                      className={`px-3 py-1.5 rounded-lg text-sm border ${
                        (activeId ?? lists[0].id) === l.id
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-border bg-bg-card text-ink-muted hover:text-ink"
                      }`}>
                <Star className="size-3.5 inline mr-1.5" />
                {l.name}
                <span className="text-xs ml-2 opacity-70">{l.items.length}</span>
              </button>
            ))}
          </div>

          {active && (
            <div className="card overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="font-medium">{active.name}</div>
                <button onClick={() => deleteList(active.id)} className="text-ink-muted hover:text-verdict-avoid text-sm flex items-center gap-1">
                  <Trash2 className="size-4" /> Delete list
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[700px]">
                  <thead className="text-xs text-ink-muted bg-bg-subtle">
                    <tr>
                      <th className="text-left p-3">Stock</th>
                      <th className="text-right p-3">Price</th>
                      <th className="text-right p-3">Change</th>
                      <th className="text-right p-3">RSI</th>
                      <th className="text-right p-3">Score</th>
                      <th className="text-right p-3">Verdict</th>
                      <th className="p-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.items.map((item) => (
                      <tr key={item.id} className="table-row">
                        <td className="p-3">
                          <Link href={`/stock/${item.stock.exchange_code}/${item.stock.ticker}`} className="hover:text-brand">
                            <div className="font-medium">{item.stock.ticker} <span className="text-ink-dim text-xs">·{item.stock.exchange_code.toUpperCase()}</span></div>
                            <div className="text-xs text-ink-muted truncate max-w-[260px]">{item.stock.company_name}</div>
                          </Link>
                        </td>
                        <td className="p-3 text-right font-mono">{fmtPrice(item.stock.last_close, item.stock.currency)}</td>
                        <td className={`p-3 text-right font-mono ${changeColor(item.stock.last_change_pct)}`}>{fmtPercent(item.stock.last_change_pct)}</td>
                        <td className="p-3 text-right font-mono">{fmtNumber(item.stock.rsi_14, { digits: 1 })}</td>
                        <td className="p-3 text-right font-mono font-semibold">{fmtNumber(item.stock.composite_score, { digits: 0 })}</td>
                        <td className="p-3 text-right"><VerdictBadge verdict={item.stock.verdict} size="xs" /></td>
                        <td className="p-3 text-right">
                          <button onClick={() => removeItem(item.id)} className="text-ink-muted hover:text-verdict-avoid">
                            <X className="size-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {active.items.length === 0 && (
                      <tr><td colSpan={7} className="p-8 text-center text-ink-muted text-sm">Empty list. Click Add stock.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {adding && active && <AddStockModal listId={active.id} onClose={() => setAdding(false)} />}
    </div>
  );
}

function AddStockModal({ listId, onClose }: { listId: number; onClose: () => void }) {
  const [q, setQ] = useState("");
  const { data: search } = useSWR(q.length >= 2 ? ["search-wl", q] : null, () => api.screener({ q, limit: 10 }));

  async function add(stockId: number) {
    try {
      await api.addWatchlistItem(listId, stockId);
      mutate("watchlists");
      onClose();
    } catch (e: any) { alert(e.message); }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-4">Add to watchlist</h3>
        <input className="input" autoFocus placeholder="Search ticker or company" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="mt-3 max-h-72 overflow-y-auto space-y-1">
          {search?.items.map((s) => (
            <button key={s.id} onClick={() => add(s.id)}
                    className="w-full text-left px-3 py-2 rounded-md hover:bg-bg-elevated">
              <div className="text-sm font-medium">{s.ticker} <span className="text-ink-dim text-xs">·{s.exchange_code.toUpperCase()}</span></div>
              <div className="text-xs text-ink-muted truncate">{s.company_name}</div>
            </button>
          ))}
          {q.length >= 2 && search && search.items.length === 0 && (
            <div className="text-sm text-ink-muted text-center py-4">No matches.</div>
          )}
        </div>
        <div className="flex justify-end pt-3">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
