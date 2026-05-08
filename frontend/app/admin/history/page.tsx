"use client";
import useSWR from "swr";
import { api } from "@/lib/api";


export default function AdminHistoryPage() {
  const { data: status } = useSWR("admin:status", api.adminStatus, { refreshInterval: 5000 });
  const runs = status?.scrape_runs ?? [];

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-border font-medium text-sm">Recent scrape runs</div>
      <div className="overflow-x-auto">
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
            {runs.map((r: any) => (
              <tr key={r.id} className="table-row">
                <td className="p-3 font-mono text-xs">{r.run_time ? new Date(r.run_time).toLocaleString() : "—"}</td>
                <td className="p-3 text-xs">{r.source || "—"}</td>
                <td className="p-3 text-xs">{r.ticker || "—"}</td>
                <td className="p-3">
                  <span className={`badge ${
                    r.status === "ok" || r.status === "completed"
                      ? "bg-verdict-buy/15 text-verdict-buy"
                      : r.status === "error" || r.status === "failed"
                        ? "bg-verdict-avoid/15 text-verdict-avoid"
                        : "bg-bg-elevated text-ink-muted"}`}>
                    {r.status || "—"}
                  </span>
                </td>
                <td className="p-3 text-right font-mono text-xs">{r.http_status ?? "—"}</td>
                <td className="p-3 text-xs text-ink-muted truncate max-w-[280px]">{r.error_message || "—"}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6} className="p-6 text-center text-ink-muted text-sm">No runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
