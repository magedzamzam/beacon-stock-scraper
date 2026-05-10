"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, type BulkImportPreview, type BulkImportResult } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import {
  AlertCircle, CheckCircle2, FileUp, Loader2, Play, RefreshCw, XCircle,
} from "lucide-react";

/**
 * Bulk CSV importer for stockanalysis.com exchange exports.
 *
 * Workflow:
 *   1. Pick exchange (required — file is exchange-specific)
 *   2. Upload CSV → preview shows row/column counts + sample
 *   3. Click "Run import" → backend fans the 248 columns out across
 *      stocks + stock_quotes + stock_history_quote + stock_fin_* + stock_mkt_*
 *   4. Result panel shows counts + per-row log
 *   5. History below shows recent imports
 */
export default function AdminBulkImportTool() {
  const { data: exchanges } = useSWR("admin:exchanges", api.adminListExchanges);
  const { data: history, mutate: refreshHistory } = useSWR(
    "admin:bulk-history",
    () => api.adminBulkImportHistory(25),
  );

  const [exchangeId, setExchangeId] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BulkImportPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // Reset when the file changes
  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setPreview(null);
    setPreviewError(null);
    setResult(null);
    setRunError(null);
  }

  async function loadPreview() {
    if (!file) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const p = await api.adminBulkImportPreview(file);
      setPreview(p);
    } catch (e: any) {
      setPreviewError(e.message);
    } finally {
      setPreviewing(false);
    }
  }

  async function runImport() {
    if (!file || !exchangeId || typeof exchangeId !== "number") return;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const r = await api.adminBulkImportExecute(file, exchangeId);
      setResult(r);
      refreshHistory();
    } catch (e: any) {
      setRunError(e.message);
    } finally {
      setRunning(false);
    }
  }

  const canRun = !!(file && exchangeId && preview && !running);

  return (
    <div className="space-y-5">
      <div className="card p-4 space-y-4">
        <header>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <FileUp className="size-4" /> Bulk CSV import
          </h3>
          <p className="text-ink-muted text-xs mt-1">
            Upload a stockanalysis.com exchange export. The 248 columns get fanned out
            across <code>stocks</code>, <code>stock_quotes</code>, <code>stock_history_quote</code>,{" "}
            <code>stock_fin_ratios/statement/cashflow</code>, <code>stock_mkt_dividends</code>, and{" "}
            <code>stock_mkt_technicals</code> — one row per stock.
          </p>
        </header>

        {/* Exchange selector — required */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Exchange (required)</span>
            <select
              className="input mt-1 w-full"
              value={exchangeId}
              onChange={(e) =>
                setExchangeId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">-- pick an exchange --</option>
              {exchanges?.map((ex) => (
                <option key={ex.id} value={ex.id}>
                  {ex.code.toUpperCase()} — {ex.name}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-ink-muted mt-1 block">
              Every row in the CSV is mapped to this exchange. You'll need a separate
              file per exchange.
            </span>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-ink-muted">CSV file</span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="input mt-1 w-full"
              onChange={onFileChange}
            />
            <span className="text-[11px] text-ink-muted mt-1 block">
              Expected: stockanalysis.com bulk export. The first column should be{" "}
              <code>Symbol</code>.
            </span>
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            className="btn-ghost"
            disabled={!file || previewing}
            onClick={loadPreview}
          >
            {previewing ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Loading preview…
              </>
            ) : (
              <>
                <RefreshCw className="size-4" /> Preview
              </>
            )}
          </button>
          <button
            className="btn-primary"
            disabled={!canRun}
            onClick={runImport}
          >
            {running ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Importing…
              </>
            ) : (
              <>
                <Play className="size-4" /> Run import
              </>
            )}
          </button>
        </div>

        {previewError && (
          <div className="text-sm text-rose-500 flex items-center gap-2">
            <AlertCircle className="size-4" /> {previewError}
          </div>
        )}

        {/* Preview panel */}
        {preview && (
          <div className="border border-border rounded-lg p-3 space-y-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <Stat label="Rows" value={preview.row_count} />
              <Stat label="Columns" value={preview.header_count} />
              <Stat
                label="With Symbol"
                value={preview.row_count - preview.rows_with_no_symbol}
                tone={preview.rows_with_no_symbol === 0 ? "ok" : "warn"}
              />
              <Stat
                label="No Symbol (will skip)"
                value={preview.rows_with_no_symbol}
                tone={preview.rows_with_no_symbol > 0 ? "warn" : "ok"}
              />
            </div>

            {!preview.has_symbol_column && (
              <div className="text-sm text-rose-500 flex items-center gap-2">
                <AlertCircle className="size-4" />
                CSV is missing a <code>Symbol</code> column — every row will be skipped.
              </div>
            )}

            {preview.samples.length > 0 && (
              <div className="overflow-auto">
                <table className="w-full text-xs">
                  <thead className="text-ink-muted">
                    <tr>
                      <th className="text-left py-1 pr-3">Ticker</th>
                      <th className="text-left py-1 pr-3">Company</th>
                      <th className="text-left py-1 pr-3">Sector</th>
                      <th className="text-right py-1 pr-3">Price</th>
                      <th className="text-right py-1 pr-3">Mkt Cap</th>
                      <th className="text-right py-1 pr-3">PE</th>
                      <th className="text-left py-1">Last Report</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.samples.map((s, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="py-1 pr-3 font-medium">{s.ticker ?? "—"}</td>
                        <td className="py-1 pr-3">{s.company_name ?? "—"}</td>
                        <td className="py-1 pr-3">{s.sector ?? "—"}</td>
                        <td className="py-1 pr-3 text-right">{s.stock_price ?? "—"}</td>
                        <td className="py-1 pr-3 text-right">{s.market_cap ?? "—"}</td>
                        <td className="py-1 pr-3 text-right">{s.pe_ratio ?? "—"}</td>
                        <td className="py-1">{s.last_report_date ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.samples.length < preview.row_count && (
                  <div className="text-[11px] text-ink-muted mt-1">
                    Showing first {preview.samples.length} of {preview.row_count} rows.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {runError && (
          <div className="text-sm text-rose-500 flex items-center gap-2">
            <AlertCircle className="size-4" /> {runError}
          </div>
        )}

        {/* Result panel */}
        {result && (
          <div className="border border-border rounded-lg p-3 space-y-2">
            <div className="flex items-center gap-2">
              {result.status === "ok" ? (
                <CheckCircle2 className="size-4 text-emerald-500" />
              ) : (
                <XCircle className="size-4 text-rose-500" />
              )}
              <span className="text-sm font-medium">
                Import #{result.import_id} — {result.status}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
              <Stat label="Total" value={result.rows_total} />
              <Stat label="Inserted" value={result.rows_inserted} tone="ok" />
              <Stat label="Updated" value={result.rows_updated} tone="ok" />
              <Stat label="Skipped" value={result.rows_skipped} tone="warn" />
              <Stat
                label="Errored"
                value={result.rows_errored}
                tone={result.rows_errored > 0 ? "bad" : "ok"}
              />
            </div>

            {result.row_logs.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-ink-muted">
                  Show row log ({result.row_logs.length} entries)
                </summary>
                <div className="mt-2 max-h-64 overflow-auto border border-border rounded p-2 font-mono">
                  {result.row_logs.map((log, i) => (
                    <div
                      key={i}
                      className={
                        log.action === "error"
                          ? "text-rose-500"
                          : log.action === "skipped"
                          ? "text-amber-500"
                          : "text-ink-muted"
                      }
                    >
                      row {log.row_number}: [{log.action}] {log.message}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* History */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold mb-3">Recent imports</h3>
        {!history?.length ? (
          <p className="text-ink-muted text-sm">No imports yet.</p>
        ) : (
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="text-ink-muted">
                <tr>
                  <th className="text-left py-1 pr-3">When</th>
                  <th className="text-left py-1 pr-3">Exchange</th>
                  <th className="text-left py-1 pr-3">User</th>
                  <th className="text-left py-1 pr-3">File</th>
                  <th className="text-right py-1 pr-3">Total</th>
                  <th className="text-right py-1 pr-3">Inserted</th>
                  <th className="text-right py-1 pr-3">Updated</th>
                  <th className="text-right py-1 pr-3">Errored</th>
                  <th className="text-left py-1">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className="border-t border-border">
                    <td className="py-1 pr-3">{fmtDate(h.started_at)}</td>
                    <td className="py-1 pr-3 uppercase">{h.exchange_code}</td>
                    <td className="py-1 pr-3 text-ink-muted">{h.user_email ?? "—"}</td>
                    <td className="py-1 pr-3 text-ink-muted truncate max-w-[200px]">
                      {h.filename ?? "—"}
                    </td>
                    <td className="py-1 pr-3 text-right">{h.rows_total}</td>
                    <td className="py-1 pr-3 text-right text-emerald-500">
                      {h.rows_inserted}
                    </td>
                    <td className="py-1 pr-3 text-right">{h.rows_updated}</td>
                    <td
                      className={
                        "py-1 pr-3 text-right " +
                        (h.rows_errored > 0 ? "text-rose-500" : "text-ink-muted")
                      }
                    >
                      {h.rows_errored}
                    </td>
                    <td className="py-1">
                      <span
                        className={
                          "px-1.5 py-0.5 rounded text-[10px] " +
                          (h.status === "ok"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : h.status === "failed"
                            ? "bg-rose-500/10 text-rose-500"
                            : "bg-amber-500/10 text-amber-500")
                        }
                      >
                        {h.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({
  label, value, tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}) {
  const toneClass =
    tone === "ok" ? "text-emerald-500"
    : tone === "warn" ? "text-amber-500"
    : tone === "bad" ? "text-rose-500"
    : "text-ink";
  return (
    <div className="border border-border rounded p-2">
      <div className="text-[10px] uppercase tracking-wide text-ink-muted">
        {label}
      </div>
      <div className={"text-base font-semibold " + toneClass}>{value}</div>
    </div>
  );
}
