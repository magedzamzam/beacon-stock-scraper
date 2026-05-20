"use client";
import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { fmtNumber, fmtPercent, fmtPrice, changeColor } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import { TrendingUp, BarChart3, Sparkles, CalendarClock } from "lucide-react";

export default function DashboardPage() {
  const { data: topBuy } = useSWR("dashboard:top-buy", () =>
    api.screener({ verdict: "BUY", sort_by: "composite_score", sort_dir: "desc", limit: 8 }));
  const { data: topWatch } = useSWR("dashboard:top-watch", () =>
    api.screener({ verdict: "WATCH", sort_by: "composite_score", sort_dir: "desc", limit: 5 }));
  // "Reporting today" — both filters set to 0 means "next_earnings_date BETWEEN
  // today AND today" OR "last_earnings_date BETWEEN today AND today". So we
  // catch both pre-announcement (still to report) and post-announcement
  // (already reported earlier today) cases without changing the backend.
  const { data: earningsToday } = useSWR("dashboard:earnings-today", () =>
    api.screener({
      earnings_within_days_future: 0,
      earnings_within_days_past: 0,
      sort_by: "composite_score",
      sort_dir: "desc",
      limit: 12,
    }));
  const { data: marketAdx } = useSWR("dashboard:adx", () =>
    api.screener({ exchange: "adx", sort_by: "market_cap", sort_dir: "desc", limit: 5 }));
  const { data: marketDfm } = useSWR("dashboard:dfm", () =>
    api.screener({ exchange: "dfm", sort_by: "market_cap", sort_dir: "desc", limit: 5 }));
  const { data: marketEgx } = useSWR("dashboard:egx", () =>
    api.screener({ exchange: "egx", sort_by: "market_cap", sort_dir: "desc", limit: 5 }));

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-ink-muted text-sm mt-1">
          Daily-updated screening signals across Dubai, Abu Dhabi, and Cairo.
        </p>
      </header>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Sparkles className="size-4 text-verdict-buy" /> Top BUY signals
          </h2>
          <Link href="/screener?verdict=BUY" className="text-xs text-brand hover:underline">View all →</Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {(topBuy?.items ?? []).map((s) => (
            <Link key={s.id} href={`/stock/${s.exchange_code}/${s.ticker}`}
                  className="card p-4 hover:border-border-strong transition-colors">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-ink-dim uppercase">{s.exchange_code}</div>
                  <div className="font-semibold">{s.ticker}</div>
                </div>
                <VerdictBadge verdict={s.verdict} size="xs" />
              </div>
              <div className="text-xs text-ink-muted truncate mt-1">{s.company_name}</div>
              <div className="mt-3 flex items-end justify-between">
                <div>
                  <div className="text-lg font-semibold">{fmtPrice(s.last_close, s.currency)}</div>
                  <div className={`text-xs ${changeColor(s.last_change_pct)}`}>{fmtPercent(s.last_change_pct)}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-ink-dim uppercase">Score</div>
                  <div className="font-mono text-sm font-semibold">{fmtNumber(s.composite_score, { digits: 0 })}</div>
                </div>
              </div>
            </Link>
          ))}
          {topBuy && topBuy.items.length === 0 && (
            <div className="col-span-full text-sm text-ink-muted card p-4">
              No BUY signals yet — run the daily pipeline from the Admin panel.
            </div>
          )}
        </div>
      </section>

      {/* Reporting today — only renders the section header + grid when the
          API has loaded. The grid stays empty (with a fallback row) on a
          quiet day so the section doesn't disappear mid-render. */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <CalendarClock className="size-4 text-brand" /> Reporting today
            {earningsToday && earningsToday.items.length > 0 && (
              <span className="text-[11px] text-ink-muted font-normal">
                · {earningsToday.items.length} {earningsToday.items.length === 1 ? "stock" : "stocks"}
              </span>
            )}
          </h2>
          <Link
            href="/screener?earnings_within_days_future=0&earnings_within_days_past=0"
            className="text-xs text-brand hover:underline"
          >
            View all →
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {(earningsToday?.items ?? []).map((s) => (
            <Link key={s.id} href={`/stock/${s.exchange_code}/${s.ticker}`}
                  className="card p-4 hover:border-border-strong transition-colors">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-ink-dim uppercase">{s.exchange_code}</div>
                  <div className="font-semibold">{s.ticker}</div>
                </div>
                <VerdictBadge verdict={s.verdict} size="xs" />
              </div>
              <div className="text-xs text-ink-muted truncate mt-1">{s.company_name}</div>
              <div className="mt-3 flex items-end justify-between">
                <div>
                  <div className="text-lg font-semibold">{fmtPrice(s.last_close, s.currency)}</div>
                  <div className={`text-xs ${changeColor(s.last_change_pct)}`}>
                    {fmtPercent(s.last_change_pct)}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-ink-dim uppercase">Score</div>
                  <div className="font-mono text-sm font-semibold">
                    {fmtNumber(s.composite_score, { digits: 0 })}
                  </div>
                </div>
              </div>
            </Link>
          ))}
          {earningsToday && earningsToday.items.length === 0 && (
            <div className="col-span-full text-sm text-ink-muted card p-4">
              No companies reporting earnings today.
            </div>
          )}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold flex items-center gap-2 mb-3">
          <BarChart3 className="size-4" /> Market overview
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <ExchangeCard title="ADX · Abu Dhabi" data={marketAdx?.items ?? []} />
          <ExchangeCard title="DFM · Dubai" data={marketDfm?.items ?? []} />
          <ExchangeCard title="EGX · Cairo" data={marketEgx?.items ?? []} />
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <TrendingUp className="size-4 text-verdict-watch" /> On the watchlist
          </h2>
          <Link href="/screener?verdict=WATCH" className="text-xs text-brand hover:underline">View all →</Link>
        </div>
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Stock</th>
                <th className="text-right p-3 hidden sm:table-cell">Price</th>
                <th className="text-right p-3">Change</th>
                <th className="text-right p-3 hidden md:table-cell">P/E</th>
                <th className="text-right p-3">Score</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {(topWatch?.items ?? []).map((s) => (
                <tr key={s.id} className="table-row">
                  <td className="p-3">
                    <Link href={`/stock/${s.exchange_code}/${s.ticker}`} className="hover:text-brand">
                      <div className="font-medium">{s.ticker} <span className="text-ink-dim text-xs">·{s.exchange_code}</span></div>
                      <div className="text-xs text-ink-muted truncate max-w-[300px]">{s.company_name}</div>
                    </Link>
                  </td>
                  <td className="p-3 text-right hidden sm:table-cell font-mono">{fmtPrice(s.last_close, s.currency)}</td>
                  <td className={`p-3 text-right font-mono ${changeColor(s.last_change_pct)}`}>{fmtPercent(s.last_change_pct)}</td>
                  <td className="p-3 text-right hidden md:table-cell font-mono">{fmtNumber(s.pe_ratio)}</td>
                  <td className="p-3 text-right font-mono font-semibold">{fmtNumber(s.composite_score, { digits: 0 })}</td>
                  <td className="p-3 text-right"><VerdictBadge verdict={s.verdict} size="xs" /></td>
                </tr>
              ))}
              {topWatch && topWatch.items.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-ink-muted text-sm">No watch signals yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ExchangeCard({ title, data }: { title: string; data: any[] }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="font-medium text-sm">{title}</div>
        <div className="text-xs text-ink-dim">Top by mkt cap</div>
      </div>
      <div className="space-y-2">
        {data.map((s) => (
          <Link key={s.id} href={`/stock/${s.exchange_code}/${s.ticker}`}
                className="flex items-center justify-between text-sm py-1.5 hover:text-brand">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-medium">{s.ticker}</span>
              <span className="text-ink-muted truncate text-xs">{s.company_name}</span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <span className={`text-xs font-mono ${changeColor(s.last_change_pct)}`}>{fmtPercent(s.last_change_pct)}</span>
              <VerdictBadge verdict={s.verdict} size="xs" />
            </div>
          </Link>
        ))}
        {data.length === 0 && <div className="text-xs text-ink-muted py-2">No data yet.</div>}
      </div>
    </div>
  );
}
