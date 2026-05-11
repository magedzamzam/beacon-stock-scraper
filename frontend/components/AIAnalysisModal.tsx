"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { api, type AIAnalysisRequest, type AIAnalysisResponse, type AIAnalysisResultItem, type AIProviderSetting, type AIPromptTemplate, type Position, type StockDetail } from "@/lib/api";
import { fmtMoney, fmtPercent, fmtPrice } from "@/lib/utils";
import { AlertCircle, BadgeCheck, Brain, CheckCircle2, Clock3, Loader2, Sparkles, X } from "lucide-react";

const DEFAULT_PROMPT_BY_SCOPE: Record<"stock" | "portfolio", string> = {
  stock: "stock_brief",
  portfolio: "portfolio_brief",
};

export default function AIAnalysisModal({
  open,
  onClose,
  scope,
  stock,
  accountId,
  positions,
}: {
  open: boolean;
  onClose: () => void;
  scope: "stock" | "portfolio";
  stock?: StockDetail | null;
  accountId?: number | null;
  positions?: Position[];
}) {
  const { data: providers } = useSWR(open ? "ai:providers" : null, api.listAIProviders);
  const { data: prompts } = useSWR(open ? "ai:prompts" : null, api.listAIPrompts);
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [promptKey, setPromptKey] = useState<string>(DEFAULT_PROMPT_BY_SCOPE[scope]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AIAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabledProviders = useMemo(
    () => (providers || []).filter((p) => p.enabled && (p.api_key_set ?? (p as any).api_key_present)),
    [providers],
  );

  useEffect(() => {
    if (!open) return;
    setPromptKey(DEFAULT_PROMPT_BY_SCOPE[scope]);
    setResult(null);
    setError(null);
  }, [open, scope]);

  useEffect(() => {
    if (open && enabledProviders.length > 0 && selectedProviders.length === 0) {
      setSelectedProviders(enabledProviders.map((p) => p.provider_key));
    }
  }, [open, enabledProviders, selectedProviders.length]);

  if (!open) return null;

  async function submit() {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const body: AIAnalysisRequest = {
        provider_keys: selectedProviders,
        prompt_key: promptKey,
        account_id: accountId ?? undefined,
      };
      const response = scope === "stock"
        ? await api.analyzeStockAI(stock?.exchange_code || "", stock?.ticker || "", body)
        : await api.analyzePortfolioAI(body);
      setResult(response);
    } catch (e: any) {
      setError(e.message || "Analysis failed");
    } finally {
      setSubmitting(false);
    }
  }

  const scopeLabel = scope === "stock"
    ? `${stock?.ticker || "Stock"} · ${stock?.company_name || ""}`
    : accountId
      ? `Account ${accountId}`
      : "All positions";

  const promptOptions = (prompts || []).filter((p) => p.scope === scope);
  const currentPrompt = promptOptions.find((p) => p.template_key === promptKey) || promptOptions[0];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card w-full max-w-4xl max-h-[90vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-dim">
              <Sparkles className="size-3.5" /> AI analysis
            </div>
            <h3 className="text-xl font-semibold mt-1">{scope === "stock" ? "Analyze stock" : "Analyze portfolio"}</h3>
            <p className="text-sm text-ink-muted mt-1">{scopeLabel}</p>
          </div>
          <button className="btn-ghost" onClick={onClose}><X className="size-4" /></button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[320px,1fr] gap-4 mt-5">
          <div className="space-y-4">
            <div className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border">
              <div className="flex items-center gap-2 mb-3 text-sm font-semibold"><Brain className="size-4" /> Providers</div>
              {!enabledProviders.length && (
                <div className="text-xs text-ink-muted">No enabled providers found. Enable and save at least one key in Profile first.</div>
              )}
              <div className="space-y-2">
                {enabledProviders.map((p) => {
                  const active = selectedProviders.includes(p.provider_key);
                  return (
                    <button
                      key={p.provider_key}
                      type="button"
                      onClick={() => setSelectedProviders((prev) => prev.includes(p.provider_key)
                        ? prev.filter((k) => k !== p.provider_key)
                        : [...prev, p.provider_key])}
                      className={`w-full rounded-xl px-3 py-2 text-left ring-1 transition-colors ${active
                        ? "bg-brand/10 ring-brand/40"
                        : "bg-bg-elevated ring-border hover:bg-bg-elevated/80"}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <div className="text-sm font-medium">{p.display_name || p.provider_name || p.provider_key}</div>
                          <div className="text-[11px] text-ink-dim font-mono">{p.model_name || p.provider_key || "model"}</div>
                        </div>
                        <CheckCircle2 className={`size-4 ${active ? "text-verdict-buy" : "text-ink-dim"}`} />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border">
              <div className="flex items-center gap-2 mb-3 text-sm font-semibold"><BadgeCheck className="size-4" /> Prompt</div>
              <select className="input" value={promptKey} onChange={(e) => setPromptKey(e.target.value)}>
                {promptOptions.length === 0 && <option value={promptKey}>{DEFAULT_PROMPT_BY_SCOPE[scope]}</option>}
                {promptOptions.map((prompt) => <option key={prompt.template_key} value={prompt.template_key}>{prompt.name}</option>)}
              </select>
              <div className="text-[11px] text-ink-dim mt-2">
                {currentPrompt?.description || "Compact prompt"}
                {currentPrompt && <span className="block mt-1 font-mono">max {currentPrompt.token_budget ?? 0} tokens</span>}
              </div>
            </div>

            {scope === "stock" && stock && (
              <div className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border text-sm">
                <div className="font-semibold">{stock.ticker}</div>
                <div className="text-xs text-ink-muted">{stock.company_name}</div>
                <div className="mt-2 text-sm font-mono">
                  {fmtPrice(stock.current_price ?? stock.last_close, stock.currency)}
                  <span className={`ml-2 ${((stock.change_pct ?? stock.last_change_pct ?? 0) < 0) ? "text-verdict-avoid" : "text-verdict-buy"}`}>
                    {fmtPercent(stock.change_pct ?? stock.last_change_pct)}
                  </span>
                </div>
              </div>
            )}

            {scope === "portfolio" && positions && (
              <div className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border text-sm">
                <div className="font-semibold">{positions.length} positions</div>
                <div className="text-xs text-ink-muted mt-1">
                  Use the current holdings and entry prices to decide HOLD / BUY MORE / SELL.
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-end gap-2">
              <button className="btn-primary" onClick={submit} disabled={submitting || selectedProviders.length === 0 || (scope === "stock" && !stock)}>
                {submitting ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                {submitting ? "Analyzing…" : "Run analysis"}
              </button>
            </div>

            {error && (
              <div className="rounded-xl bg-verdict-avoid/10 text-verdict-avoid ring-1 ring-verdict-avoid/25 p-3 text-sm flex items-start gap-2">
                <AlertCircle className="size-4 mt-0.5" />
                <div>{error}</div>
              </div>
            )}

            {result && (
              <div className="space-y-3">
                {result.results.map((r: AIAnalysisResultItem) => (
                  <div key={r.provider_key} className="rounded-2xl bg-bg-subtle p-4 ring-1 ring-border">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold">{r.provider_name || r.provider_key}</div>
                        <div className="text-xs text-ink-dim font-mono">{r.model_name || r.provider_key}</div>
                      </div>
                      <div className="text-xs text-ink-muted flex items-center gap-2">
                        {r.latency_ms != null && <span className="flex items-center gap-1"><Clock3 className="size-3.5" /> {r.latency_ms} ms</span>}
                        {r.ok ? <span className="text-verdict-buy">OK</span> : <span className="text-verdict-avoid">FAIL</span>}
                      </div>
                    </div>

                    {!r.ok && r.error && <div className="text-sm text-verdict-avoid mt-2">{r.error}</div>}

                    {r.ok && r.analysis && (
                      <AnalysisView analysis={r.analysis} scope={scope} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AnalysisView({ analysis, scope }: { analysis: Record<string, any>; scope: "stock" | "portfolio" }) {
  const decision = scope === "stock" ? analysis.decision : analysis.portfolio_view;
  const summary = analysis.summary || analysis.one_liner || "";
  const confidence = analysis.confidence;
  const thesis = analysis.thesis || analysis.rationale || [];
  const risks = analysis.risks || [];
  const actions = analysis.actions || (analysis.action ? [analysis.action] : []);
  const positions = analysis.positions || [];

  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {decision && <span className="badge bg-brand/10 text-brand">{String(decision)}</span>}
        {confidence != null && <span className="badge bg-bg-elevated text-ink-muted">{confidence}% confidence</span>}
      </div>
      {summary && <div className="text-sm text-ink">{summary}</div>}

      {thesis?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-1">Thesis</div>
          <ul className="space-y-1 text-sm">
            {thesis.slice(0, 4).map((item: any, idx: number) => <li key={idx}>• {String(item)}</li>)}
          </ul>
        </div>
      )}

      {risks?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-1">Risks</div>
          <ul className="space-y-1 text-sm text-verdict-avoid">
            {risks.slice(0, 4).map((item: any, idx: number) => <li key={idx}>• {String(item)}</li>)}
          </ul>
        </div>
      )}

      {actions?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-1">Action</div>
          <ul className="space-y-1 text-sm">
            {actions.slice(0, 4).map((item: any, idx: number) => <li key={idx}>• {String(item)}</li>)}
          </ul>
        </div>
      )}

      {positions?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-dim mb-1">Positions</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {positions.map((pos: any, idx: number) => (
              <div key={idx} className="rounded-xl bg-bg-elevated p-3 ring-1 ring-border text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{pos.ticker}</div>
                  <span className="badge bg-bg-subtle text-ink-muted text-[10px]">{pos.decision}</span>
                </div>
                <div className="text-xs text-ink-dim mt-1">{pos.reason}</div>
                {pos.confidence != null && <div className="text-[11px] text-ink-muted mt-1">{pos.confidence}% confidence</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
