"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, type AdminStockListItem } from "@/lib/api";
import { Plus, Search, Wifi, WifiOff } from "lucide-react";


export default function AdminStocksPage() {
  const [q, setQ] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const { data: stocks, isLoading } = useSWR(["admin-stocks", q], () => api.adminListStocks(q || undefined, 200));

  async function toggleScraping(stock: AdminStockListItem) {
    try {
      await api.adminPatchStock(stock.id, { is_scraping_enabled: !stock.is_scraping_enabled });
      mutate(["admin-stocks", q]);
    } catch (e: any) {
      alert(e.message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-ink-muted" />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search ticker or company"
            className="input pl-9 w-full"
          />
        </div>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>
          <Plus className="size-4" /> Add stock
        </button>
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Ticker</th>
                <th className="text-left p-3">Company</th>
                <th className="text-left p-3">Sector</th>
                <th className="text-left p-3">Currency</th>
                <th className="text-right p-3">Last close</th>
                <th className="text-center p-3">Active</th>
                <th className="text-center p-3">Scrape</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={7} className="p-8 text-center text-ink-muted">Loading…</td></tr>
              )}
              {!isLoading && (stocks || []).length === 0 && (
                <tr><td colSpan={7} className="p-8 text-center text-ink-muted text-sm">No stocks match.</td></tr>
              )}
              {(stocks || []).map((s) => (
                <tr key={s.id} className="table-row">
                  <td className="p-3 font-mono">
                    {s.ticker} <span className="text-ink-dim text-xs">·{s.exchange_code.toUpperCase()}</span>
                  </td>
                  <td className="p-3">{s.company_name}</td>
                  <td className="p-3 text-ink-muted">{s.sector || "—"}</td>
                  <td className="p-3 text-ink-muted">{s.currency || "—"}</td>
                  <td className="p-3 text-right font-mono">{s.last_close ?? "—"}</td>
                  <td className="p-3 text-center">
                    <span className={`badge ${s.active ? "bg-verdict-buy/15 text-verdict-buy" : "bg-bg-elevated text-ink-muted"}`}>
                      {s.active ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    <button
                      onClick={() => toggleScraping(s)}
                      className="inline-flex items-center gap-1 text-sm hover:text-brand"
                      title={s.is_scraping_enabled ? "Click to disable scraping" : "Click to enable scraping"}
                    >
                      {s.is_scraping_enabled
                        ? <Wifi className="size-4 text-verdict-buy" />
                        : <WifiOff className="size-4 text-ink-muted" />}
                      <span className="text-xs">{s.is_scraping_enabled ? "On" : "Off"}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showAdd && (
        <AddStockModal
          onClose={() => setShowAdd(false)}
          onSaved={() => { mutate(["admin-stocks", q]); setShowAdd(false); }}
        />
      )}
    </div>
  );
}


function AddStockModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { data: exchanges } = useSWR("admin-exchanges", () => api.adminListExchanges());
  const [exchangeCode, setExchangeCode] = useState("");
  const [ticker, setTicker] = useState("");
  const [company, setCompany] = useState("");
  const [isin, setIsin] = useState("");
  const [slug, setSlug] = useState("");
  const [sector, setSector] = useState("");
  const [industry, setIndustry] = useState("");
  const [currency, setCurrency] = useState("");
  const [country, setCountry] = useState("");
  const [website, setWebsite] = useState("");
  const [enableScraping, setEnableScraping] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!exchangeCode) { setError("Pick an exchange"); return; }
    if (!ticker.trim()) { setError("Ticker is required"); return; }
    if (!company.trim()) { setError("Company name is required"); return; }
    setSubmitting(true);
    try {
      await api.adminCreateStock({
        exchange_code: exchangeCode,
        ticker: ticker.trim(),
        company_name: company.trim(),
        isin: isin.trim() || undefined,
        marketscreener_slug: slug.trim() || undefined,
        sector: sector.trim() || undefined,
        industry: industry.trim() || undefined,
        currency: currency.trim() || undefined,
        country: country.trim() || undefined,
        website: website.trim() || undefined,
        is_scraping_enabled: enableScraping,
      });
      onSaved();
    } catch (e: any) {
      setError(e.message || "Failed to create stock");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-3">Add stock</h3>
        <p className="text-xs text-ink-dim mb-4">
          By default, scraping is OFF for new stocks so the next pipeline tick won't try an unverified slug.
          Enable it once you've confirmed the slug works.
        </p>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Exchange *</label>
              <select className="input mt-1" value={exchangeCode} onChange={(e) => setExchangeCode(e.target.value)}>
                <option value="">— Select —</option>
                {(exchanges || []).map((x) => (
                  <option key={x.code} value={x.code}>{x.code.toUpperCase()} ({x.name})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Ticker *</label>
              <input className="input mt-1 uppercase" maxLength={32}
                     value={ticker} onChange={(e) => setTicker(e.target.value)} />
            </div>
          </div>

          <div>
            <label className="label">Company name *</label>
            <input className="input mt-1" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">ISIN</label>
              <input className="input mt-1" maxLength={32} value={isin} onChange={(e) => setIsin(e.target.value)} />
            </div>
            <div>
              <label className="label">Currency</label>
              <input className="input mt-1 uppercase" maxLength={10}
                     value={currency} onChange={(e) => setCurrency(e.target.value)} />
            </div>
          </div>

          <div>
            <label className="label">stockanalysis.com slug (optional)</label>
            <input className="input mt-1" value={slug} onChange={(e) => setSlug(e.target.value)}
                   placeholder="e.g. waha-ad" />
            <p className="text-[11px] text-ink-dim mt-1">Used by the scraper. Leave blank if unknown — you can fill it in later.</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Sector</label>
              <input className="input mt-1" value={sector} onChange={(e) => setSector(e.target.value)} />
            </div>
            <div>
              <label className="label">Industry</label>
              <input className="input mt-1" value={industry} onChange={(e) => setIndustry(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Country</label>
              <input className="input mt-1" value={country} onChange={(e) => setCountry(e.target.value)} />
            </div>
            <div>
              <label className="label">Website</label>
              <input className="input mt-1" value={website} onChange={(e) => setWebsite(e.target.value)} />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm pt-2">
            <input type="checkbox" checked={enableScraping}
                   onChange={(e) => setEnableScraping(e.target.checked)} />
            <span>Enable scraping immediately (otherwise stays off until you toggle it)</span>
          </label>

          {error && <div className="text-sm text-verdict-avoid">{error}</div>}
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <button className="btn-ghost" onClick={onClose} disabled={submitting}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Saving…" : "Add stock"}
          </button>
        </div>
      </div>
    </div>
  );
}
