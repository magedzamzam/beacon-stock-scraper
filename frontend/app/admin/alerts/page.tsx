"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  Bell, Plus, Trash2, Play, Send, AlertCircle, CheckCircle2, XCircle,
  Loader2, RefreshCw, ToggleLeft, ToggleRight, ChevronDown, ChevronRight,
} from "lucide-react";
import {
  api,
  type AlertChannelInput, type AlertChannelRow,
  type AlertRuleInput, type AlertRuleRow,
  type AlertSchemaField, type AlertsMeta,
} from "@/lib/api";
import { fmtDate } from "@/lib/utils";

/**
 * Alerts admin page.
 *
 * Three panels:
 *   - Channels: where alerts go (email/telegram/webhook/sms)
 *   - Rules:    what triggers alerts
 *   - Events:   recent fire history
 *
 * Channel + rule forms are rendered DYNAMICALLY from the /admin/alerts/meta
 * endpoint's schema metadata, so adding a new rule_type or channel_type
 * server-side requires no frontend changes.
 */
export default function AdminAlertsPage() {
  const { data: meta } = useSWR("alerts:meta", api.alertsMeta);
  const { data: channels, mutate: reloadChannels } = useSWR(
    "alerts:channels", api.alertChannels,
  );
  const { data: rules, mutate: reloadRules } = useSWR(
    "alerts:rules", api.alertRules,
  );
  const { data: events, mutate: reloadEvents } = useSWR(
    "alerts:events", () => api.alertEvents(50),
    { refreshInterval: 30_000 },
  );

  const [showChannelForm, setShowChannelForm] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluateMsg, setEvaluateMsg] = useState<string | null>(null);

  async function evaluateNow() {
    setEvaluating(true);
    setEvaluateMsg(null);
    try {
      const s = await api.evaluateAlertsNow();
      setEvaluateMsg(
        `Done. Evaluated ${s.rules_evaluated}/${s.rules_total} rules · ` +
        `fired ${s.alerts_fired} · skipped (cooldown) ${s.alerts_skipped_cooldown}` +
        (s.rules_errored ? ` · errored ${s.rules_errored}` : ""),
      );
      reloadEvents();
      reloadRules();
    } catch (e: any) {
      setEvaluateMsg(`Failed: ${e.message}`);
    } finally {
      setEvaluating(false);
    }
  }

  if (!meta) {
    return (
      <div className="card p-8 text-center text-ink-muted">
        <Loader2 className="size-4 inline-block animate-spin mr-2" /> Loading…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Bell className="size-4" /> Alerts
          </h2>
          <p className="text-ink-muted text-xs mt-1">
            Rules + channels for notifying you when things happen.
            Rules run every minute server-side. Each rule has its own
            cooldown so the same alert doesn't fire repeatedly.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={evaluateNow} disabled={evaluating}
                  className="btn-ghost text-xs">
            {evaluating ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            Evaluate now
          </button>
        </div>
      </header>
      {evaluateMsg && (
        <div className="text-xs text-ink-muted">{evaluateMsg}</div>
      )}

      {/* Channels panel */}
      <section className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Channels</h3>
          <button onClick={() => setShowChannelForm(v => !v)}
                  className="btn-ghost text-xs">
            <Plus className="size-3.5" /> {showChannelForm ? "Cancel" : "Add channel"}
          </button>
        </div>
        {showChannelForm && (
          <ChannelForm
            meta={meta}
            onCancel={() => setShowChannelForm(false)}
            onSaved={() => { setShowChannelForm(false); reloadChannels(); }}
          />
        )}
        <ChannelList channels={channels || []}
                     onChange={() => reloadChannels()} />
      </section>

      {/* Rules panel */}
      <section className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Rules</h3>
          <button onClick={() => setShowRuleForm(v => !v)}
                  disabled={!channels?.length}
                  title={!channels?.length ? "Add a channel first" : ""}
                  className="btn-ghost text-xs">
            <Plus className="size-3.5" /> {showRuleForm ? "Cancel" : "Add rule"}
          </button>
        </div>
        {!channels?.length && (
          <div className="text-xs text-amber-500 flex items-center gap-1">
            <AlertCircle className="size-3.5" /> Add a channel before creating rules — rules need somewhere to send.
          </div>
        )}
        {showRuleForm && (
          <RuleForm
            meta={meta}
            channels={channels || []}
            onCancel={() => setShowRuleForm(false)}
            onSaved={() => { setShowRuleForm(false); reloadRules(); }}
          />
        )}
        <RuleList rules={rules || []} channels={channels || []}
                  onChange={() => { reloadRules(); reloadEvents(); }} />
      </section>

      {/* Events panel */}
      <section className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Recent alerts</h3>
          <button onClick={() => reloadEvents()} className="btn-ghost text-xs">
            <RefreshCw className="size-3.5" /> Refresh
          </button>
        </div>
        <EventList events={events || []} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Channels
// ---------------------------------------------------------------------------
function ChannelList({ channels, onChange }: {
  channels: AlertChannelRow[];
  onChange: () => void;
}) {
  async function toggle(c: AlertChannelRow) {
    await api.updateAlertChannel(c.id, { is_active: !c.is_active });
    onChange();
  }
  async function del(c: AlertChannelRow) {
    if (!confirm(`Delete channel "${c.name}"? Rules using it will stop firing through this channel.`)) return;
    await api.deleteAlertChannel(c.id);
    onChange();
  }

  if (!channels.length) {
    return <div className="text-xs text-ink-muted">No channels yet.</div>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full text-xs">
        <thead className="text-ink-muted">
          <tr>
            <th className="text-left py-1 pr-3">Name</th>
            <th className="text-left py-1 pr-3">Type</th>
            <th className="text-left py-1 pr-3">Config</th>
            <th className="text-left py-1 pr-3">Status</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {channels.map(c => (
            <tr key={c.id} className="border-t border-border">
              <td className="py-2 pr-3 font-medium">{c.name}</td>
              <td className="py-2 pr-3 uppercase text-ink-muted">{c.channel_type}</td>
              <td className="py-2 pr-3 text-ink-muted truncate max-w-[280px]">
                {summarizeConfig(c.config)}
              </td>
              <td className="py-2 pr-3">
                <button onClick={() => toggle(c)} className="flex items-center gap-1 text-xs">
                  {c.is_active
                    ? <><ToggleRight className="size-4 text-emerald-500" /> Active</>
                    : <><ToggleLeft className="size-4 text-ink-muted" /> Off</>}
                </button>
              </td>
              <td className="py-2 text-right">
                <button onClick={() => del(c)} className="text-rose-500 hover:opacity-80">
                  <Trash2 className="size-3.5" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function summarizeConfig(config: Record<string, unknown>): string {
  // Show non-secret keys, mask secrets. Same rules wherever a "config" field is
  // marked password in the schema — we use a hard-coded list here for simplicity.
  const SECRETS = new Set(["bot_token", "smtp_pass", "twilio_token"]);
  const parts: string[] = [];
  for (const [k, v] of Object.entries(config || {})) {
    if (v == null || v === "") continue;
    if (SECRETS.has(k)) parts.push(`${k}=***`);
    else parts.push(`${k}=${String(v).slice(0, 30)}`);
  }
  return parts.join(", ") || "—";
}

function ChannelForm({ meta, onCancel, onSaved }: {
  meta: AlertsMeta;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [channelType, setChannelType] = useState(meta.channels[0]?.key || "");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const schema = useMemo(
    () => meta.channels.find(c => c.key === channelType)?.config_schema || [],
    [channelType, meta],
  );

  // Reset config when switching type — fields differ per channel.
  useEffect(() => { setConfig({}); }, [channelType]);

  async function save() {
    setError(null); setSaving(true);
    try {
      const body: AlertChannelInput = { name, channel_type: channelType, config };
      await api.createAlertChannel(body);
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-border rounded p-3 space-y-3 bg-bg-subtle/30">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="block text-xs">
          <span className="text-ink-muted">Name</span>
          <input className="input mt-1 w-full" value={name}
                 onChange={e => setName(e.target.value)}
                 placeholder="My Telegram bot" />
        </label>
        <label className="block text-xs">
          <span className="text-ink-muted">Channel type</span>
          <select className="input mt-1 w-full" value={channelType}
                  onChange={e => setChannelType(e.target.value)}>
            {meta.channels.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </label>
      </div>
      <DynamicFields schema={schema} values={config} onChange={setConfig} />
      {error && <div className="text-xs text-rose-500">{error}</div>}
      <div className="flex gap-2">
        <button onClick={save} disabled={saving || !name || !channelType}
                className="btn-primary text-xs">
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
          Save channel
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------
function RuleList({ rules, channels, onChange }: {
  rules: AlertRuleRow[];
  channels: AlertChannelRow[];
  onChange: () => void;
}) {
  const channelById = useMemo(() => {
    const m: Record<number, AlertChannelRow> = {};
    for (const c of channels) m[c.id] = c;
    return m;
  }, [channels]);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<Record<number, string>>({});

  async function toggle(r: AlertRuleRow) {
    setBusyId(r.id);
    await api.updateAlertRule(r.id, { is_enabled: !r.is_enabled });
    setBusyId(null);
    onChange();
  }
  async function del(r: AlertRuleRow) {
    if (!confirm(`Delete rule "${r.name}"?`)) return;
    await api.deleteAlertRule(r.id);
    onChange();
  }
  async function testFire(r: AlertRuleRow) {
    setBusyId(r.id);
    setTestResult(t => ({ ...t, [r.id]: "" }));
    try {
      const out = await api.testFireAlertRule(r.id);
      // Render channel statuses inline
      const ok = Object.values(out.delivery).filter(d => d.status === "ok").length;
      const tot = Object.keys(out.delivery).length;
      const errs = Object.entries(out.delivery)
        .filter(([_, d]) => d.status !== "ok")
        .map(([cid, d]) => `${cid}: ${d.error || "failed"}`)
        .join("; ");
      setTestResult(t => ({
        ...t,
        [r.id]: tot === 0
          ? "No channels wired."
          : `${ok}/${tot} delivered${errs ? " — " + errs : ""}`,
      }));
    } catch (e: any) {
      setTestResult(t => ({ ...t, [r.id]: `Failed: ${e.message}` }));
    } finally {
      setBusyId(null);
    }
  }

  if (!rules.length) {
    return <div className="text-xs text-ink-muted">No rules yet.</div>;
  }

  return (
    <div className="space-y-2">
      {rules.map(r => {
        const expanded = expandedId === r.id;
        return (
          <div key={r.id} className="border border-border rounded">
            <div className="flex items-center gap-2 px-3 py-2">
              <button onClick={() => setExpandedId(expanded ? null : r.id)}
                      className="text-ink-muted">
                {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{r.name}</span>
                  <span className="text-[10px] uppercase tracking-wide text-ink-muted">
                    {r.rule_type}
                  </span>
                </div>
                <div className="text-[11px] text-ink-muted flex items-center gap-3">
                  <span>every {r.interval_seconds}s</span>
                  <span>cooldown {r.cooldown_seconds}s</span>
                  <span>
                    channels: {r.channel_ids.map(id => channelById[id]?.name || `#${id}`).join(", ") || "—"}
                  </span>
                  {r.last_evaluated_at && (
                    <span>last eval {fmtDate(r.last_evaluated_at)}</span>
                  )}
                </div>
                {r.last_error && (
                  <div className="text-[11px] text-rose-500 mt-0.5 truncate">
                    {r.last_error}
                  </div>
                )}
                {testResult[r.id] && (
                  <div className="text-[11px] text-emerald-500 mt-0.5">
                    {testResult[r.id]}
                  </div>
                )}
              </div>
              <button onClick={() => toggle(r)} disabled={busyId === r.id}
                      className="text-xs flex items-center gap-1">
                {r.is_enabled
                  ? <><ToggleRight className="size-4 text-emerald-500" /> On</>
                  : <><ToggleLeft className="size-4 text-ink-muted" /> Off</>}
              </button>
              <button onClick={() => testFire(r)} disabled={busyId === r.id}
                      className="btn-ghost text-xs">
                <Send className="size-3.5" /> Test
              </button>
              <button onClick={() => del(r)} className="text-rose-500 hover:opacity-80">
                <Trash2 className="size-3.5" />
              </button>
            </div>
            {expanded && (
              <div className="px-3 pb-3 pt-1 border-t border-border bg-bg-subtle/20">
                <RuleParamsView rule={r} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RuleParamsView({ rule }: { rule: AlertRuleRow }) {
  return (
    <div className="text-xs space-y-1">
      <div className="text-ink-muted">Parameters:</div>
      <pre className="bg-bg p-2 rounded overflow-x-auto text-[11px]">
        {JSON.stringify(rule.params, null, 2)}
      </pre>
    </div>
  );
}

function RuleForm({ meta, channels, onCancel, onSaved }: {
  meta: AlertsMeta;
  channels: AlertChannelRow[];
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState(meta.rules[0]?.key || "");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [intervalS, setIntervalS] = useState(60);
  const [cooldownS, setCooldownS] = useState(3600);
  const [channelIds, setChannelIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const ruleMeta = useMemo(
    () => meta.rules.find(r => r.key === ruleType),
    [ruleType, meta],
  );

  useEffect(() => { setParams({}); }, [ruleType]);

  async function save() {
    setError(null); setSaving(true);
    try {
      const body: AlertRuleInput = {
        name,
        rule_type: ruleType,
        params,
        interval_seconds: intervalS,
        cooldown_seconds: cooldownS,
        channel_ids: channelIds,
        is_enabled: true,
      };
      await api.createAlertRule(body);
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-border rounded p-3 space-y-3 bg-bg-subtle/30">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="block text-xs">
          <span className="text-ink-muted">Name</span>
          <input className="input mt-1 w-full" value={name}
                 onChange={e => setName(e.target.value)}
                 placeholder="Alert me when AAPL hits BUY" />
        </label>
        <label className="block text-xs">
          <span className="text-ink-muted">Rule type</span>
          <select className="input mt-1 w-full" value={ruleType}
                  onChange={e => setRuleType(e.target.value)}>
            {meta.rules.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          {ruleMeta?.description && (
            <span className="text-[11px] text-ink-muted block mt-0.5">
              {ruleMeta.description}
            </span>
          )}
        </label>
      </div>
      <DynamicFields schema={ruleMeta?.params_schema || []} values={params} onChange={setParams} />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <label className="block text-xs">
          <span className="text-ink-muted">Evaluate every (seconds)</span>
          <input type="number" min={10} max={86400} className="input mt-1 w-full"
                 value={intervalS}
                 onChange={e => setIntervalS(Number(e.target.value))} />
        </label>
        <label className="block text-xs">
          <span className="text-ink-muted">Cooldown per stock (seconds)</span>
          <input type="number" min={0} max={7 * 86400} className="input mt-1 w-full"
                 value={cooldownS}
                 onChange={e => setCooldownS(Number(e.target.value))} />
        </label>
        <div>
          <span className="text-xs text-ink-muted">Channels</span>
          <div className="mt-1 space-y-1 max-h-28 overflow-auto border border-border rounded p-2">
            {channels.map(c => (
              <label key={c.id} className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={channelIds.includes(c.id)}
                       onChange={e => {
                         setChannelIds(ids =>
                           e.target.checked
                             ? [...ids, c.id]
                             : ids.filter(x => x !== c.id),
                         );
                       }} />
                <span>{c.name} <span className="text-ink-muted">({c.channel_type})</span></span>
              </label>
            ))}
          </div>
        </div>
      </div>
      {error && <div className="text-xs text-rose-500">{error}</div>}
      <div className="flex gap-2">
        <button onClick={save} disabled={saving || !name || !ruleType || !channelIds.length}
                className="btn-primary text-xs">
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
          Save rule
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------
function EventList({ events }: { events: any[] }) {
  if (!events.length) {
    return <div className="text-xs text-ink-muted">No alerts have fired yet.</div>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full text-xs">
        <thead className="text-ink-muted">
          <tr>
            <th className="text-left py-1 pr-3">When</th>
            <th className="text-left py-1 pr-3">Rule</th>
            <th className="text-left py-1 pr-3">Title</th>
            <th className="text-left py-1 pr-3">Delivery</th>
          </tr>
        </thead>
        <tbody>
          {events.map(e => {
            const total = Object.keys(e.delivery || {}).length;
            const ok = Object.values(e.delivery || {})
              .filter((d: any) => d.status === "ok").length;
            const allOk = total > 0 && ok === total;
            const noChannels = total === 0;
            return (
              <tr key={e.id} className="border-t border-border align-top">
                <td className="py-1.5 pr-3 whitespace-nowrap text-ink-muted">
                  {fmtDate(e.fired_at)}
                </td>
                <td className="py-1.5 pr-3 text-ink-muted">{e.rule_name}</td>
                <td className="py-1.5 pr-3">
                  <div className="font-medium">{e.title}</div>
                  {e.body && <div className="text-ink-muted text-[11px]">{e.body}</div>}
                </td>
                <td className="py-1.5 pr-3">
                  {noChannels
                    ? <span className="text-amber-500">No channels</span>
                    : allOk
                      ? <span className="text-emerald-500 flex items-center gap-1">
                          <CheckCircle2 className="size-3.5" /> {ok}/{total}
                        </span>
                      : <span className="text-rose-500 flex items-center gap-1">
                          <XCircle className="size-3.5" /> {ok}/{total}
                        </span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dynamic form fields driven by AlertSchemaField[]
// ---------------------------------------------------------------------------
function DynamicFields({ schema, values, onChange }: {
  schema: AlertSchemaField[];
  values: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  if (!schema.length) return null;
  function set(name: string, val: unknown) {
    onChange({ ...values, [name]: val });
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {schema.map(f => (
        <label key={f.name} className="block text-xs">
          <span className="text-ink-muted">
            {f.label}{f.required && <span className="text-rose-500"> *</span>}
          </span>
          {f.type === "select" ? (
            <select className="input mt-1 w-full"
                    value={(values[f.name] as string) ?? f.default ?? ""}
                    onChange={e => set(f.name, e.target.value)}>
              {(f.options || []).map(opt => (
                <option key={opt} value={opt}>{opt || "—"}</option>
              ))}
            </select>
          ) : f.type === "textarea" ? (
            <textarea className="input mt-1 w-full font-mono text-[11px]" rows={5}
                      value={(values[f.name] as string) ?? ""}
                      placeholder={f.placeholder}
                      onChange={e => set(f.name, e.target.value)} />
          ) : f.type === "number" ? (
            <input type="number" className="input mt-1 w-full"
                   min={f.min} max={f.max} step={f.step}
                   value={(values[f.name] as number) ?? f.default ?? ""}
                   onChange={e => set(f.name, e.target.value === "" ? "" : Number(e.target.value))} />
          ) : f.type === "password" ? (
            <input type="password" className="input mt-1 w-full"
                   value={(values[f.name] as string) ?? ""}
                   placeholder={f.placeholder}
                   onChange={e => set(f.name, e.target.value)} />
          ) : (
            <input type="text" className="input mt-1 w-full"
                   value={(values[f.name] as string) ?? ""}
                   placeholder={f.placeholder}
                   onChange={e => set(f.name, e.target.value)} />
          )}
        </label>
      ))}
    </div>
  );
}
