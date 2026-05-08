"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/utils";
import { RefreshCw, PlayCircle, Brain, Briefcase, Database } from "lucide-react";


export default function AdminOverviewPage() {
  const { data: status } = useSWR("admin:status", api.adminStatus, { refreshInterval: 5000 });
  const [running, setRunning] = useState<string | null>(null);

  async function run(name: string, fn: () => Promise<any>) {
    setRunning(name);
    try { await fn(); } catch (e: any) { alert(e.message); }
    finally { setTimeout(() => { setRunning(null); mutate("admin:status"); }, 1500); }
  }

  return (
    <div className="space-y-5">
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
