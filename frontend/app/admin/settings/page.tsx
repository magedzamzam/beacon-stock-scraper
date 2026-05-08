"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api, type JobSetting, type JobConfig } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import { Play, Pencil, Check, X as XIcon, Clock, AlertCircle, RefreshCw } from "lucide-react";


export default function AdminSettingsPage() {
  const { data: jobs, isLoading } = useSWR("admin:jobs", api.listJobSettings, { refreshInterval: 15000 });
  const { data: exchanges } = useSWR("admin-exchanges", () => api.adminListExchanges());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<{ key: string; result: string } | null>(null);

  async function runNow(key: string) {
    setRunning(key);
    setRunResult(null);
    try {
      const r = await api.runJob(key);
      setRunResult({ key, result: `${r.status}${r.message ? ": " + r.message : ""}` });
      mutate("admin:jobs");
    } catch (e: any) {
      setRunResult({ key, result: `failed: ${e.message || "unknown error"}` });
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <h3 className="font-semibold text-sm mb-1">Scheduled jobs</h3>
        <p className="text-xs text-ink-dim">
          Schedules are read from the database every 60 seconds, so edits take effect without
          restarting the scheduler. Crons use 5-field syntax:{" "}
          <code className="px-1 rounded bg-bg-elevated">minute hour day month dow</code>.
        </p>
      </div>

      {isLoading && <div className="card p-6 text-center text-ink-muted text-sm">Loading…</div>}

      <div className="space-y-3">
        {(jobs || []).map((j) => (
          <JobCard
            key={j.key}
            job={j}
            running={running === j.key}
            runResult={runResult?.key === j.key ? runResult.result : null}
            exchanges={(exchanges || []).map(x => x.code)}
            onRunNow={() => runNow(j.key)}
            onEdit={() => setEditingKey(j.key)}
          />
        ))}
      </div>

      {editingKey && (
        <EditJobModal
          job={(jobs || []).find(j => j.key === editingKey)!}
          exchanges={(exchanges || []).map(x => x.code)}
          onClose={() => setEditingKey(null)}
          onSaved={() => { mutate("admin:jobs"); setEditingKey(null); }}
        />
      )}
    </div>
  );
}


function JobCard({
  job, running, runResult, exchanges, onRunNow, onEdit,
}: {
  job: JobSetting;
  running: boolean;
  runResult: string | null;
  exchanges: string[];
  onRunNow: () => void;
  onEdit: () => void;
}) {
  const lr = job.last_run;
  const statusTone =
    !lr ? "text-ink-dim" :
    lr.status === "ok" ? "text-verdict-buy" :
    lr.status === "failed" ? "text-verdict-avoid" :
    "text-ink-muted";

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-semibold">{job.label}</h4>
            {!job.config.enabled && (
              <span className="badge bg-bg-elevated text-ink-muted">disabled</span>
            )}
            {job.config.enabled && (
              <span className="badge bg-verdict-buy/15 text-verdict-buy">enabled</span>
            )}
          </div>
          <p className="text-xs text-ink-muted mt-1">{job.purpose}</p>

          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-2 text-ink-muted">
              <Clock className="size-3.5" />
              <span className="font-mono">{job.config.cron}</span>
              <span className="text-ink-dim">({cronToHuman(job.config.cron)})</span>
            </div>
            {job.supports_exchanges && (
              <div className="text-ink-muted">
                Exchanges:{" "}
                <span className="font-medium">
                  {job.config.exchanges.length === 0
                    ? "all"
                    : job.config.exchanges.join(", ").toUpperCase()}
                </span>
              </div>
            )}
          </div>

          <div className={`mt-3 text-xs ${statusTone}`}>
            {lr ? (
              <span className="flex items-center gap-2">
                {lr.status === "ok" && <Check className="size-3.5" />}
                {lr.status === "failed" && <AlertCircle className="size-3.5" />}
                {lr.status === "running" && <RefreshCw className="size-3.5 animate-spin" />}
                Last run: {lr.status} ({lr.triggered_by}) — {fmtDate(lr.started_at)}
                {lr.duration_s != null && <span className="text-ink-dim">· {lr.duration_s.toFixed(1)}s</span>}
              </span>
            ) : (
              <span>No runs yet.</span>
            )}
          </div>

          {lr?.error_message && (
            <div className="mt-1 text-xs text-verdict-avoid truncate" title={lr.error_message}>
              {lr.error_message}
            </div>
          )}

          {runResult && (
            <div className="mt-2 text-xs text-ink-muted">
              Manual run → {runResult}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          <button onClick={onRunNow} disabled={running} className="btn-ghost text-sm">
            <Play className="size-3.5" /> {running ? "Running…" : "Run now"}
          </button>
          <button onClick={onEdit} className="btn-ghost text-sm">
            <Pencil className="size-3.5" /> Edit
          </button>
        </div>
      </div>
    </div>
  );
}


function EditJobModal({
  job, exchanges, onClose, onSaved,
}: {
  job: JobSetting;
  exchanges: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState(job.config.enabled);
  const [cron, setCron] = useState(job.config.cron);
  const [picked, setPicked] = useState<string[]>(job.config.exchanges);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleExchange(code: string) {
    setPicked(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);
  }

  async function save() {
    setError(null);
    const parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) {
      setError("Cron must have 5 fields: minute hour day month day-of-week");
      return;
    }
    setSaving(true);
    try {
      const body: JobConfig = {
        enabled,
        cron: cron.trim(),
        exchanges: picked,
        description: job.config.description ?? null,
      };
      await api.updateJobSetting(job.key, body);
      onSaved();
    } catch (e: any) {
      setError(e.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 className="font-semibold mb-3">Edit job — {job.label}</h3>
        <p className="text-xs text-ink-dim mb-4">{job.purpose}</p>

        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Enabled
          </label>

          <div>
            <label className="label">Cron schedule (5 fields)</label>
            <input
              className="input mt-1 font-mono"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 16 * * *"
            />
            <p className="text-[11px] text-ink-dim mt-1">
              {cronToHuman(cron)}. Format: <span className="font-mono">minute hour day month dow</span>.
            </p>
          </div>

          {job.supports_exchanges && (
            <div>
              <label className="label">Exchanges (none = all)</label>
              <div className="flex flex-wrap gap-2 mt-1">
                {exchanges.map(code => {
                  const active = picked.includes(code);
                  return (
                    <button
                      key={code}
                      type="button"
                      onClick={() => toggleExchange(code)}
                      className={`badge ${active
                        ? "bg-brand/15 text-brand ring-1 ring-brand/40"
                        : "bg-bg-subtle text-ink-muted hover:bg-bg-elevated"}`}
                    >
                      {code.toUpperCase()}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-ink-dim mt-1">
                Click a chip to toggle. Empty = scrape all exchanges.
              </p>
            </div>
          )}

          {error && <div className="text-sm text-verdict-avoid">{error}</div>}
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <button className="btn-ghost" onClick={onClose} disabled={saving}>
            <XIcon className="size-3.5" /> Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            <Check className="size-3.5" /> {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}


/** Translate a 5-field cron into a short English description. Best-effort. */
function cronToHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "Invalid cron";
  const [m, h, dom, mo, dow] = parts;

  // "0 16 * * *" → "Daily at 16:00"
  if (m !== "*" && h !== "*" && dom === "*" && mo === "*" && dow === "*") {
    return `Daily at ${h.padStart(2, "0")}:${m.padStart(2, "0")}`;
  }
  // "0 3 1 * *" → "Monthly on the 1st at 03:00"
  if (m !== "*" && h !== "*" && dom !== "*" && mo === "*" && dow === "*") {
    return `Monthly on day ${dom} at ${h.padStart(2, "0")}:${m.padStart(2, "0")}`;
  }
  // "15 */6 * * *" → "Every 6 hours at :15"
  if (h.startsWith("*/") && dom === "*" && mo === "*" && dow === "*") {
    const n = h.slice(2);
    return `Every ${n}h at :${m.padStart(2, "0")}`;
  }
  return "Custom schedule";
}
