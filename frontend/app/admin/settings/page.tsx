"use client";

export default function AdminSettingsPage() {
  return (
    <div className="card p-6">
      <h3 className="font-semibold mb-2">Settings</h3>
      <p className="text-sm text-ink-muted">
        Settings UI coming soon. Today's pipeline schedule, scoring weights and feature flags
        live in environment variables — see <code className="px-1 rounded bg-bg-elevated">docker-compose.yml</code>.
      </p>
    </div>
  );
}
