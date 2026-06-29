"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, type MoveSignalParams } from "@/lib/api";
import { fmtNumber, fmtPrice } from "@/lib/utils";
import { Radar, RefreshCw } from "lucide-react";

const MODES = ["absolute", "atr", "percent"] as const;

function scoreColor(s: number) {
  if (s >= 0.7) return "text-emerald-500";
  if (s >= 0.5) return "text-amber-500";
  return "text-ink-muted";
}

function LiveGoldPanel(cfg: Pick<MoveSignalParams, "target_mode" | "target_value" | "atr_period" | "lookback" | "fire_threshold">) {
  const { data, error } = useSWR(
    ["live-gold", cfg],
    () => api.getLiveMoveSignal({ symbol: "GOLD", resolution: "MINUTE_5", price_type: "bid", ...cfg }),
    { refreshInterval: 5000 },
  );
  const sig = data?.signal;
  const price = data?.quote?.bid ?? data?.quote?.offer ?? null;
  const stale = !data || sig?.insufficient_data;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`inline-block size-2 rounded-full ${data && !error && !stale ? "bg-emerald-500 animate-pulse" : "bg-ink-dim"}`} />
          <h2 className="text-sm font-semibold text-ink">Live — GOLD · 5-min</h2>
        </div>
        <span className="text-[11px] text-ink-dim">
          {data?.last_closed_bar_ts
            ? `last bar ${new Date(data.last_closed_bar_ts).toLocaleTimeString()} · ${data.bars_used} bars`
            : "waiting for stream…"}
        </span>
      </div>
      {error && <p className="text-xs text-rose-500">Live feed unavailable.</p>}
      {sig?.insufficient_data && (
        <p className="text-xs text-ink-muted">Not enough streamed bars yet — the service needs to accumulate history.</p>
      )}
      {sig && !sig.insufficient_data && (
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-sm">
          <Stat label="Price" value={fmtPrice(price, "USD")} />
          <Stat label="Score" value={`${(sig.score * 100).toFixed(0)}%`} cls={scoreColor(sig.score)} big />
          <Stat label="Target" value={fmtPrice(sig.target_abs, "USD")} />
          <Stat label="ATR" value={fmtPrice(sig.atr, "USD")} />
          <Stat label="Range×" value={fmtNumber(sig.range_expansion, { digits: 2 })} />
          <Stat label="Vol×" value={fmtNumber(sig.vol_surge, { digits: 2 })} />
        </div>
      )}
      {sig?.reason && !sig.insufficient_data && (
        <p className="text-[11px] text-ink-dim mt-2">{sig.reason}</p>
      )}
    </div>
  );
}

function Stat({ label, value, cls, big }: { label: string; value: string; cls?: string; big?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-ink-muted">{label}</div>
      <div className={`tabular-nums font-semibold ${big ? "text-xl" : ""} ${cls ?? "text-ink"}`}>{value}</div>
    </div>
  );
}

export default function SignalsPage() {
  const [params, setParams] = useState<MoveSignalParams>({
    target_mode: "absolute",
    target_value: 5,
    atr_period: 14,
    lookback: 20,
    fire_threshold: 0.5,
    only_fired: true,
    limit: 100,
  });
  const [autoRefresh, setAutoRefresh] = useState(false);

  const { data, isLoading, mutate, isValidating } = useSWR(
    ["move-signals", params],
    () => api.scanMoveSignals(params),
    { keepPreviousData: true, refreshInterval: autoRefresh ? 30000 : 0 },
  );

  function update<K extends keyof MoveSignalParams>(k: K, v: MoveSignalParams[K]) {
    setParams((p) => ({ ...p, [k]: v }));
  }

  const targetUnit =
    params.target_mode === "atr" ? "× ATR" : params.target_mode === "percent" ? "%" : "$";

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Radar className="size-5 text-ink" />
          <h1 className="text-lg font-semibold text-ink">Move Signals</h1>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-ink-muted">
            <input type="checkbox" checked={autoRefresh}
                   onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh 30s
          </label>
          <button className="btn-ghost flex items-center gap-1.5" onClick={() => mutate()}>
            <RefreshCw className={`size-4 ${isValidating ? "animate-spin" : ""}`} /> Scan
          </button>
        </div>
      </div>

      <p className="text-xs text-ink-muted max-w-3xl">
        Flags symbols whose <b>next bar</b> is likely to move at least the target
        from its open in <b>either direction</b> (direction is not predicted —
        this is a volatility/expansion monitor driven by recent ATR, range
        expansion and volume surge). Bars are daily; tune the knobs to test
        scenarios. For a multi-price universe prefer <b>ATR</b> or <b>percent</b>
        mode over a fixed dollar target.
      </p>

      {/* Live — streamed instrument (default GOLD) */}
      <LiveGoldPanel
        target_mode={params.target_mode}
        target_value={params.target_value}
        atr_period={params.atr_period}
        lookback={params.lookback}
        fire_threshold={params.fire_threshold}
      />

      {/* Config panel */}
      <div className="card p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <label className="text-xs text-ink-muted space-y-1">
          <span>Target mode</span>
          <select className="input w-full" value={params.target_mode}
                  onChange={(e) => update("target_mode", e.target.value as MoveSignalParams["target_mode"])}>
            {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>Target ({targetUnit})</span>
          <input className="input w-full" type="number" step="0.1" value={params.target_value}
                 onChange={(e) => update("target_value", Number(e.target.value))} />
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>ATR period</span>
          <input className="input w-full" type="number" value={params.atr_period}
                 onChange={(e) => update("atr_period", Number(e.target.value))} />
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>Lookback</span>
          <input className="input w-full" type="number" value={params.lookback}
                 onChange={(e) => update("lookback", Number(e.target.value))} />
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>Fire threshold</span>
          <input className="input w-full" type="number" step="0.05" min="0" max="1"
                 value={params.fire_threshold}
                 onChange={(e) => update("fire_threshold", Number(e.target.value))} />
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>Exchange</span>
          <input className="input w-full" placeholder="all" value={params.exchange ?? ""}
                 onChange={(e) => update("exchange", e.target.value.toUpperCase() || undefined)} />
        </label>
        <label className="text-xs text-ink-muted space-y-1">
          <span>Min price</span>
          <input className="input w-full" type="number" placeholder="any"
                 value={params.min_price ?? ""}
                 onChange={(e) => update("min_price", e.target.value ? Number(e.target.value) : undefined)} />
        </label>
        <label className="text-xs text-ink-muted flex items-center gap-2 col-span-2 md:col-span-1">
          <input type="checkbox" checked={params.only_fired ?? true}
                 onChange={(e) => update("only_fired", e.target.checked)} />
          <span>Only fired</span>
        </label>
      </div>

      {/* Summary */}
      <div className="text-xs text-ink-muted">
        {data
          ? <>Scanned <b className="text-ink">{data.scanned}</b> symbols · <b className="text-ink">{data.count}</b> {params.only_fired ? "firing" : "scored"}</>
          : isLoading ? "Scanning…" : "—"}
      </div>

      {/* Results */}
      <div className="card overflow-x-auto">
        <table className="table w-full text-sm">
          <thead>
            <tr className="text-ink-muted text-xs text-left">
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Exch</th>
              <th className="px-3 py-2 text-right">Last</th>
              <th className="px-3 py-2 text-right">Score</th>
              <th className="px-3 py-2 text-right">Target</th>
              <th className="px-3 py-2 text-right">ATR</th>
              <th className="px-3 py-2 text-right">Range×</th>
              <th className="px-3 py-2 text-right">Vol×</th>
              <th className="px-3 py-2 text-right">RSI</th>
              <th className="px-3 py-2">Why</th>
            </tr>
          </thead>
          <tbody>
            {data?.signals.map((s) => (
              <tr key={s.stock_id} className="border-t border-border hover:bg-bg-subtle">
                <td className="px-3 py-2">
                  <Link href={`/stock/${s.exchange_code}/${s.ticker}`}
                        className="text-ink font-medium hover:underline">{s.ticker}</Link>
                  <div className="text-[11px] text-ink-dim truncate max-w-[180px]">{s.company_name}</div>
                </td>
                <td className="px-3 py-2 text-ink-muted">{s.exchange_code}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtPrice(s.last_close, s.currency)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-semibold ${scoreColor(s.score)}`}>
                  {(s.score * 100).toFixed(0)}%
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{fmtPrice(s.target_abs, s.currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{fmtPrice(s.atr, s.currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{fmtNumber(s.range_expansion, { digits: 2 })}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{fmtNumber(s.vol_surge, { digits: 2 })}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{s.rsi != null ? s.rsi.toFixed(0) : "—"}</td>
                <td className="px-3 py-2 text-[11px] text-ink-dim max-w-[280px] truncate" title={s.reason}>{s.reason}</td>
              </tr>
            ))}
            {data && data.signals.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-8 text-center text-ink-muted">
                No symbols meet the current configuration.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
