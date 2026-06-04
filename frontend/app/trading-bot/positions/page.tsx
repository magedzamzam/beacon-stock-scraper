"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  Activity, RefreshCw, X, TrendingUp, TrendingDown, ChevronDown, AlertCircle,
  Target, Move3D, Loader2, CheckCircle2, Bot,
} from "lucide-react";
import { api, type TgBotPositionRow } from "@/lib/api";

/**
 * /trading-bot/positions — read-only by default, action-laden via dropdowns.
 *
 * Filtered to positions opened by THIS USER'S bot trades only. The same
 * Capital.com account may have manual positions on the same symbol — we
 * deliberately don't list them here (manual positions belong on the
 * Portfolio screen).
 *
 * Actions per position:
 *   - Close
 *   - Move SL to entry  (= breakeven; server computes from avg_open_price)
 *   - Move SL to X      (= prompt for number; client passes it through)
 *
 * Bulk action: "Close all for signal N" — only available when grouped by
 * signal. Closes every bot position linked to that signal on the chosen
 * account. Does NOT touch manual positions or positions from other signals.
 */
export default function BotPositionsPage() {
  const { data: positions, error, isLoading, mutate } = useSWR(
    "trading-bot:positions",
    () => api.tgBotPositions({ refresh: false }),
    { refreshInterval: 10_000 },
  );
  const [refreshing, setRefreshing] = useState(false);

  async function hardRefresh() {
    // refresh=true asks the API to pull from broker_gateway first. Slow but
    // necessary after closing positions to see them disappear immediately.
    setRefreshing(true);
    try {
      const fresh = await api.tgBotPositions({ refresh: true });
      mutate(fresh, { revalidate: false });
    } catch (e) {
      // Fall through — keep showing cached data.
    } finally {
      setRefreshing(false);
    }
  }

  // Group by signal so the bulk-close action is scoped sanely.
  const grouped = useMemo(() => {
    if (!positions) return [];
    const by = new Map<string, {
      label: string;
      signal_id: number | null;
      account_id: number;
      rows: TgBotPositionRow[];
    }>();
    for (const p of positions) {
      // One group per (signal_id, account_id) pair. The same signal can
      // be traded on multiple accounts.
      const key = `${p.signal.id ?? "no-signal"}::${p.account.account_id}`;
      if (!by.has(key)) {
        by.set(key, {
          label: p.signal
            ? `${p.signal.channel_title ?? "Signal"} · ${p.signal.direction}` +
              ` · ${new Date(p.signal.signal_time ?? "").toLocaleString()}`
            : "Unlinked positions",
          signal_id: p.signal.id,
          account_id: p.account.account_id,
          rows: [],
        });
      }
      by.get(key)!.rows.push(p);
    }
    return Array.from(by.values());
  }, [positions]);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Activity className="size-6" /> Bot positions
          </h1>
          <p className="text-ink-muted text-sm mt-1">
            Live positions and pending orders opened by the bot.
            <Link href="/trading-bot" className="ml-2 text-brand hover:underline">
              ← Back to signals
            </Link>
          </p>
        </div>
        <button onClick={hardRefresh} disabled={refreshing} className="btn-ghost text-xs">
          <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh from broker"}
        </button>
      </header>

      {error && (
        <div className="text-sm text-rose-500 flex items-center gap-2 p-3 border border-rose-500/30 rounded bg-rose-500/5">
          <AlertCircle className="size-4" /> {String(error.message || error)}
        </div>
      )}

      {!error && !isLoading && positions?.length === 0 && (
        <div className="card p-8 text-center text-sm text-ink-muted">
          <Bot className="size-8 mx-auto mb-2 text-ink-dim" />
          No open bot positions. They appear here within seconds of placing trades
          from a signal.
        </div>
      )}

      {grouped.map(g => (
        <SignalGroup key={`${g.signal_id}-${g.account_id}`}
                     group={g}
                     onAction={() => mutate()} />
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Signal group — header + bulk action + per-position rows
// ---------------------------------------------------------------------------
function SignalGroup({ group, onAction }: {
  group: { label: string; signal_id: number | null; account_id: number; rows: TgBotPositionRow[] };
  onAction: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const totalPl = group.rows.reduce(
    (s, p) => s + (p.unrealized_pl ?? 0), 0,
  );
  const totalQty = group.rows.reduce(
    (s, p) => s + (p.quantity ?? 0), 0,
  );

  async function closeAllForSignal() {
    if (!group.signal_id) return;
    if (!confirm(`Close ALL ${group.rows.length} positions for this signal?`)) return;
    setBusy(true); setError(null);
    try {
      await api.tgCloseManyPositions({
        account_id: group.account_id,
        signal_id: group.signal_id,
      });
      onAction();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card overflow-hidden">
      <header className="flex items-center justify-between p-3 border-b border-border bg-bg-subtle/40">
        <div>
          <div className="text-sm font-medium">{group.label}</div>
          <div className="text-[11px] text-ink-muted mt-0.5">
            {group.rows.length} position{group.rows.length === 1 ? "" : "s"}{" "}
            · total qty <span className="font-mono">{totalQty.toFixed(2)}</span>{" "}
            · P/L{" "}
            <span className={`font-mono ${totalPl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {totalPl.toFixed(2)}
            </span>
          </div>
        </div>
        {group.signal_id && (
          <button onClick={closeAllForSignal} disabled={busy}
                  className="text-xs px-2 py-1 rounded border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 disabled:opacity-50">
            {busy ? <Loader2 className="size-3 inline animate-spin" /> : <X className="size-3 inline" />}
            {" "}Close all for signal
          </button>
        )}
      </header>

      {error && (
        <div className="px-3 py-2 text-xs text-rose-400 border-b border-rose-500/30 bg-rose-500/5">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-ink-muted bg-bg-subtle">
            <tr>
              <th className="text-left  px-3 py-2">Symbol</th>
              <th className="text-left  px-3 py-2">TP</th>
              <th className="text-right px-3 py-2">Qty</th>
              <th className="text-right px-3 py-2">Entry</th>
              <th className="text-right px-3 py-2">Now</th>
              <th className="text-right px-3 py-2">SL</th>
              <th className="text-right px-3 py-2">TP price</th>
              <th className="text-right px-3 py-2">P/L</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {group.rows.map(p => (
              <PositionRow key={p.snapshot_id} p={p} onAction={onAction} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}


// ---------------------------------------------------------------------------
// Per-position row with an actions menu
// ---------------------------------------------------------------------------
function PositionRow({ p, onAction }: {
  p: TgBotPositionRow;
  onAction: () => void;
}) {
  const isLong = (p.direction ?? "").toUpperCase() === "LONG";
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function close() {
    if (!confirm(`Close position ${p.broker_position_ref}?`)) return;
    if (!p.broker_position_ref) return;
    setBusy(true);
    try { await api.tgClosePosition(p.broker_position_ref); onAction(); }
    catch (e: any) { alert(e.message); }
    finally { setBusy(false); setMenuOpen(false); }
  }
  async function moveToEntry() {
    if (!p.broker_position_ref) return;
    setBusy(true);
    try { await api.tgMoveSlToEntry(p.broker_position_ref); onAction(); }
    catch (e: any) { alert(e.message); }
    finally { setBusy(false); setMenuOpen(false); }
  }
  async function moveTo() {
    if (!p.broker_position_ref) return;
    const ans = prompt(
      `Move stop loss to what level?\n\n` +
      `Current SL: ${p.stop_loss ?? "(none)"}\n` +
      `Entry: ${p.avg_open_price ?? "?"}\n` +
      `Now: ${p.current_price ?? "?"}`,
      String(p.stop_loss ?? p.avg_open_price ?? ""),
    );
    if (!ans) return;
    const n = Number(ans);
    if (!Number.isFinite(n) || n <= 0) {
      alert("Invalid number");
      return;
    }
    setBusy(true);
    try { await api.tgModifyPosition(p.broker_position_ref, { stop_loss: n }); onAction(); }
    catch (e: any) { alert(e.message); }
    finally { setBusy(false); setMenuOpen(false); }
  }

  const Dir = isLong ? TrendingUp : TrendingDown;
  const dirCls = isLong ? "text-emerald-400" : "text-rose-400";

  return (
    <tr className="border-t border-border hover:bg-bg-subtle/30">
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <Dir className={`size-3.5 ${dirCls}`} />
          <span className="font-mono font-medium">{p.broker_symbol}</span>
        </div>
        <div className="text-[11px] text-ink-dim font-mono mt-0.5">
          {p.broker_position_ref}
        </div>
      </td>
      <td className="px-3 py-2 text-xs">
        <span className="text-ink-muted">{p.bot_trade.tp_level ?? "—"}</span>
      </td>
      <td className="px-3 py-2 text-right font-mono">{fmt(p.quantity, 2)}</td>
      <td className="px-3 py-2 text-right font-mono">{fmt(p.avg_open_price)}</td>
      <td className="px-3 py-2 text-right font-mono">{fmt(p.current_price)}</td>
      <td className="px-3 py-2 text-right font-mono text-rose-400">{fmt(p.stop_loss)}</td>
      <td className="px-3 py-2 text-right font-mono text-emerald-400">{fmt(p.take_profit)}</td>
      <td className={`px-3 py-2 text-right font-mono ${(p.unrealized_pl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
        {fmt(p.unrealized_pl)}
      </td>
      <td className="px-3 py-2 text-right relative">
        <button onClick={() => setMenuOpen(o => !o)} disabled={busy}
                className="btn-ghost text-xs">
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <ChevronDown className="size-3.5" />}
          Actions
        </button>
        {menuOpen && (
          <div className="absolute right-3 top-9 z-20 bg-bg-card border border-border rounded shadow-lg text-xs min-w-[180px]">
            <button onClick={moveToEntry} disabled={busy}
                    className="w-full text-left px-3 py-2 hover:bg-bg-subtle flex items-center gap-2">
              <Target className="size-3.5" /> Move SL to entry
            </button>
            <button onClick={moveTo} disabled={busy}
                    className="w-full text-left px-3 py-2 hover:bg-bg-subtle flex items-center gap-2">
              <Move3D className="size-3.5" /> Move SL to…
            </button>
            <div className="border-t border-border" />
            <button onClick={close} disabled={busy}
                    className="w-full text-left px-3 py-2 hover:bg-rose-500/10 text-rose-400 flex items-center gap-2">
              <X className="size-3.5" /> Close position
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}


function fmt(n: number | null | undefined, digits = 2) {
  if (n == null || !Number.isFinite(n)) return "—";
  return Number(n).toLocaleString(undefined, {
    maximumFractionDigits: 6, minimumFractionDigits: digits,
  });
}
