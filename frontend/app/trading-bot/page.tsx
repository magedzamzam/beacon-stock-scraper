"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Bot, ChevronRight, ArrowUp, ArrowDown, AlertCircle,
  RefreshCw, MessageSquare, RadioTower,
} from "lucide-react";
import { api, type TgSignalRow } from "@/lib/api";

/**
 * Trading Bot — Milestone 1.
 *
 * Read-only view of parsed signals from configured Telegram channels.
 * Sidebar (left) lists the most recent signals; selecting one opens a
 * detail pane with the raw message text. Status badge on each row will
 * matter once trade execution lands (Milestone 3) — for now everything
 * stays 'NEW'.
 *
 * Refreshes every 10s via SWR — short enough that new signals appear
 * promptly, long enough not to hammer the API.
 */
export default function TradingBotPage() {
  const { data: signals, mutate, isLoading } = useSWR(
    "trading-bot:signals",
    () => api.tgSignals(100),
    { refreshInterval: 10_000 },
  );

  // Selected signal id for the detail pane. Null = nothing selected.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = signals?.find(s => s.id === selectedId) ?? signals?.[0] ?? null;

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Bot className="size-6" /> Trading Bot
          </h1>
          <p className="text-ink-muted text-sm mt-1">
            Parsed signals from configured Telegram channels.
            Auto-refreshes every 10s.
          </p>
        </div>
        <button onClick={() => mutate()} className="btn-ghost text-xs">
          <RefreshCw className="size-3.5" /> Refresh
        </button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        {/* Sidebar — signal list */}
        <aside className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-border bg-bg-subtle/40">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <RadioTower className="size-4" /> Recent signals
              {signals && (
                <span className="text-[11px] text-ink-muted font-normal">
                  · {signals.length}
                </span>
              )}
            </h2>
          </div>
          <div className="max-h-[70vh] overflow-y-auto divide-y divide-border">
            {isLoading && (
              <div className="p-4 text-xs text-ink-muted">Loading…</div>
            )}
            {!isLoading && (!signals || signals.length === 0) && (
              <div className="p-4 text-xs text-ink-muted">
                No signals yet. Make sure the Telegram listener is configured
                and at least one channel is enabled.
              </div>
            )}
            {signals?.map(s => (
              <SignalRow
                key={s.id}
                signal={s}
                isActive={s.id === (selected?.id ?? -1)}
                onClick={() => setSelectedId(s.id)}
              />
            ))}
          </div>
        </aside>

        {/* Detail pane */}
        <section className="card p-4 min-h-[400px]">
          {selected ? (
            <SignalDetail signal={selected} />
          ) : (
            <div className="text-sm text-ink-muted flex items-center gap-2">
              <AlertCircle className="size-4" />
              Select a signal from the list to see details.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}


function SignalRow({
  signal: s, isActive, onClick,
}: { signal: TgSignalRow; isActive: boolean; onClick: () => void }) {
  const Dir = s.direction === "BUY" ? ArrowUp : ArrowDown;
  const dirCls = s.direction === "BUY"
    ? "bg-emerald-500/15 text-emerald-400"
    : "bg-rose-500/15 text-rose-400";
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 hover:bg-bg-subtle/40 transition-colors
                  ${isActive ? "bg-bg-subtle/60" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-[11px] font-medium px-2 py-0.5 rounded inline-flex items-center gap-0.5 ${dirCls}`}>
            <Dir className="size-3" /> {s.direction}
          </span>
          <span className="font-medium truncate">{s.symbol}</span>
        </div>
        <ChevronRight className="size-4 text-ink-dim shrink-0" />
      </div>
      <div className="mt-1.5 text-[11px] text-ink-muted truncate">
        {s.channel_title || `Channel ${s.channel_id}`}
      </div>
      <div className="mt-1 font-mono text-xs text-ink">
        {fmt(s.entry_from)}
        {s.entry_from !== s.entry_to && <> — {fmt(s.entry_to)}</>}
      </div>
      <div className="mt-0.5 text-[11px] text-ink-dim">
        {relTime(s.signal_time)}
      </div>
    </button>
  );
}


function SignalDetail({ signal: s }: { signal: TgSignalRow }) {
  const dirCls = s.direction === "BUY"
    ? "bg-emerald-500/15 text-emerald-400"
    : "bg-rose-500/15 text-rose-400";
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium px-2 py-0.5 rounded ${dirCls}`}>
              {s.direction}
            </span>
            <h2 className="text-xl font-semibold">{s.symbol}</h2>
            <span className="text-[11px] uppercase tracking-wide text-ink-dim">
              {s.parser_key}
            </span>
          </div>
          <div className="text-xs text-ink-muted mt-1">
            From {s.channel_title || `channel ${s.channel_id}`} ·{" "}
            {new Date(s.signal_time).toLocaleString()}
          </div>
        </div>
        <span className="text-[11px] px-2 py-0.5 rounded bg-bg-subtle text-ink-muted">
          {s.status}
        </span>
      </div>

      <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Field label="Entry from" value={fmt(s.entry_from)} mono />
        <Field label="Entry to"   value={fmt(s.entry_to)} mono />
        <Field label="Stop loss"  value={fmt(s.sl)} mono valueCls="text-rose-400" />
        <Field label="TPs"        value={(s.tps || []).map(fmt).join(" · ") || "—"} mono />
      </dl>

      {s.raw_text && (
        <div>
          <div className="text-xs text-ink-muted mb-1 flex items-center gap-1">
            <MessageSquare className="size-3.5" /> Original message
          </div>
          <pre className="bg-bg-subtle/40 rounded p-3 text-xs whitespace-pre-wrap break-words font-mono">
            {s.raw_text}
          </pre>
        </div>
      )}
    </div>
  );
}


function Field({ label, value, mono, valueCls }: {
  label: string; value: string; mono?: boolean; valueCls?: string;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-dim">{label}</dt>
      <dd className={`mt-0.5 ${mono ? "font-mono" : ""} ${valueCls || "text-ink"}`}>
        {value}
      </dd>
    </div>
  );
}


function fmt(n: number) {
  // XAU prices have up to two decimals; forex pairs have up to five. We
  // pick a sensible default — show up to 6 significant digits without
  // trailing zeros.
  return Number(n).toLocaleString(undefined, {
    maximumFractionDigits: 6, minimumFractionDigits: 0,
  });
}

function relTime(iso: string) {
  // Lightweight "5m ago" formatter — avoids pulling date-fns just for this.
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}
