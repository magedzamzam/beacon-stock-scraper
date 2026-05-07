"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { api, type ScreenerParams, type Verdict } from "@/lib/api";
import { fmtNumber, fmtPercent, changeColor } from "@/lib/utils";
import VerdictBadge from "@/components/VerdictBadge";
import { Search, ArrowUp, ArrowDown, X } from "lucide-react";

export default function ScreenerPage() {
  const sp = useSearchParams();
  const [params, setParams] = useState<ScreenerParams>({
    sort_by: "composite_score",
    sort_dir: "desc",
    limit: 50,
    offset: 0,
    verdict: (sp?.get("verdict") as Verdict) || undefined,
    exchange: sp?.get("exchange") || undefined,
  });
  const [debouncedQ, setDebouncedQ] = useState<string>("");

  useEffect(() => {
    const t = setTimeout(() => setParams((p) => ({ ...p, q: debouncedQ || undefined, offset: 0 })), 300);
    return () => clearTimeout(t);
  }, [debouncedQ]);

  const { data: filters } = useSWR("filters", api.filters);
  const { data, isLoading } = useSWR(["screener", params], () => api.screener(params), { keepPreviousData: true });

  const totalPages = data ? Math.ceil(data.total / (params.limit ?? 50)) : 0;
  const page = Math.floor((params.offset ?? 0) / (params.limit ?? 50)) + 1;

  function update<K extends keyof ScreenerParams>(k: K, v: ScreenerParams[K]) {
    setParams((p) => ({ ...p, [k]: v, offset: 0 }));
  }
  function toggleSort(field: string) {
    setParams((p) => {
      if (p.sort_by === field) return { ...p, sort_dir: p.sort_dir === "asc" ? "desc" : "asc" };
      return { ...p, sort_by: field, sort_dir: "desc" };
    });
  }
  function clearFilters() {
    setDebouncedQ("");
    setParams({ sort_by: "composite_score", sort_dir: "desc", limit: 50, offset: 0 });
  }

  const activeFiltersCount = useMemo(() => {
    let n = 0;
    (["q","exchange","sector","industry","verdict","min_score","max_pe","min_dividend"] as const).forEach((k) => {
      if (params[k] !== undefined && params[k] !== "") n++;
    });
    return n;
  }, [params]);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
          <p className="text-ink-muted text-sm mt-1">
            {data ? `${data.total.toLocaleString()} stocks across DFM, ADX, and EGX` : "Loading…"}
          </p>
        </div>
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-2.5 size-4 text-ink-dim" />
          <input
            placeholder="Search ticker or company"
            className="input pl-9"
            onChange={(e) => setDebouncedQ(e.target.value)}
          />
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[260px,1fr] gap-5">
        {/* Filters */}
        <aside className="card p-4 h-fit lg:sticky lg:top-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold">Filters</div>
            {activeFiltersCount > 0 && (
              <button onClick={clearFilters} className="text-xs text-ink-muted hover:text-ink flex items-center gap-1">
                <X className="size-3" /> Clear
              </button>
            )}
          </div>
          <div className="space-y-3">
            <Field label="Exchange">
              <select className="input" value={params.exchange ?? ""} onChange={(e) => update("exchange", e.target.value || undefined)}>
                <option value="">All</option>
                {filters?.exchanges.map((x) => (
                  <option key={x.code} value={x.code}>{x.code.toUpperCase()} — {x.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Sector">
              <select className="input" value={params.sector ?? ""} onChange={(e) => update("sector", e.target.value || undefined)}>
                <option value="">All</option>
                {filters?.sectors.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Industry">
              <select className="input" value={params.industry ?? ""} onChange={(e) => update("industry", e.target.value || undefined)}>
                <option value="">All</option>
                {filters?.industries.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </Field>
            <Field label="Verdict">
              <div className="grid grid-cols-3 gap-1">
                {(["BUY","WATCH","STAY_AWAY"] as Verdict[]).map((v) => (
                  <button key={v} onClick={() => update("verdict", params.verdict === v ? undefined : v)}
                          className={`text-xs py-1.5 rounded-md border ${params.verdict===v ? "border-brand bg-brand/10 text-brand" : "border-border bg-bg-subtle text-ink-muted hover:text-ink"}`}>
                    {v.replace("_"," ")}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Min score">
              <input type="number" min={0} max={100} className="input"
                     value={params.min_score ?? ""} onChange={(e) => update("min_score", e.target.value ? Number(e.target.value) : undefined)} />
            </Field>
            <Field label="Max P/E">
              <input type="number" min={0} className="input"
                     value={params.max_pe ?? ""} onChange={(e) => update("max_pe", e.target.value ? Number(e.target.value) : undefined)} />
            </Field>
            <Field label="Min dividend %">
              <input type="number" min={0} step={0.1} className="input"
                     value={params.min_dividend ?? ""} onChange={(e) => update("min_dividend", e.target.value ? Number(e.target.value) : undefined)} />
            </Field>
          </div>
        </aside>

        {/* Table */}
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[860px]">
              <thead className="text-xs text-ink-muted bg-bg-subtle">
                <tr>
                  <Th>Stock</Th>
                  <Th align="right" sortKey="last_close" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>Price</Th>
                  <Th align="right" sortKey="last_change_pct" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>Change</Th>
                  <Th align="right" sortKey="market_cap" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>Mkt Cap</Th>
                  <Th align="right" sortKey="pe_ratio" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>P/E</Th>
                  <Th align="right" sortKey="dividend_yield_pct" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>Div Y</Th>
                  <Th align="right" sortKey="rsi_14" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>RSI</Th>
                  <Th align="right" sortKey="composite_score" current={params.sort_by} dir={params.sort_dir} onSort={toggleSort}>Score</Th>
                  <Th align="right">Verdict</Th>
                </tr>
              </thead>
              <tbody>
                {isLoading && !data && (
                  <tr><td colSpan={9} className="p-10 text-center text-ink-muted">Loading…</td></tr>
                )}
                {(data?.items ?? []).map((s) => (
                  <tr key={s.id} className="table-row">
                    <td className="p-3">
                      <Link href={`/stock/${s.exchange_code}/${s.ticker}`} className="hover:text-brand">
                        <div className="font-medium">{s.ticker} <span className="text-ink-dim text-xs">·{s.exchange_code.toUpperCase()}</span></div>
                        <div className="text-xs text-ink-muted truncate max-w-[260px]">{s.company_name}</div>
                      </Link>
                    </td>
                    <td className="p-3 text-right font-mono">{fmtNumber(s.last_close)}</td>
                    <td className={`p-3 text-right font-mono ${changeColor(s.last_change_pct)}`}>{fmtPercent(s.last_change_pct)}</td>
                    <td className="p-3 text-right font-mono">{fmtNumber(s.market_cap, { compact: true, digits: 1 })}</td>
                    <td className="p-3 text-right font-mono">{fmtNumber(s.pe_ratio)}</td>
                    <td className="p-3 text-right font-mono">{s.dividend_yield_pct != null ? `${s.dividend_yield_pct.toFixed(2)}%` : "—"}</td>
                    <td className="p-3 text-right font-mono">{fmtNumber(s.rsi_14, { digits: 1 })}</td>
                    <td className="p-3 text-right font-mono font-semibold">{fmtNumber(s.composite_score, { digits: 0 })}</td>
                    <td className="p-3 text-right"><VerdictBadge verdict={s.verdict} size="xs" /></td>
                  </tr>
                ))}
                {data && data.items.length === 0 && (
                  <tr><td colSpan={9} className="p-10 text-center text-ink-muted text-sm">No stocks match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {data && data.total > (params.limit ?? 50) && (
            <div className="flex items-center justify-between p-3 border-t border-border text-sm text-ink-muted">
              <div>Page {page} of {totalPages}</div>
              <div className="flex gap-2">
                <button className="btn-ghost"
                        disabled={(params.offset ?? 0) === 0}
                        onClick={() => setParams((p) => ({ ...p, offset: Math.max(0, (p.offset ?? 0) - (p.limit ?? 50)) }))}>
                  Prev
                </button>
                <button className="btn-ghost"
                        disabled={page >= totalPages}
                        onClick={() => setParams((p) => ({ ...p, offset: (p.offset ?? 0) + (p.limit ?? 50) }))}>
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label mb-1">{label}</div>
      {children}
    </div>
  );
}

function Th({ children, align = "left", sortKey, current, dir, onSort }: {
  children: React.ReactNode; align?: "left" | "right"; sortKey?: string; current?: string; dir?: string; onSort?: (k: string) => void;
}) {
  const Active = sortKey && current === sortKey;
  return (
    <th className={`p-3 ${align === "right" ? "text-right" : "text-left"}`}>
      {sortKey ? (
        <button onClick={() => onSort?.(sortKey)} className={`inline-flex items-center gap-1 hover:text-ink ${Active ? "text-ink" : ""}`}>
          {children}
          {Active && (dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
        </button>
      ) : children}
    </th>
  );
}
