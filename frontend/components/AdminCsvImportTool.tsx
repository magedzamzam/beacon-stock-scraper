"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { AlertCircle, CheckCircle2, Download, FileUp, RotateCcw, Table2 } from "lucide-react";
import { api, type ImportExecuteResult, type ImportPreview, type ImportTable, type ImportTableColumn } from "@/lib/api";
import { cn, fmtDate } from "@/lib/utils";

const TABLE_ORDER = (a: ImportTable, b: ImportTable) => a.label.localeCompare(b.label);

function normalize(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "").trim();
}

function splitWords(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").split(/\s+/).filter(Boolean);
}

function scoreHeaderMatch(column: ImportTableColumn, header: string) {
  const cnorm = normalize(column.name);
  const hnorm = normalize(header);
  if (!cnorm || !hnorm) return 0;
  if (cnorm === hnorm) return 100;
  const cwords = splitWords(column.name);
  const hwords = splitWords(header);
  let score = 0;
  if (cwords.some((w) => hwords.includes(w))) score += 25;
  if (hnorm.includes(cnorm) || cnorm.includes(hnorm)) score += 35;
  const aliases: Record<string, string[]> = {
    ticker: ["symbol", "stocksymbol", "tickersymbol"],
    exchange_code: ["exchange", "market", "exchangecode"],
    company_name: ["company", "name", "companyname"],
    last_close: ["close", "closingprice", "price", "lastprice"],
    open_price: ["open", "openingprice"],
    news_date: ["date", "published", "publisheddate", "postdate"],
    source_code: ["source", "publisher"],
    sentiment_label: ["sentiment", "label"],
    sentiment_score: ["sentimentscore", "score"],
    analyst_target: ["target", "targetprice"],
    analyst_count: ["analysts", "count"],
    analyst_rating: ["rating", "recommendation"],
  };
  const colAliases = aliases[cnorm] || [];
  for (const alias of colAliases) {
    if (hnorm === alias || hnorm.includes(alias) || alias.includes(hnorm)) score += 20;
  }
  return score;
}

function buildInitialMapping(table: ImportTable | undefined, headers: string[]) {
  const out: Record<string, string> = {};
  if (!table || headers.length === 0) return out;
  for (const col of table.columns) {
    let best = "";
    let bestScore = 0;
    for (const header of headers) {
      const score = scoreHeaderMatch(col, header);
      if (score > bestScore) {
        best = header;
        bestScore = score;
      }
    }
    if (bestScore >= 40) out[col.name] = best;
  }
  return out;
}

function buildInitialMatchColumns(table: ImportTable | undefined) {
  if (!table) return [] as string[];
  return table.suggested_match_columns?.length ? table.suggested_match_columns : table.primary_key;
}

function invertMapping(mappingByDb: Record<string, string>) {
  const out: Record<string, string> = {};
  Object.entries(mappingByDb).forEach(([dbCol, csvCol]) => {
    if (csvCol) out[csvCol] = dbCol;
  });
  return out;
}

export default function AdminCsvImportTool() {
  const { data: catalog, isLoading: catalogLoading, error: catalogError } = useSWR("admin:import:catalog", api.adminImportCatalog);

  const tables = useMemo(() => (catalog?.tables || []).slice().sort(TABLE_ORDER), [catalog]);

  const [selectedTable, setSelectedTable] = useState<string>("");
  const [mode, setMode] = useState<"update" | "insert">("update");
  const [ignoreBlankValues, setIgnoreBlankValues] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mappingByDb, setMappingByDb] = useState<Record<string, string>>({});
  const [matchColumns, setMatchColumns] = useState<string[]>([]);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportExecuteResult | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);

  const currentTable = useMemo(() => tables.find((t) => t.name === selectedTable), [tables, selectedTable]);
  const headers = preview?.headers || [];

  useEffect(() => {
    if (!selectedTable && tables.length > 0) {
      setSelectedTable(tables[0].name);
    }
  }, [tables, selectedTable]);

  useEffect(() => {
    if (!currentTable || headers.length === 0) return;
    setMappingByDb(buildInitialMapping(currentTable, headers));
    setMatchColumns(buildInitialMatchColumns(currentTable));
  }, [currentTable, headers.join("|")]);

  function resetPreviewState() {
    setPreview(null);
    setMappingByDb({});
    setMatchColumns(buildInitialMatchColumns(currentTable));
    setResult(null);
    setError(null);
    setImportMessage(null);
  }

  async function handlePreview() {
    if (!file) {
      setError("Please choose a CSV file first.");
      return;
    }
    setBusy("preview");
    setError(null);
    setResult(null);
    setImportMessage(null);
    try {
      const res = await api.adminImportPreview(file);
      setPreview(res);
      setMappingByDb(buildInitialMapping(currentTable, res.headers));
      setMatchColumns(buildInitialMatchColumns(currentTable));
      setImportMessage(`Preview ready: ${res.row_count} rows detected.`);
    } catch (err: any) {
      setError(err.message || "Preview failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleImport() {
    if (!preview) {
      setError("Upload and preview a CSV file first.");
      return;
    }
    if (!currentTable) {
      setError("Choose a target table.");
      return;
    }
    const columnMapping = invertMapping(mappingByDb);
    if (Object.keys(columnMapping).length === 0) {
      setError("Map at least one CSV column to a database column.");
      return;
    }
    setBusy("import");
    setError(null);
    setImportMessage(null);
    try {
      const res = await api.adminImportExecute({
        import_id: preview.import_id,
        table_name: currentTable.name,
        mode,
        column_mapping: columnMapping,
        match_columns: matchColumns,
        ignore_blank_values: ignoreBlankValues,
      });
      setResult(res);
      setImportMessage(`Import finished: ${res.inserted} inserted, ${res.updated} updated, ${res.errors} errors.`);
    } catch (err: any) {
      setError(err.message || "Import failed");
    } finally {
      setBusy(null);
    }
  }

  const selectedColumns = currentTable?.columns || [];

  return (
    <div className="card p-4 md:p-5 space-y-5">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Table2 className="size-4 text-brand" /> CSV import tool
          </h3>
          <p className="text-xs text-ink-muted mt-1">
            Upload a CSV, preview it, map columns, choose insert or update, then write it into the database.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={resetPreviewState} disabled={!preview && !result && !file}>
            <RotateCcw className="size-4" /> Reset
          </button>
          <button className="btn-primary" onClick={handlePreview} disabled={!file || busy === "preview"}>
            <FileUp className="size-4" /> {busy === "preview" ? "Reading…" : "Preview CSV"}
          </button>
        </div>
      </div>

      {catalogError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
          Failed to load import catalog: {(catalogError as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="space-y-4 xl:col-span-1">
          <div className="card p-4 space-y-4">
            <div>
              <label className="label mb-2 block">CSV file</label>
              <input
                type="file"
                accept=".csv,text/csv"
                className="input"
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setPreview(null);
                  setResult(null);
                  setError(null);
                  setImportMessage(null);
                }}
              />
              <p className="mt-2 text-[11px] text-ink-dim">
                Any delimiter is allowed; the server auto-detects comma, semicolon, tab, or pipe.
              </p>
            </div>

            <div>
              <label className="label mb-2 block">Target table</label>
              <select
                className="input"
                value={selectedTable}
                onChange={(e) => {
                  setSelectedTable(e.target.value);
                  const table = tables.find((t) => t.name === e.target.value);
                  setMappingByDb(buildInitialMapping(table, headers));
                  setMatchColumns(buildInitialMatchColumns(table));
                }}
              >
                <option value="" disabled>{catalogLoading ? "Loading tables…" : "Choose a table"}</option>
                {tables.map((table) => (
                  <option key={table.name} value={table.name}>
                    {table.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="label mb-2">Import mode</div>
              <div className="grid grid-cols-2 gap-2">
                {(["update", "insert"] as const).map((m) => (
                  <button
                    key={m}
                    className={cn("btn-ghost", mode === m && "bg-brand text-white hover:bg-brand-dim")}
                    onClick={() => setMode(m)}
                    type="button"
                  >
                    {m.toUpperCase()}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-ink-dim">
                Update mode acts as an upsert using the match columns. Insert mode always creates new rows.
              </p>
            </div>

            <label className="flex items-start gap-3 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={ignoreBlankValues}
                onChange={(e) => setIgnoreBlankValues(e.target.checked)}
                className="mt-1"
              />
              <span>
                <span className="block font-medium">Ignore blank cells</span>
                <span className="block text-xs text-ink-muted">Blank CSV cells are skipped instead of overwriting existing values.</span>
              </span>
            </label>
          </div>

          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold">Match columns</h4>
              <span className="text-[11px] text-ink-dim">Used for update mode</span>
            </div>
            {currentTable ? (
              <div className="space-y-2 max-h-72 overflow-auto pr-1">
                {selectedColumns.filter((c) => c.primary_key || c.unique || currentTable.suggested_match_columns.includes(c.name)).map((col) => {
                  const checked = matchColumns.includes(col.name);
                  return (
                    <label key={col.name} className="flex items-center gap-3 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          setMatchColumns((prev) => e.target.checked
                            ? Array.from(new Set([...prev, col.name]))
                            : prev.filter((x) => x !== col.name));
                        }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{col.name}</span>
                        <span className="ml-2 text-[11px] text-ink-muted">{col.primary_key ? "PK" : col.unique ? "Unique" : "Suggested"}</span>
                      </span>
                    </label>
                  );
                })}
                {selectedColumns.filter((c) => c.primary_key || c.unique || currentTable.suggested_match_columns.includes(c.name)).length === 0 && (
                  <div className="text-xs text-ink-muted">This table does not expose a clear key. Choose a unique set of columns manually in the mapping below.</div>
                )}
              </div>
            ) : (
              <div className="text-xs text-ink-muted">Choose a table first.</div>
            )}
          </div>

          <div className="card p-4 space-y-3">
            <h4 className="text-sm font-semibold">Preview summary</h4>
            {preview ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between gap-2"><span className="text-ink-muted">File</span><span className="truncate max-w-[220px] text-right">{preview.filename}</span></div>
                <div className="flex justify-between gap-2"><span className="text-ink-muted">Rows</span><span>{preview.row_count}</span></div>
                <div className="flex justify-between gap-2"><span className="text-ink-muted">Delimiter</span><span>{preview.delimiter === "\t" ? "TAB" : preview.delimiter}</span></div>
                <div className="flex justify-between gap-2"><span className="text-ink-muted">Encoding</span><span>{preview.encoding}</span></div>
                <div className="flex justify-between gap-2"><span className="text-ink-muted">Last import</span><span>{fmtDate(result?.finished_at || null)}</span></div>
              </div>
            ) : (
              <div className="text-xs text-ink-muted">Upload a CSV and click Preview to inspect the data before importing.</div>
            )}
          </div>
        </div>

        <div className="space-y-4 xl:col-span-2">
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold">Column mapping</h4>
                <p className="text-xs text-ink-muted">Choose which CSV column populates each database field.</p>
              </div>
              <button className="btn-primary" onClick={handleImport} disabled={!preview || !currentTable || busy === "import"}>
                <Download className="size-4" /> {busy === "import" ? "Importing…" : "Run import"}
              </button>
            </div>

            {currentTable ? (
              <div className="max-h-[520px] overflow-auto rounded-xl border border-border">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-bg-subtle text-xs text-ink-muted">
                    <tr>
                      <th className="text-left p-3 w-[28%]">Database column</th>
                      <th className="text-left p-3 w-[27%]">Type</th>
                      <th className="text-left p-3 w-[31%]">CSV source</th>
                      <th className="text-left p-3 w-[14%]">Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedColumns.map((col) => (
                      <tr key={col.name} className="table-row align-top">
                        <td className="p-3">
                          <div className="font-medium">{col.name}</div>
                          <div className="text-[11px] text-ink-muted">
                            {col.foreign_key ? `FK → ${col.foreign_key}` : col.nullable ? "nullable" : "required"}
                          </div>
                        </td>
                        <td className="p-3 text-xs text-ink-muted">{col.type}</td>
                        <td className="p-3">
                          <select
                            className="input text-sm"
                            value={mappingByDb[col.name] || ""}
                            onChange={(e) => setMappingByDb((prev) => ({ ...prev, [col.name]: e.target.value }))}
                          >
                            <option value="">Skip column</option>
                            {headers.map((header) => (
                              <option key={header} value={header}>{header}</option>
                            ))}
                          </select>
                        </td>
                        <td className="p-3 text-xs text-ink-muted">
                          <div className="space-y-1">
                            {col.primary_key && <div className="badge bg-verdict-buy/15 text-verdict-buy">PK</div>}
                            {!col.primary_key && col.unique && <div className="badge bg-brand/15 text-brand">Unique</div>}
                            {matchColumns.includes(col.name) && <div className="badge bg-verdict-watch/15 text-verdict-watch">Match</div>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-6 text-sm text-ink-muted">
                Select a table to see available columns.
              </div>
            )}
          </div>

          {preview && (
            <div className="card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold">CSV preview</h4>
                  <p className="text-xs text-ink-muted">First rows from the uploaded file.</p>
                </div>
                <div className="text-xs text-ink-dim">{preview.row_count} rows detected</div>
              </div>
              <div className="overflow-auto rounded-xl border border-border max-h-[420px]">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-bg-subtle text-ink-muted">
                    <tr>
                      <th className="text-left p-2 w-20">Row</th>
                      {preview.headers.map((h) => (
                        <th key={h} className="text-left p-2 min-w-[160px]">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample_rows.map((row) => (
                      <tr key={row.row_number} className="table-row">
                        <td className="p-2 font-mono text-ink-muted">{row.row_number}</td>
                        {preview.headers.map((h) => (
                          <td key={h} className="p-2 whitespace-nowrap">{row.values[h] ?? ""}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-100 flex items-start gap-2">
          <AlertCircle className="size-4 mt-0.5 shrink-0" />
          <div>{error}</div>
        </div>
      )}

      {importMessage && !error && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-100 flex items-start gap-2">
          <CheckCircle2 className="size-4 mt-0.5 shrink-0" />
          <div>{importMessage}</div>
        </div>
      )}

      {result && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-medium text-sm">Import log</div>
              <div className="text-xs text-ink-muted">
                {result.table_name} · {result.mode.toUpperCase()} · {result.processed} processed
              </div>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="badge bg-bg-elevated text-ink-muted">Inserted {result.inserted}</span>
              <span className="badge bg-bg-elevated text-ink-muted">Updated {result.updated}</span>
              <span className="badge bg-bg-elevated text-ink-muted">Skipped {result.skipped}</span>
              <span className="badge bg-bg-elevated text-ink-muted">Errors {result.errors}</span>
            </div>
          </div>
          <div className="max-h-[320px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-subtle text-xs text-ink-muted">
                <tr>
                  <th className="text-left p-3">Row</th>
                  <th className="text-left p-3">Action</th>
                  <th className="text-left p-3">Message</th>
                </tr>
              </thead>
              <tbody>
                {result.row_logs.map((log) => (
                  <tr key={`${log.row_number}-${log.action}`} className="table-row align-top">
                    <td className="p-3 font-mono text-xs">{log.row_number}</td>
                    <td className="p-3 text-xs uppercase tracking-wide">{log.action}</td>
                    <td className="p-3 text-xs text-ink-muted">{log.message}</td>
                  </tr>
                ))}
                {result.row_logs.length === 0 && (
                  <tr><td colSpan={3} className="p-6 text-center text-ink-muted text-sm">No row logs.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
