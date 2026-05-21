"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Bot, Plus, Pencil, Trash2, RefreshCw, AlertCircle, Search,
  CheckCircle2, ToggleLeft, ToggleRight, Loader2,
} from "lucide-react";
import {
  api,
  type TgChannelInput, type TgChannelRow, type TgResolveResult,
} from "@/lib/api";

/**
 * Admin → Bot config (Milestone 2).
 *
 * Per-channel CRUD with strategy parameters:
 *   - Identity:       channel_id, title, username, image_url
 *   - Parsing:        parser_key, notes
 *   - Strategy:       order_position_type, tp_strategy
 *   - Flags:          is_enabled, is_tradeable, is_trusted
 *
 * The "Resolve" button pre-fills the form by asking the listener service
 * to look up @username or numeric id and return the canonical title +
 * numeric id. Admin never has to know Telegram's -100... prefix manually.
 */
export default function AdminBotPage() {
  const { data: channels, mutate, isLoading } = useSWR(
    "admin:bot:channels", api.tgChannels,
  );
  const [editing, setEditing] = useState<TgChannelRow | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Bot className="size-4" /> Bot configuration
          </h2>
          <p className="text-ink-muted text-xs mt-1">
            Per-channel strategy parameters. The listener picks up changes
            within 60 seconds — no restart needed.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => mutate()} className="btn-ghost text-xs">
            <RefreshCw className="size-3.5" /> Refresh
          </button>
          <button onClick={() => { setEditing(null); setShowAdd(true); }}
                  className="btn-primary text-xs">
            <Plus className="size-3.5" /> Add channel
          </button>
        </div>
      </header>

      {showAdd && (
        <ChannelForm
          initial={null}
          onCancel={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); mutate(); }}
        />
      )}
      {editing && (
        <ChannelForm
          initial={editing}
          onCancel={() => setEditing(null)}
          onSaved={() => { setEditing(null); mutate(); }}
        />
      )}

      <section className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-ink-muted bg-bg-subtle">
              <tr>
                <th className="text-left p-3">Channel</th>
                <th className="text-left p-3">Parser</th>
                <th className="text-left p-3">Strategy</th>
                <th className="text-left p-3">Flags</th>
                <th className="text-left p-3 hidden md:table-cell">Last msg</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={6} className="p-6 text-center text-ink-muted">
                  <Loader2 className="size-4 inline-block animate-spin" /> Loading…
                </td></tr>
              )}
              {!isLoading && (!channels || channels.length === 0) && (
                <tr><td colSpan={6} className="p-6 text-center text-ink-muted text-sm">
                  No channels yet. Click "Add channel" to set one up.
                </td></tr>
              )}
              {channels?.map(c => (
                <ChannelRow key={c.id} c={c}
                            onEdit={() => { setShowAdd(false); setEditing(c); }}
                            onChange={() => mutate()} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------
function ChannelRow({ c, onEdit, onChange }: {
  c: TgChannelRow;
  onEdit: () => void;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function toggle(field: "is_enabled" | "is_tradeable" | "is_trusted") {
    setBusy(true);
    try {
      await api.updateTgChannel(c.id, { [field]: !c[field] });
      onChange();
    } finally {
      setBusy(false);
    }
  }
  async function del() {
    if (!confirm(`Delete channel "${c.channel_title}"? Past signals stay.`)) return;
    setBusy(true);
    try { await api.deleteTgChannel(c.id); onChange(); }
    finally { setBusy(false); }
  }

  return (
    <tr className="border-t border-border align-top">
      <td className="p-3">
        <div className="flex items-center gap-2">
          {c.image_url && (
            <img src={c.image_url} alt="" className="size-7 rounded object-cover" />
          )}
          <div className="min-w-0">
            <div className="font-medium truncate">{c.channel_title}</div>
            <div className="text-[11px] text-ink-muted font-mono">
              {c.channel_username ? `@${c.channel_username} · ` : ""}{c.channel_id}
            </div>
          </div>
        </div>
      </td>
      <td className="p-3 text-xs uppercase tracking-wide text-ink-muted">
        {c.parser_key}
      </td>
      <td className="p-3 text-xs">
        <div><span className="text-ink-muted">Type:</span> {c.order_position_type}</div>
        <div className="text-ink-muted truncate max-w-[220px]">
          TP: <span className="text-ink font-mono">{c.tp_strategy}</span>
        </div>
      </td>
      <td className="p-3">
        <div className="space-y-1">
          <FlagToggle label="Listening" value={c.is_enabled}  busy={busy}
                      onClick={() => toggle("is_enabled")} />
          <FlagToggle label="Tradeable" value={c.is_tradeable} busy={busy}
                      onClick={() => toggle("is_tradeable")} />
          <FlagToggle label="Trusted"   value={c.is_trusted}   busy={busy}
                      onClick={() => toggle("is_trusted")} />
        </div>
      </td>
      <td className="p-3 hidden md:table-cell text-xs text-ink-muted">
        {c.last_message_at
          ? new Date(c.last_message_at).toLocaleString()
          : <span className="text-ink-dim">never</span>}
      </td>
      <td className="p-3 text-right whitespace-nowrap">
        <button onClick={onEdit} className="btn-ghost text-xs" disabled={busy}>
          <Pencil className="size-3.5" />
        </button>
        <button onClick={del} className="text-rose-500 hover:opacity-80 ml-2" disabled={busy}>
          <Trash2 className="size-3.5" />
        </button>
      </td>
    </tr>
  );
}


function FlagToggle({ label, value, busy, onClick }: {
  label: string; value: boolean; busy: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick} disabled={busy}
            className="flex items-center gap-1 text-xs hover:text-ink">
      {value
        ? <ToggleRight className="size-3.5 text-emerald-500" />
        : <ToggleLeft className="size-3.5 text-ink-muted" />}
      <span className={value ? "text-ink" : "text-ink-muted"}>{label}</span>
    </button>
  );
}


// ---------------------------------------------------------------------------
// Add / edit form
// ---------------------------------------------------------------------------
const ORDER_TYPES = ["MARKET", "LIMIT", "STOP"] as const;
const PARSER_KEYS = ["gold_xau"] as const;   // Extend as new parsers ship

function ChannelForm({ initial, onCancel, onSaved }: {
  initial: TgChannelRow | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const isEdit = initial !== null;
  const [form, setForm] = useState<TgChannelInput>(() => initial ? {
    channel_id: initial.channel_id,
    channel_title: initial.channel_title,
    channel_username: initial.channel_username,
    parser_key: initial.parser_key,
    is_enabled: initial.is_enabled,
    notes: initial.notes,
    order_position_type: initial.order_position_type,
    tp_strategy: initial.tp_strategy,
    is_tradeable: initial.is_tradeable,
    is_trusted: initial.is_trusted,
    image_url: initial.image_url,
  } : {
    channel_id: 0, channel_title: "",
    parser_key: "gold_xau",
    is_enabled: true, is_tradeable: true, is_trusted: true,
    order_position_type: "MARKET",
    tp_strategy: "tp1",
  });

  const [resolveQuery, setResolveQuery] = useState("");
  const [resolveBusy, setResolveBusy] = useState(false);
  const [resolveResult, setResolveResult] = useState<TgResolveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function set<K extends keyof TgChannelInput>(k: K, v: TgChannelInput[K]) {
    setForm(prev => ({ ...prev, [k]: v }));
  }

  async function resolve() {
    if (!resolveQuery.trim()) return;
    setResolveBusy(true); setError(null); setResolveResult(null);
    try {
      const r = await api.resolveTgChannel(resolveQuery.trim());
      setResolveResult(r);
      // Pre-fill form
      set("channel_id", r.channel_id);
      set("channel_title", r.title);
      set("channel_username", r.username);
    } catch (e: any) {
      setError(`Resolve failed: ${e.message}`);
    } finally {
      setResolveBusy(false);
    }
  }

  async function save() {
    setError(null);
    if (!form.channel_id || !form.channel_title) {
      setError("channel_id and channel_title are required");
      return;
    }
    setSaving(true);
    try {
      if (isEdit && initial) {
        // channel_id is immutable — strip it from PATCH to keep the API simple
        const { channel_id, ...rest } = form;
        await api.updateTgChannel(initial.id, rest);
      } else {
        await api.createTgChannel(form);
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {isEdit ? `Edit · ${initial?.channel_title}` : "Add channel"}
        </h3>
      </div>

      {!isEdit && (
        <div className="space-y-2 p-3 border border-border rounded bg-bg-subtle/30">
          <div className="text-xs text-ink-muted">
            Resolve a channel by <code>@username</code> or numeric id.
            The listener looks it up via your Telegram account.
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={resolveQuery}
              onChange={e => setResolveQuery(e.target.value)}
              placeholder="@channelname or -1001234567890"
              className="input flex-1 text-sm"
              onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); resolve(); } }}
            />
            <button onClick={resolve} disabled={resolveBusy || !resolveQuery.trim()}
                    className="btn-ghost text-xs">
              {resolveBusy
                ? <Loader2 className="size-3.5 animate-spin" />
                : <Search className="size-3.5" />}
              Resolve
            </button>
          </div>
          {resolveResult && (
            <div className="text-xs text-emerald-500 flex items-center gap-1">
              <CheckCircle2 className="size-3.5" />
              Found {resolveResult.kind}: {resolveResult.title}
              {resolveResult.username && <span className="text-ink-muted ml-1">
                (@{resolveResult.username})
              </span>}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Field label="Channel ID" required>
          <input type="number"
                 value={form.channel_id || ""}
                 onChange={e => set("channel_id", Number(e.target.value))}
                 className="input w-full" disabled={isEdit}
                 placeholder="-1001234567890" />
        </Field>
        <Field label="Title" required>
          <input type="text" value={form.channel_title}
                 onChange={e => set("channel_title", e.target.value)}
                 className="input w-full" placeholder="GoldGA" />
        </Field>
        <Field label="Username (without @)">
          <input type="text" value={form.channel_username ?? ""}
                 onChange={e => set("channel_username", e.target.value || null)}
                 className="input w-full" placeholder="goldga_signals" />
        </Field>
        <Field label="Image URL">
          <input type="text" value={form.image_url ?? ""}
                 onChange={e => set("image_url", e.target.value || null)}
                 className="input w-full" placeholder="https://..." />
        </Field>

        <Field label="Parser">
          <select value={form.parser_key ?? "gold_xau"}
                  onChange={e => set("parser_key", e.target.value)}
                  className="input w-full">
            {PARSER_KEYS.map(k => <option key={k} value={k}>{k}</option>)}
          </select>
        </Field>
        <Field label="Order type">
          <select value={form.order_position_type ?? "MARKET"}
                  onChange={e => set("order_position_type",
                    e.target.value as TgChannelInput["order_position_type"])}
                  className="input w-full">
            {ORDER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>

        <Field label="TP strategy"
               help={"Comma-separated TP allocations, e.g. 'tp1, tp1, tp2, tp3' — " +
                     "one slice per token, each closes at that TP level."}>
          <input type="text" value={form.tp_strategy ?? "tp1"}
                 onChange={e => set("tp_strategy", e.target.value)}
                 className="input w-full font-mono"
                 placeholder="tp1, tp1, tp2, tp3" />
        </Field>
        <Field label="Notes">
          <input type="text" value={form.notes ?? ""}
                 onChange={e => set("notes", e.target.value || null)}
                 className="input w-full" />
        </Field>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <CheckboxField label="Listening" value={form.is_enabled ?? true}
                       help="Listener subscribes to messages."
                       onChange={v => set("is_enabled", v)} />
        <CheckboxField label="Tradeable" value={form.is_tradeable ?? true}
                       help="Future: signals from this channel can place trades."
                       onChange={v => set("is_tradeable", v)} />
        <CheckboxField label="Trusted" value={form.is_trusted ?? true}
                       help="Metadata flag. Used by confidence scoring later."
                       onChange={v => set("is_trusted", v)} />
      </div>

      {error && (
        <div className="text-xs text-rose-500 flex items-center gap-1">
          <AlertCircle className="size-3.5" /> {error}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button onClick={save} disabled={saving} className="btn-primary text-xs">
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <CheckCircle2 className="size-3.5" />}
          {isEdit ? "Save changes" : "Add channel"}
        </button>
        <button onClick={onCancel} disabled={saving} className="btn-ghost text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}


function Field({ label, required, help, children }: {
  label: string; required?: boolean; help?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-xs">
      <span className="text-ink-muted">
        {label}{required && <span className="text-rose-500"> *</span>}
      </span>
      <div className="mt-1">{children}</div>
      {help && <span className="text-[11px] text-ink-dim block mt-0.5">{help}</span>}
    </label>
  );
}


function CheckboxField({ label, value, help, onChange }: {
  label: string; value: boolean; help?: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 text-xs cursor-pointer">
      <input type="checkbox" checked={value}
             onChange={e => onChange(e.target.checked)}
             className="mt-0.5" />
      <div>
        <div className="text-ink">{label}</div>
        {help && <div className="text-[11px] text-ink-dim mt-0.5">{help}</div>}
      </div>
    </label>
  );
}
