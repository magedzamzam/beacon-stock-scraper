"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { api, type AIProviderSetting, type AIPromptTemplate, type AIProviderUpsert } from "@/lib/api";
import { Check, Eye, EyeOff, KeyRound, PencilLine, Power, Save, Sparkles } from "lucide-react";

const PROVIDER_ORDER = ["openai", "gemini", "anthropic", "xai"] as const;

export default function AISettingsPanel() {
  const { data: providers, isLoading: providersLoading } = useSWR("ai:providers", api.listAIProviders);
  const { data: prompts, isLoading: promptsLoading } = useSWR("ai:prompts", api.listAIPrompts);

  const sortedProviders = useMemo(() => {
    if (!providers) return [];
    const map = new Map(providers.map((p) => [p.provider_key, p]));
    return PROVIDER_ORDER.map((k) => map.get(k)).filter(Boolean) as AIProviderSetting[];
  }, [providers]);

  return (
    <section className="card p-5 mt-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2"><Sparkles className="size-4" /> AI models</h2>
          <p className="text-xs text-ink-muted">
            Store one key per provider, toggle models on or off, and keep prompts compact so requests stay cheap.
          </p>
        </div>
      </div>

      {providersLoading && <div className="text-sm text-ink-muted py-4">Loading AI providers…</div>}
      {!providersLoading && sortedProviders.length === 0 && (
        <div className="text-sm text-ink-muted py-4">No providers yet.</div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {sortedProviders.map((provider) => (
          <ProviderCard key={provider.provider_key} provider={provider} />
        ))}
      </div>

      <div className="mt-5 border-t border-border pt-4">
        <div className="flex items-center gap-2 mb-2 text-sm font-semibold">
          <PencilLine className="size-4" /> Prompt presets
        </div>
        {promptsLoading && <div className="text-sm text-ink-muted py-2">Loading prompts…</div>}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {(prompts || []).map((prompt) => (
            <div key={prompt.key} className="rounded-xl bg-bg-subtle p-3 ring-1 ring-border">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-sm">{prompt.label}</div>
                <span className="badge bg-bg-elevated text-ink-muted text-[10px] uppercase">{prompt.scope}</span>
              </div>
              <p className="text-xs text-ink-muted mt-1">{prompt.description}</p>
              <div className="text-[11px] text-ink-dim mt-2 font-mono">max {prompt.max_output_tokens} tokens</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProviderCard({ provider }: { provider: AIProviderSetting }) {
  const [enabled, setEnabled] = useState(provider.enabled);
  const [modelName, setModelName] = useState(provider.model_name || "");
  const [baseUrl, setBaseUrl] = useState(provider.base_url || "");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(provider.updated_at);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEnabled(provider.enabled);
    setModelName(provider.model_name || "");
    setBaseUrl(provider.base_url || "");
    setSavedAt(provider.updated_at);
  }, [provider.enabled, provider.model_name, provider.base_url, provider.updated_at]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body: AIProviderUpsert = {
        enabled,
        api_key: apiKey.trim() ? apiKey.trim() : undefined,
        model_name: modelName.trim() || undefined,
        base_url: baseUrl.trim() || undefined,
      };
      const updated = await api.saveAIProvider(provider.provider_key, body);
      mutate("ai:providers");
      setApiKey("");
      setSavedAt(updated.updated_at);
    } catch (e: any) {
      setError(e.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{provider.provider_name}</h3>
            {provider.enabled ? (
              <span className="badge bg-verdict-buy/15 text-verdict-buy text-[10px]">enabled</span>
            ) : (
              <span className="badge bg-bg-elevated text-ink-muted text-[10px]">disabled</span>
            )}
          </div>
          <div className="text-[11px] text-ink-dim mt-1">
            {provider.api_key_present ? "API key saved" : "No API key saved yet"}
            {savedAt && <span> · updated {new Date(savedAt).toLocaleString()}</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setEnabled((v) => !v)}
          className={`btn-ghost text-xs ${enabled ? "text-verdict-buy" : ""}`}
        >
          <Power className="size-3.5" /> {enabled ? "On" : "Off"}
        </button>
      </div>

      <div className="space-y-3 mt-4">
        <div>
          <label className="label">Model</label>
          <input className="input mt-1" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder={provider.model_name || "model name"} />
        </div>
        <div>
          <label className="label">API key</label>
          <div className="mt-1 flex gap-2">
            <div className="relative flex-1">
              <input
                className="input pr-10"
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={provider.api_key_present ? "leave blank to keep current key" : "paste key here"}
              />
              <KeyRound className="absolute right-3 top-1/2 -translate-y-1/2 size-4 text-ink-dim" />
            </div>
            <button className="btn-ghost" onClick={() => setShowKey((v) => !v)} type="button">
              {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        <div>
          <label className="label">Base URL (optional)</label>
          <input className="input mt-1" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={provider.base_url || "provider endpoint"} />
        </div>
        {error && <div className="text-xs text-verdict-avoid">{error}</div>}
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="text-[11px] text-ink-dim">Save keeps existing API key when left blank.</div>
        <button className="btn-primary text-sm" onClick={save} disabled={saving}>
          <Save className="size-4" /> {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
