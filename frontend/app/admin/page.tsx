"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { fmtDate } from "@/lib/utils";
import { RefreshCw, PlayCircle, Brain, Briefcase, Database } from "lucide-react";

export default function AdminPage() {
  const { user } = useAuth();
  const { data: status } = useSWR("admin:status", api.adminStatus, { refreshInterval: 5000 });
  const [running, setRunning] = useState<string | null>(null);

  if (!user?.is_admin) {
    return <div className="card p-8 text-center text-ink-muted">Admin only.</div>;
  }

  async function run(name: string, fn: () => Promise<any>) {
    setRunning(name);
    try { await fn(); } catch (e: any) { alert(e.message); }
    finally { setTimeout(() => { setRunning(null); mutate("admin:status"); }, 1500); }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <p className="text-ink-muted text-sm mt-1">Manual triggers, pipeline status, scrape logs.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat icon={<Database className="size-4" />} label="Stocks" value={status?.stock_count ?? "—"} />
        <Stat icon={<Brain className="size-4" />} label="Scored today" value={status?.scored_today ?? "—"} />
        <Stat icon={<Briefcase className="size-4" />} label="Open positions" value={status?.open_positions ?? "—"} />
        <Stat icon={<RefreshCw className="size-4" />} label="Last scrape" value={fmtDate(status?.last_scrape_at)} />
      </div>

      <div className="card p-4">
        <h3 className="text-sm font-semibold mb-3">Pipeline triggers</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <button className="btn-ghost justify-start" onClick={() => run("scrape", api.adminScrapeAll)}
                  disabled={running === "scrape"}>
            <PlayCircle className="size-4" /> {running === "scrape" ? "Starting…" : "Scrape all stocks"}
          </button>
          <button className="btn-ghost justify-start" onClick={() => run("sentiment", api.adminScoreSentiment)}
                  disabled={running === "sentiment"}>
            <Brain className="size-4" /> {running === "sentiment" ? "Scoring…" : "Score sentiment"}
          </button>
          <button className="btn-ghost justify-start" onClick={() => run("score", api.adminScoreAll)}
                  disabled={running === "score"}>
            <Brain className="size-4" /> {running === "score" ? "Starting…" : "Score all stocks"}
          </button>
          <button className="btn-ghost justify-start" onClick={() => run("port", api.adminScorePortfolio)}
                  disabled={running === "port"}>
            <Briefcase className="size-4" /> {running === "port" ? "Starting…" : "Score portfolios"}
          </button>
        </div>
        <p className="text-xs text-ink-dim mt-2">
          The scheduler runs the full pipeline daily at 11:00 Asia/Dubai. Use these for manual reruns.
        </p>
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-border font-medium text-sm">Recent scrape runs</div>
        <table className="w-full text-sm">
          <thead className="text-xs text-ink-muted bg-bg-subtle">
            <tr>
              <th className="text-left p-3">When</th>
              <th className="text-left p-3">Source</th>
              <th className="text-left p-3">Ticker</th>
              <th className="text-left p-3">Status</th>
              <th className="text-right p-3">HTTP</th>
              <th className="text-left p-3">Error</th>
            </tr>
          </thead>
          <tbody>
            {(status?.scrape_runs ?? []).map((r: any) => (
              <tr key={r.id} className="table-row">
                <td className="p-3 font-mono text-xs">{r.run_time ? new Date(r.run_time).toLocaleString() : "—"}</td>
                <td className="p-3 text-xs">{r.source || "—"}</td>
                <td className="p-3 text-xs">{r.ticker || "—"}</td>
                <td className="p-3">
                  <span className={`badge ${r.status === "ok" || r.status === "completed" ? "bg-verdict-buy/15 text-verdict-buy" : r.status === "error" || r.status === "failed" ? "bg-verdict-avoid/15 text-verdict-avoid" : "bg-bg-elevated text-ink-muted"}`}>
                    {r.status || "—"}
                  </span>
                </td>
                <td className="p-3 text-right font-mono text-xs">{r.http_status ?? "—"}</td>
                <td className="p-3 text-xs text-ink-muted truncate max-w-[280px]">{r.error_message || "—"}</td>
              </tr>
            ))}
            {(!status?.scrape_runs || status.scrape_runs.length === 0) && (
              <tr><td colSpan={6} className="p-6 text-center text-ink-muted text-sm">No runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: any }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-ink-muted flex items-center gap-2">{icon} {label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}
