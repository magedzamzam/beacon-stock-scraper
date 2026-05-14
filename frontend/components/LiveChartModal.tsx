"use client";

/**
 * Live monitor chart — opens as a modal from the stock detail page.
 *
 * Design notes:
 *   - Pure pass-through: bars come from broker_gateway → Capital.com via the
 *     /stocks/{id}/bars proxy. Nothing persisted on our side.
 *   - "Live" = REST polling every 5 seconds rather than WebSocket. A full WS
 *     stack would mean a long-lived connection inside broker_gateway plus
 *     subscription bookkeeping plus reconnect handling — substantial new
 *     infrastructure that's hard to revert cleanly. Polling reuses the
 *     existing cached-adapter session in the gateway (one Capital.com login
 *     per ~8 minutes) and feels essentially live at MINUTE_5 or coarser
 *     resolutions because the bar itself only changes every N minutes.
 *   - Uses `lightweight-charts` (already in package.json) — the same library
 *     TradingView ships, so the look matches a real trading chart.
 *
 * Reverting this feature: delete this file + the button that opens it on
 * the stock detail page. Backend endpoints and adapter methods can stay or
 * go; they're not wired to anything else.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { createChart, IChartApi, ISeriesApi, LineStyle, UTCTimestamp, ColorType } from "lightweight-charts";
import { CandlestickChart, LineChart as LineIcon, RefreshCw, X, Activity, Loader2, AlertCircle } from "lucide-react";
import { api, type BarResolution, type OhlcBar, type BarsResponse } from "@/lib/api";

// Capital.com supported resolutions, in display order.
const RESOLUTIONS: Array<{ key: BarResolution; label: string }> = [
  { key: "MINUTE",     label: "1m" },
  { key: "MINUTE_5",   label: "5m" },
  { key: "MINUTE_15",  label: "15m" },
  { key: "MINUTE_30",  label: "30m" },
  { key: "HOUR",       label: "1H" },
  { key: "HOUR_4",     label: "4H" },
  { key: "DAY",        label: "D" },
  { key: "WEEK",       label: "W" },
  { key: "MONTH",      label: "M" },
];

// Refresh cadence per resolution (ms). On daily+ resolutions there's no point
// hammering the API; the bar doesn't tick that often.
function refreshIntervalMs(res: BarResolution): number {
  switch (res) {
    case "MINUTE":     return 3_000;
    case "MINUTE_5":   return 5_000;
    case "MINUTE_15":  return 10_000;
    case "MINUTE_30":  return 15_000;
    case "HOUR":       return 30_000;
    case "HOUR_4":     return 60_000;
    case "DAY":        return 120_000;
    case "WEEK":       return 300_000;
    case "MONTH":      return 600_000;
  }
}

// Capital.com gives "YYYY/MM/DD HH:MM:SS" in their local TZ (the snapshotTime
// field). Convert to a UTC unix timestamp the chart expects. Best-effort —
// if the format ever changes we fall back to Date.parse, which lightweight
// charts may render at epoch 0; the user would see all bars at the same x
// and know something is off rather than getting a silent misalignment.
function tsToUtcSeconds(t: string): UTCTimestamp {
  // Replace / with - so Date.parse treats it as ISO-ish.
  // Capital documents snapshotTime as UTC despite the lack of a 'Z'.
  const normalized = t.replace(/\//g, "-").replace(" ", "T") + "Z";
  const ms = Date.parse(normalized);
  if (Number.isNaN(ms)) return (Math.floor(Date.now() / 1000)) as UTCTimestamp;
  return Math.floor(ms / 1000) as UTCTimestamp;
}

interface Props {
  stockId: number;
  ticker: string;
  exchange: string;
  currency: string;
  brokerId?: number;       // optional — proxy picks first tradeable mapping if omitted
  onClose: () => void;
}

export default function LiveChartModal({
  stockId, ticker, exchange, currency, brokerId, onClose,
}: Props) {
  const [resolution, setResolution] = useState<BarResolution>("MINUTE_5");
  const [chartType, setChartType] = useState<"candle" | "line">("candle");

  // Pull bars on a polling cadence that scales with resolution.
  const swrKey = ["bars", stockId, resolution, brokerId ?? "auto"] as const;
  const { data, error, isLoading, mutate } = useSWR<BarsResponse>(
    swrKey,
    () => api.stockBars(stockId, { resolution, max_bars: 300, broker_id: brokerId }),
    {
      refreshInterval: refreshIntervalMs(resolution),
      revalidateOnFocus: true,
      dedupingInterval: 1000,
    },
  );

  // ----- Chart wiring -----
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Create the chart instance once on mount; tear it down on unmount.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9ca3af",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: {
        borderColor: "rgba(255,255,255,0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;

    // Both series exist; we toggle visibility rather than recreate.
    // (Creating/destroying series on every type change loses scroll position
    // and adds jank on slow tabs.)
    const candle = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderUpColor: "#10b981",
      borderDownColor: "#f43f5e",
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
      priceLineStyle: LineStyle.Dotted,
    });
    const line = chart.addLineSeries({
      color: "#3b82f6",
      lineWidth: 2,
      priceLineStyle: LineStyle.Dotted,
    });
    line.applyOptions({ visible: false });
    candleSeriesRef.current = candle;
    lineSeriesRef.current = line;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      lineSeriesRef.current = null;
    };
  }, []);

  // Toggle series visibility when chartType changes.
  useEffect(() => {
    if (!candleSeriesRef.current || !lineSeriesRef.current) return;
    candleSeriesRef.current.applyOptions({ visible: chartType === "candle" });
    lineSeriesRef.current.applyOptions({ visible: chartType === "line" });
  }, [chartType]);

  // Push new bar data into the active series when the response changes.
  useEffect(() => {
    const bars = data?.bars;
    if (!bars || !candleSeriesRef.current || !lineSeriesRef.current) return;

    // Deduplicate by timestamp (Capital sometimes returns the same minute
    // twice on the boundary). lightweight-charts crashes on duplicate times,
    // so we keep the last entry per time bucket.
    const byTime = new Map<number, OhlcBar>();
    for (const b of bars) {
      const t = tsToUtcSeconds(b.t);
      byTime.set(t, b);
    }
    const sorted = [...byTime.entries()].sort((a, b) => a[0] - b[0]);

    if (chartType === "candle") {
      candleSeriesRef.current.setData(
        sorted.map(([t, b]) => ({
          time: t as UTCTimestamp,
          open: b.o,
          high: b.h ?? Math.max(b.o, b.c),
          low: b.l ?? Math.min(b.o, b.c),
          close: b.c,
        })),
      );
    } else {
      lineSeriesRef.current.setData(
        sorted.map(([t, b]) => ({ time: t as UTCTimestamp, value: b.c })),
      );
    }
  }, [data, chartType]);

  // Latest-bar summary for the header readout.
  const last = useMemo(() => {
    const bars = data?.bars;
    if (!bars || bars.length === 0) return null;
    const newest = bars[bars.length - 1];
    const oldest = bars[0];
    const pctSinceOldest =
      oldest && oldest.c ? ((newest.c - oldest.c) / oldest.c) * 100 : null;
    return { newest, oldest, pctSinceOldest };
  }, [data]);

  // ESC to close
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="relative w-full max-w-6xl h-[85vh] bg-bg rounded-lg border border-border shadow-2xl flex flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-3">
            <Activity className="size-4 text-brand" />
            <div>
              <div className="text-sm font-semibold flex items-center gap-2">
                {ticker}
                <span className="text-xs font-normal text-ink-muted">
                  {exchange} · live monitor
                </span>
              </div>
              {last && (
                <div className="text-xs text-ink-muted flex items-center gap-3 mt-0.5">
                  <span className="font-mono">
                    {currency} {last.newest.c.toFixed(2)}
                  </span>
                  {last.pctSinceOldest != null && (
                    <span
                      className={
                        last.pctSinceOldest >= 0
                          ? "text-emerald-500"
                          : "text-rose-500"
                      }
                    >
                      {last.pctSinceOldest >= 0 ? "+" : ""}
                      {last.pctSinceOldest.toFixed(2)}%
                      <span className="text-ink-dim ml-1">
                        over visible range
                      </span>
                    </span>
                  )}
                  {data?.fetched_at && (
                    <span className="text-ink-dim">
                      {new Date(data.fetched_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink p-1 rounded hover:bg-bg-subtle"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-border bg-bg-subtle/30">
          <div className="flex flex-wrap gap-1">
            {RESOLUTIONS.map((r) => (
              <button
                key={r.key}
                onClick={() => setResolution(r.key)}
                className={
                  "text-xs px-2 py-1 rounded font-mono " +
                  (resolution === r.key
                    ? "bg-brand/15 text-brand"
                    : "text-ink-muted hover:text-ink hover:bg-bg-subtle")
                }
              >
                {r.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setChartType("candle")}
              className={
                "p-1.5 rounded " +
                (chartType === "candle"
                  ? "bg-brand/15 text-brand"
                  : "text-ink-muted hover:text-ink hover:bg-bg-subtle")
              }
              aria-label="Candlestick"
              title="Candlestick"
            >
              <CandlestickChart className="size-4" />
            </button>
            <button
              onClick={() => setChartType("line")}
              className={
                "p-1.5 rounded " +
                (chartType === "line"
                  ? "bg-brand/15 text-brand"
                  : "text-ink-muted hover:text-ink hover:bg-bg-subtle")
              }
              aria-label="Line"
              title="Line"
            >
              <LineIcon className="size-4" />
            </button>
            <span className="w-px h-4 bg-border mx-1" />
            <button
              onClick={() => mutate()}
              className="p-1.5 rounded text-ink-muted hover:text-ink hover:bg-bg-subtle"
              aria-label="Refresh now"
              title="Refresh now"
            >
              <RefreshCw className={"size-4 " + (isLoading ? "animate-spin" : "")} />
            </button>
          </div>
        </div>

        {/* Chart body */}
        <div className="flex-1 relative">
          {error && (
            <div className="absolute inset-0 flex items-center justify-center text-rose-500 text-sm gap-2">
              <AlertCircle className="size-4" />
              {(error as Error).message || "Failed to load bars"}
            </div>
          )}
          {!error && isLoading && !data && (
            <div className="absolute inset-0 flex items-center justify-center text-ink-muted text-sm gap-2">
              <Loader2 className="size-4 animate-spin" />
              Loading bars from broker…
            </div>
          )}
          {!error && data?.bars?.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-ink-muted text-sm">
              No bars returned by the broker for this resolution.
            </div>
          )}
          <div ref={containerRef} className="absolute inset-0" />
        </div>

        {/* Footer note — operational caveats. The user opening the chart for
            the first time benefits from seeing where the data comes from. */}
        <footer className="px-4 py-1.5 border-t border-border text-[11px] text-ink-dim flex items-center justify-between">
          <span>
            Polling every {refreshIntervalMs(resolution) / 1000}s · Source: broker
            ({data?.broker_id != null ? `id ${data.broker_id}` : "auto"})
          </span>
          <span>Press ESC to close</span>
        </footer>
      </div>
    </div>
  );
}
