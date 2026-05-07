"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { fmtDate } from "@/lib/utils";
import { Plus, Trash2, RefreshCw, Wifi, WifiOff, ShieldCheck } from "lucide-react";


export default function ProfilePage() {
  const { user } = useAuth();
  const [showAdd, setShowAdd] = useState(false);

  const { data: accounts, isLoading } = useSWR("accounts", () => api.listAccounts());

  return (
    <div className="container-narrow">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Profile</h1>
        <p className="text-ink-muted">{user?.email}{user?.is_admin ? " · admin" : ""}</p>
      </header>

      <section className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Trading accounts</h2>
            <p className="text-xs text-ink-muted">
              Connect brokers (Capital.com) for automated trading, or add manual accounts (Thndr, others) to track positions and trades.
            </p>
          </div>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>
            <Plus className="size-4" /> Add account
          </button>
        </div>

        {isLoading && <div className="text-ink-muted">Loading…</div>}
        {!isLoading && accounts?.length === 0 && (
          <div className="text-sm text-ink-muted py-4">
            No accounts yet. Add one to start tracking positions and placing orders.
          </div>
        )}

        <div className="space-y-2">
          {accounts?.map(acct => <AccountCard key={acct.id} acct={acct} />)}
        </div>
      </section>

      {showAdd && (
        <AddAccountModal
          onClose={() => setShowAdd(false)}
          onSaved={() => { mutate("accounts"); setShowAdd(false); }}
        />
      )}
    </div>
  );
}


function AccountCard({ acct }: { acct: any }) {
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function test() {
    setTesting(true); setResult(null);
    try {
      const r = await api.testAccount(acct.id);
      setResult(r.ok ? `OK — ${r.message}` : `FAIL — ${r.message}`);
      mutate("accounts");
    } catch (e: any) {
      setResult(`Error: ${e.message}`);
    } finally {
      setTesting(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete account "${acct.label}"? Order history is preserved.`)) return;
    await api.deleteAccount(acct.id);
    mutate("accounts");
  }

  const statusIcon = acct.broker_kind === "manual"
    ? <ShieldCheck className="size-4 text-ink-muted" />
    : (acct.last_connect_status === "ok"
        ? <Wifi className="size-4 text-verdict-buy" />
        : <WifiOff className="size-4 text-ink-muted" />);

  return (
    <div className="rounded-lg bg-bg-subtle p-4 flex items-center justify-between">
      <div className="flex items-start gap-3">
        {statusIcon}
        <div>
          <div className="font-medium">
            {acct.label} <span className="text-ink-dim text-sm">· {acct.broker_name}</span>
            {acct.broker_kind === "manual" && (
              <span className="badge ml-2 bg-bg-elevated text-ink-muted ring-1 ring-border">manual</span>
            )}
          </div>
          <div className="text-xs text-ink-dim mt-0.5">
            {acct.currency || "—"}
            {acct.last_connect_at && (<> · last checked {fmtDate(acct.last_connect_at)}</>)}
            {acct.last_connect_status === "error" && acct.last_connect_error && (
              <> · <span className="text-verdict-avoid">{acct.last_connect_error}</span></>
            )}
          </div>
          {result && <div className="text-xs mt-1">{result}</div>}
        </div>
      </div>
      <div className="flex gap-1">
        {acct.broker_kind === "automated" && (
          <button className="btn-ghost" onClick={test} disabled={testing}>
            <RefreshCw className={`size-4 ${testing ? "animate-spin" : ""}`} /> Test
          </button>
        )}
        <button className="btn-ghost" onClick={remove}><Trash2 className="size-4" /></button>
      </div>
    </div>
  );
}


function AddAccountModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { data: brokers, isLoading: brokersLoading, error: brokersError } = useSWR("brokers", () => api.listBrokers());
  const [step, setStep] = useState<"pick" | "fill">("pick");
  const [chosen, setChosen] = useState<any | null>(null);
  const [label, setLabel] = useState("");
  const [currency, setCurrency] = useState("");
  const [creds, setCreds] = useState<Record<string, any>>({});
  const [displayMeta, setDisplayMeta] = useState<Record<string, any>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!chosen) return;
    if (!label.trim()) { setError("Label is required"); return; }
    setSubmitting(true);
    try {
      await api.createAccount({
        broker_code: chosen.code,
        label: label.trim(),
        currency: currency.trim() || undefined,
        credentials: chosen.kind === "automated" ? creds : {},
        display_metadata: displayMeta,
      });
      onSaved();
    } catch (e: any) {
      setError(e.message || "Failed to create account");
    } finally {
      setSubmitting(false);
    }
  }

  function setCredField(key: string, val: any) { setCreds({ ...creds, [key]: val }); }
  function setMetaField(key: string, val: any) { setDisplayMeta({ ...displayMeta, [key]: val }); }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card p-5 w-full max-w-lg" onClick={e => e.stopPropagation()}>
        {step === "pick" && (
          <>
            <h3 className="font-semibold mb-3">Add a trading account</h3>
            <p className="text-xs text-ink-dim mb-4">Pick the broker. Automated brokers will need credentials in the next step.</p>

            {brokersLoading && <div className="text-sm text-ink-muted py-4">Loading brokers…</div>}
            {brokersError && (
              <div className="text-sm text-verdict-avoid py-4">
                Failed to load brokers: {String(brokersError.message || brokersError)}
              </div>
            )}
            {!brokersLoading && !brokersError && brokers?.length === 0 && (
              <div className="text-sm text-verdict-avoid py-4">
                No brokers available. Run the database migration{" "}
                <code className="px-1 rounded bg-bg-elevated">db/migrations/002_brokers.sql</code>.
              </div>
            )}

            <div className="grid gap-2">
              {brokers?.map(b => (
                <button key={b.id} className="rounded-lg bg-bg-subtle hover:bg-bg-elevated p-3 text-left transition-colors"
                        onClick={() => { setChosen(b); setStep("fill"); }}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">{b.name}</div>
                      <div className="text-xs text-ink-dim">{b.kind === "automated" ? "Live API connection" : "Track manually"}</div>
                    </div>
                    {b.kind === "automated"
                      ? <Wifi className="size-4 text-verdict-buy" />
                      : <ShieldCheck className="size-4 text-ink-muted" />}
                  </div>
                </button>
              ))}
            </div>
            <div className="flex justify-end mt-4">
              <button className="btn-ghost" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}

        {step === "fill" && chosen && (
          <>
            <h3 className="font-semibold mb-1">New {chosen.name} account</h3>
            {chosen.docs_url && (
              <p className="text-xs text-ink-dim mb-4">
                <a href={chosen.docs_url} target="_blank" rel="noreferrer" className="underline">API docs</a>
              </p>
            )}

            <div className="space-y-3">
              <div>
                <label className="label">Label</label>
                <input className="input mt-1" value={label} onChange={e => setLabel(e.target.value)}
                       placeholder={chosen.kind === "automated" ? "Capital live" : "Thndr real"} />
              </div>
              <div>
                <label className="label">Account currency (optional)</label>
                <input className="input mt-1 uppercase" maxLength={8}
                       value={currency} onChange={e => setCurrency(e.target.value)}
                       placeholder={chosen.kind === "automated" ? "USD" : "AED"} />
              </div>

              {(chosen.credential_schema || []).map((f: any) => (
                <div key={f.key}>
                  <label className="label">{f.label}{f.required && <span className="text-verdict-avoid"> *</span>}</label>
                  {f.type === "password" || f.type === "email" || f.type === "text" ? (
                    <input
                      className="input mt-1"
                      type={f.type === "password" ? "password" : (f.type === "email" ? "email" : "text")}
                      value={(chosen.kind === "automated" ? creds[f.key] : displayMeta[f.key]) ?? ""}
                      onChange={e => chosen.kind === "automated"
                        ? setCredField(f.key, e.target.value)
                        : setMetaField(f.key, e.target.value)}
                      autoComplete="off"
                    />
                  ) : f.type === "boolean" ? (
                    <label className="flex items-center gap-2 mt-1 text-sm">
                      <input type="checkbox" checked={!!creds[f.key]}
                             onChange={e => setCredField(f.key, e.target.checked)} />
                      <span>{f.label}</span>
                    </label>
                  ) : (
                    <input className="input mt-1" type="text"
                           value={(chosen.kind === "automated" ? creds[f.key] : displayMeta[f.key]) ?? ""}
                           onChange={e => chosen.kind === "automated"
                             ? setCredField(f.key, e.target.value)
                             : setMetaField(f.key, e.target.value)} />
                  )}
                </div>
              ))}

              {chosen.kind === "automated" && (
                <p className="text-xs text-ink-dim">
                  Credentials are encrypted at rest with AES-GCM. Only the broker_gateway service can decrypt them.
                </p>
              )}

              {error && <div className="text-sm text-verdict-avoid">{error}</div>}
            </div>

            <div className="flex gap-2 justify-end mt-4">
              <button className="btn-ghost"
                      onClick={() => { setStep("pick"); setChosen(null); setCreds({}); setDisplayMeta({}); }}>
                Back
              </button>
              <button className="btn-primary" onClick={submit} disabled={submitting}>
                {submitting ? "Saving…" : "Save account"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
