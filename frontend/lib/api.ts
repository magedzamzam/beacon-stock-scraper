// Typed API client for Beacon Screener backend.
// Uses Next.js rewrites in dev (/api -> http://localhost:8000) and nginx in prod.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("beacon_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem("beacon_token", token);
  else window.localStorage.removeItem("beacon_token");
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  withAuth = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (withAuth) {
    const tok = getToken();
    if (tok) headers.set("Authorization", `Bearer ${tok}`);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (res.status === 401 && withAuth) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------------- Types ----------------
export type Verdict = "BUY" | "WATCH" | "STAY_AWAY";
export type PositionVerdict = "HOLD" | "SELL" | "BUY_MORE" | "TRIM" | "STOP_LOSS";

export interface StockSummary {
  id: number;
  ticker: string;
  exchange_code: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string | null;
  last_close: number | null;
  last_change_pct: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  dividend_yield_pct: number | null;
  rsi_14: number | null;
  composite_score: number | null;
  verdict: Verdict | null;
  last_updated: string | null;
}

export interface ScoreBreakdown {
  ticker: string;
  exchange_code: string;
  score_date: string;
  fundamental_score: number;
  valuation_score: number;
  momentum_score: number;
  technical_score: number;
  analyst_score: number;
  quality_score: number;
  risk_score: number;
  composite_score: number;
  verdict: Verdict;
  pros: string[];
  cons: string[];
  model_version: string;
}

export interface EarningsBlock {
  last_earnings_date: string | null;
  next_earnings_date: string | null;
  earnings_time: string | null;
  est_revenue: number | null;
  est_revenue_growth_pct: number | null;
  est_eps: number | null;
  days_to_next: number | null;
  days_since_last: number | null;
  data_imported_at: string | null;
}

export interface ShareStructureBlock {
  shares_change_yoy_pct: number | null;
  shares_change_qoq_pct: number | null;
  insiders_pct: number | null;
  institutional_pct: number | null;
  retail_pct: number | null;
  period_end: string | null;
}

export interface StockDetail extends StockSummary {
  isin: string | null;
  founded_year: number | null;
  employees: number | null;
  website: string | null;
  beta: number | null;
  forward_pe: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  enterprise_value: number | null;
  revenue_ttm: number | null;
  sma_50: number | null;
  sma_200: number | null;
  analyst_target: number | null;
  analyst_upside_pct: number | null;
  analyst_count: number | null;
  analyst_rating: string | null;
  // Unified price (single source of truth)
  current_price: number | null;
  prev_close: number | null;
  change_abs: number | null;
  change_pct: number | null;
  price_source: "broker" | "scrape" | null;
  price_fetched_at: string | null;
  // Earnings + share structure (from bulk CSV import). Either can be null.
  earnings: EarningsBlock | null;
  share_structure: ShareStructureBlock | null;
}

export interface PriceHistoryPoint {
  trading_date: string;
  close: number | null;
  volume: number | null;
}

export interface NewsItem {
  id: number;
  news_date: string | null;
  headline: string;
  source_code: string | null;
  url: string | null;
  sentiment_label: string | null;
  sentiment_score: number | null;
  summary: string | null;
}

export interface FilterOptions {
  exchanges: { code: string; name: string }[];
  sectors: string[];
  industries: string[];
  verdicts: Verdict[];
}

export interface ScreenerParams {
  q?: string;
  exchange?: string;
  sector?: string;
  industry?: string;
  verdict?: Verdict;
  min_score?: number;
  max_pe?: number;
  min_dividend?: number;
  // Earnings calendar window. Each can be set independently.
  //   earnings_within_days_future=3 → companies with next earnings in next 3 days
  //   earnings_within_days_past=2   → companies that reported in last 2 days
  // Setting both OR-s them.
  earnings_within_days_future?: number;
  earnings_within_days_past?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface WatchlistItem {
  id: number;
  stock: StockSummary;
  note: string | null;
  added_at: string;
}

export interface Watchlist {
  id: number;
  name: string;
  created_at: string;
  items: WatchlistItem[];
}

export interface Position {
  id: number;
  stock: StockSummary;
  quantity: number;
  avg_entry_price: number;
  entry_date: string | null;
  notes: string | null;
  market_value: number | null;
  cost_basis: number;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  position_verdict: PositionVerdict | null;
  position_confidence: number | null;
  position_reasoning: string[] | null;
}

export interface Portfolio {
  positions: Position[];
  total_cost: number;
  total_value: number;
  total_pl: number;
  total_pl_pct: number;
}

export interface User {
  id: number;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface AIProviderSetting {
  provider_key: string;
  provider_name: string;
  enabled: boolean;
  api_key_present: boolean;
  model_name: string | null;
  base_url: string | null;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_test_error: string | null;
  updated_at: string | null;
}

export interface AIPromptTemplate {
  key: string;
  label: string;
  scope: "stock" | "portfolio";
  description: string | null;
  system_prompt: string;
  max_output_tokens: number;
  updated_at: string | null;
}

export interface AIAnalysisResult {
  provider_key: string;
  provider_name: string;
  model_name: string;
  ok: boolean;
  error: string | null;
  latency_ms: number | null;
  analysis: Record<string, any> | null;
}

export interface AIAnalysisResponse {
  scope: "stock" | "portfolio";
  prompt_key: string;
  context: Record<string, any>;
  results: AIAnalysisResult[];
}

export interface AIProviderUpsert {
  enabled: boolean;
  api_key?: string | null;
  model_name?: string | null;
  base_url?: string | null;
}

// ---------------- Endpoints ----------------
export const api = {
  // auth
  register: (email: string, password: string, display_name?: string) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name }) }, false),
  login: async (email: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    return request<AuthResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    }, false);
  },
  me: () => request<User>("/auth/me"),

  // stocks
  screener: (p: ScreenerParams = {}) => {
    const qs = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== "") qs.set(k, String(v)); });
    return request<{ total: number; items: StockSummary[] }>(`/stocks?${qs.toString()}`);
  },
  filters: () => request<FilterOptions>("/stocks/filters"),
  stockDetail: (exchange: string, ticker: string) =>
    request<StockDetail>(`/stocks/${exchange}/${ticker}`),
  stockScore: (exchange: string, ticker: string) =>
    request<ScoreBreakdown>(`/stocks/${exchange}/${ticker}/score`),
  priceHistory: (exchange: string, ticker: string, days = 180) =>
    request<PriceHistoryPoint[]>(`/stocks/${exchange}/${ticker}/price-history?days=${days}`),
  stockNews: (exchange: string, ticker: string, limit = 20) =>
    request<NewsItem[]>(`/stocks/${exchange}/${ticker}/news?limit=${limit}`),
  refreshStock: (exchange: string, ticker: string) =>
    request<{ status: string }>(`/stocks/${exchange}/${ticker}/refresh`, { method: "POST" }),

  analyzeStock: (exchange: string, ticker: string, body: { provider_keys?: string[]; prompt_key?: string; account_id?: number | null }) =>
    request<AIAnalysisResponse>(`/ai/analyze/stock/${exchange}/${ticker}`, { method: "POST", body: JSON.stringify(body) }),
  analyzePortfolio: (body: { provider_keys?: string[]; prompt_key?: string; account_id?: number | null }) =>
    request<AIAnalysisResponse>(`/ai/analyze/portfolio`, { method: "POST", body: JSON.stringify(body) }),
  listAIProviders: () => request<AIProviderSetting[]>(`/ai/providers`),
  saveAIProvider: (provider_key: string, body: AIProviderUpsert) =>
    request<AIProviderSetting>(`/ai/providers/${encodeURIComponent(provider_key)}`, { method: "PUT", body: JSON.stringify(body) }),
  listAIPrompts: () => request<AIPromptTemplate[]>(`/ai/prompts`),

  // watchlists
  listWatchlists: () => request<Watchlist[]>("/watchlists"),
  createWatchlist: (name: string) =>
    request<Watchlist>("/watchlists", { method: "POST", body: JSON.stringify({ name }) }),
  deleteWatchlist: (id: number) =>
    request<void>(`/watchlists/${id}`, { method: "DELETE" }),
  addWatchlistItem: (watchlistId: number, stock_id: number, note?: string) =>
    request<WatchlistItem>(`/watchlists/${watchlistId}/items`, {
      method: "POST", body: JSON.stringify({ stock_id, note }),
    }),
  removeWatchlistItem: (watchlistId: number, itemId: number) =>
    request<void>(`/watchlists/${watchlistId}/items/${itemId}`, { method: "DELETE" }),

  // portfolio
  portfolio: () => request<Portfolio>("/portfolio"),
  addPosition: (
    stock_id: number,
    quantity: number,
    avg_entry_price: number,
    entry_date?: string,
    notes?: string,
    account_id?: number,
  ) =>
    request<Position>("/portfolio", {
      method: "POST",
      body: JSON.stringify({ stock_id, quantity, avg_entry_price, entry_date, notes, account_id }),
    }),
  closePosition: (id: number) =>
    request<void>(`/portfolio/${id}`, { method: "DELETE" }),

  // admin
  adminStatus: () => request<any>("/admin/status"),
  adminScrapeAll: () => request<any>("/admin/scrape-all", { method: "POST" }),
  adminScoreAll: () => request<any>("/admin/score-all", { method: "POST" }),
  adminScorePortfolio: () => request<any>("/admin/score-portfolio", { method: "POST" }),
  adminScoreSentiment: () => request<any>("/admin/score-sentiment", { method: "POST" }),
  adminOverrideStock: (
    exchange: string,
    ticker: string,
    payload: {
      last_close?: number;
      currency?: string;
      analyst_target?: number;
      analyst_count?: number;
      analyst_rating?: string;
    },
  ) =>
    request<{ ticker: string; exchange: string; changes: Record<string, any>; rescored: any }>(
      `/admin/stocks/${exchange}/${ticker}/override`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // csv import
  adminImportCatalog: () => request<ImportCatalog>("/admin/imports/catalog"),
  adminImportPreview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportPreview>("/admin/imports/preview", { method: "POST", body: form });
  },
  adminImportExecute: (payload: ImportExecuteRequest) =>
    request<ImportExecuteResult>("/admin/imports/execute", { method: "POST", body: JSON.stringify(payload) }),

  // bulk csv import (stockanalysis.com exchange exports)
  adminBulkImportPreview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<BulkImportPreview>("/admin/imports/bulk/preview", { method: "POST", body: form });
  },
  adminBulkImportExecute: (file: File, exchangeId: number) => {
    const form = new FormData();
    form.append("file", file);
    form.append("exchange_id", String(exchangeId));
    return request<BulkImportResult>("/admin/imports/bulk/execute", { method: "POST", body: form });
  },
  adminBulkImportHistory: (limit = 25) =>
    request<BulkImportHistoryEntry[]>(`/admin/imports/bulk/history?limit=${limit}`),

  // ===== Alerts =====
  alertsMeta: () => request<AlertsMeta>("/admin/alerts/meta"),
  alertChannels: () => request<AlertChannelRow[]>("/admin/alerts/channels"),
  createAlertChannel: (body: AlertChannelInput) =>
    request<AlertChannelRow>("/admin/alerts/channels", {
      method: "POST", body: JSON.stringify(body),
    }),
  updateAlertChannel: (id: number, body: Partial<AlertChannelInput>) =>
    request<AlertChannelRow>(`/admin/alerts/channels/${id}`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  deleteAlertChannel: (id: number) =>
    request<{ deleted: number }>(`/admin/alerts/channels/${id}`, { method: "DELETE" }),
  alertRules: () => request<AlertRuleRow[]>("/admin/alerts/rules"),
  createAlertRule: (body: AlertRuleInput) =>
    request<AlertRuleRow>("/admin/alerts/rules", {
      method: "POST", body: JSON.stringify(body),
    }),
  updateAlertRule: (id: number, body: Partial<AlertRuleInput>) =>
    request<AlertRuleRow>(`/admin/alerts/rules/${id}`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  deleteAlertRule: (id: number) =>
    request<{ deleted: number }>(`/admin/alerts/rules/${id}`, { method: "DELETE" }),
  testFireAlertRule: (id: number) =>
    request<{ delivery: Record<string, { status: string; error: string | null }> }>(
      `/admin/alerts/rules/${id}/test-fire`, { method: "POST" },
    ),
  evaluateAlertsNow: () =>
    request<AlertsEvaluateSummary>("/admin/alerts/evaluate-now", { method: "POST" }),
  alertEvents: (limit = 50, ruleId?: number) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (ruleId != null) qs.set("rule_id", String(ruleId));
    return request<AlertEventRow[]>(`/admin/alerts/events?${qs.toString()}`);
  },

  // ===== Trading Bot =====
  tgSignals: (limit = 50) =>
    request<TgSignalRow[]>(`/trading-bot/signals?limit=${limit}`),
  tgRawMessages: (limit = 50, parseStatus?: string) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (parseStatus) qs.set("parse_status", parseStatus);
    return request<TgRawMessageRow[]>(`/trading-bot/raw?${qs.toString()}`);
  },
  tgChannels: () => request<TgChannelRow[]>("/trading-bot/channels"),
  createTgChannel: (body: TgChannelInput) =>
    request<TgChannelRow>("/trading-bot/channels", {
      method: "POST", body: JSON.stringify(body),
    }),
  updateTgChannel: (id: number, body: Partial<TgChannelInput>) =>
    request<TgChannelRow>(`/trading-bot/channels/${id}`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  deleteTgChannel: (id: number) =>
    request<{ deleted: number }>(`/trading-bot/channels/${id}`, { method: "DELETE" }),
  resolveTgChannel: (query: string) =>
    request<TgResolveResult>(`/trading-bot/resolve?query=${encodeURIComponent(query)}`),
  // ===== Trading Bot · Milestone 3 (manual execution) =====
  tgBotSettings: () => request<TgBotSettings>("/trading-bot/settings"),
  updateTgBotSettings: (body: Partial<TgBotSettingsInput>) =>
    request<TgBotSettings>("/trading-bot/settings", {
      method: "PATCH", body: JSON.stringify(body),
    }),
  tgTradeOptions: (signalId: number) =>
    request<TgTradeOptions>(`/trading-bot/signals/${signalId}/trade-options`),
  tgTradeSignal: (signalId: number, body: TgTradeRequest) =>
    request<TgTradeResult>(`/trading-bot/signals/${signalId}/trade`, {
      method: "POST", body: JSON.stringify(body),
    }),
  tgTradesForSignal: (signalId: number) =>
    request<TgTradeRow[]>(`/trading-bot/signals/${signalId}/trades`),
  tgMyTrades: (limit = 50) =>
    request<TgTradeRow[]>(`/trading-bot/trades?limit=${limit}`),

  // ===== Brokers / accounts =====
  listBrokers: () =>
    request<BrokerInfo[]>("/accounts/brokers"),

  listAccounts: () =>
    request<TradingAccountSummary[]>("/accounts"),

  createAccount: (body: {
    broker_code: string; label: string; currency?: string;
    credentials?: Record<string, any>; display_metadata?: Record<string, any>;
  }) => request<TradingAccountSummary>("/accounts", { method: "POST", body: JSON.stringify(body) }),

  deleteAccount: (id: number) =>
    request<{ deleted: number }>(`/accounts/${id}`, { method: "DELETE" }),

  testAccount: (id: number) =>
    request<{ ok: boolean; message: string }>(`/accounts/${id}/test`, { method: "POST" }),

  accountInfo: (id: number) =>
    request<{ account_id: string; balance: string | null; available: string | null; currency: string | null }>(
      `/accounts/${id}/info`,
    ),

  accountPositions: (id: number, refresh = false) =>
    request<any[]>(`/accounts/${id}/positions${refresh ? "?refresh=true" : ""}`),

  // ===== Orders =====
  placeOrder: (body: {
    account_id: number; stock_id?: number; broker_symbol?: string;
    side: "BUY" | "SELL"; order_type: "MARKET" | "LIMIT" | "STOP";
    quantity: number; limit_price?: number; stop_loss?: number; take_profit?: number; notes?: string;
  }) => request<any>("/orders", { method: "POST", body: JSON.stringify(body) }),

  listOrders: (account_id?: number) =>
    request<any[]>(`/orders${account_id ? `?account_id=${account_id}` : ""}`),

  cancelOrder: (id: number) =>
    request<any>(`/orders/${id}`, { method: "DELETE" }),

  // ===== Instruments (admin maps stock <-> broker symbol) =====
  instrumentsForStock: (stock_id: number) =>
    request<BrokerInstrumentMapping[]>(`/instruments/by-stock/${stock_id}`),

  upsertInstrument: (body: {
    broker_code: string; broker_symbol: string; stock_id?: number;
    broker_name?: string; instrument_type?: string; currency?: string;
    min_qty?: number; is_tradeable?: boolean;
  }) => request<{ ok: boolean }>("/instruments", { method: "POST", body: JSON.stringify(body) }),

  deleteInstrument: (broker_code: string, broker_symbol: string) =>
    request<{ deleted: number }>(
      `/instruments/${broker_code}/${encodeURIComponent(broker_symbol)}`,
      { method: "DELETE" },
    ),

  searchBrokerInstruments: (broker_code: string, q: string) =>
    request<Array<{
      broker_symbol: string; name: string; instrument_type: string | null;
      currency: string | null; min_qty: string | null;
    }>>(`/instruments/search/${broker_code}?q=${encodeURIComponent(q)}`),

  // ===== Account stats =====
  accountStats: (id: number, refresh = false) =>
    request<AccountStats>(`/accounts/${id}/stats${refresh ? "?refresh=true" : ""}`),

  accountStatsHistory: (id: number, days = 30) =>
    request<AccountStatsPoint[]>(`/accounts/${id}/stats/history?days=${days}`),

  // ===== Admin: stocks management =====
  adminListStocks: (q?: string, limit = 100, offset = 0) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    qs.set("limit", String(limit));
    qs.set("offset", String(offset));
    return request<AdminStockListItem[]>(`/admin/stocks?${qs.toString()}`);
  },
  adminCreateStock: (body: AdminStockCreateRequest) =>
    request<AdminStockListItem>("/admin/stocks", { method: "POST", body: JSON.stringify(body) }),
  adminPatchStock: (id: number, body: { is_scraping_enabled?: boolean; active?: boolean }) =>
    request<{ id: number; changed: Record<string, any> }>(`/admin/stocks/${id}`, {
      method: "PATCH", body: JSON.stringify(body),
    }),
  adminListExchanges: () =>
    request<Array<{ id: number; code: string; name: string }>>("/admin/exchanges"),

  // ===== Admin: scheduled job settings =====
  listJobSettings: () =>
    request<JobSetting[]>("/admin/settings"),
  updateJobSetting: (key: string, body: JobConfig) =>
    request<JobSetting>(`/admin/settings/${encodeURIComponent(key)}`, {
      method: "PUT", body: JSON.stringify(body),
    }),
  runJob: (key: string) =>
    request<{ status: string; summary?: any; error?: string | null; message?: string }>(
      `/admin/settings/${encodeURIComponent(key)}/run`,
      { method: "POST" },
    ),
  listJobRuns: (job_key?: string, limit = 50) => {
    const qs = new URLSearchParams();
    if (job_key) qs.set("job_key", job_key);
    qs.set("limit", String(limit));
    return request<JobRun[]>(`/admin/settings/runs?${qs.toString()}`);
  },

  // ===== Live broker quotes =====
  listBrokerQuotes: (stock_id: number) =>
    request<BrokerQuoteRow[]>(`/stocks/${stock_id}/broker_quotes`),

  refreshBrokerQuotes: (stock_id: number, broker_id?: number) => {
    const qs = broker_id !== undefined ? `?broker_id=${broker_id}` : "";
    return request<BrokerQuoteRefreshResult>(
      `/stocks/${stock_id}/broker_quotes/refresh${qs}`,
      { method: "POST" },
    );
  },

  // Historical OHLC bars for the live chart. Backed by Capital.com's
  // /api/v1/prices endpoint via broker_gateway. Pure pass-through — nothing
  // is persisted. 409 when the stock has no broker mapping.
  stockBars: (stock_id: number, params: BarsParams) => {
    const qs = new URLSearchParams();
    qs.set("resolution", params.resolution);
    if (params.max_bars != null) qs.set("max_bars", String(params.max_bars));
    if (params.from_ts) qs.set("from_ts", params.from_ts);
    if (params.to_ts) qs.set("to_ts", params.to_ts);
    if (params.broker_id != null) qs.set("broker_id", String(params.broker_id));
    return request<BarsResponse>(`/stocks/${stock_id}/bars?${qs.toString()}`);
  },
};

// ===== Bars (live chart) =====
export type BarResolution =
  | "MINUTE" | "MINUTE_5" | "MINUTE_15" | "MINUTE_30"
  | "HOUR" | "HOUR_4"
  | "DAY" | "WEEK" | "MONTH";

export interface BarsParams {
  resolution: BarResolution;
  max_bars?: number;
  from_ts?: string;
  to_ts?: string;
  broker_id?: number;
}

export interface OhlcBar {
  t: string;               // Capital.com snapshot time, "YYYY/MM/DD HH:MM:SS"
  o: number;
  h: number | null;
  l: number | null;
  c: number;
  v: number | null;
}

export interface BarsResponse {
  broker_id: number;
  symbol: string;
  resolution: BarResolution;
  fetched_at: string;
  bars: OhlcBar[];
}

// ===== Live broker quote types =====
export interface BrokerQuoteRow {
  broker_id: number;
  broker_name: string | null;
  broker_code: string | null;
  broker_symbol: string;
  bid: string | null;
  offer: string | null;
  last_price: string | null;
  open_price: string | null;
  high_price: string | null;
  low_price: string | null;
  close_price: string | null;
  change_abs: string | null;
  change_pct: string | null;
  volume: string | null;
  currency: string | null;
  market_status: string | null;
  fetched_at: string;
}

export interface BrokerQuoteRefreshResult {
  refreshed: Array<{ broker_id: number; broker_symbol: string }>;
  failed: Array<{ broker_id: number; broker_symbol: string }>;
}

// ===== Job settings types =====
export interface JobConfig {
  enabled: boolean;
  cron: string;
  exchanges: string[];
  description?: string | null;
}

export interface JobLastRun {
  started_at: string;
  finished_at: string | null;
  status: string;
  triggered_by: string;
  duration_s: number | null;
  error_message: string | null;
  summary: any;
}

export interface JobSetting {
  key: string;
  label: string;
  purpose: string;
  supports_exchanges: boolean;
  config: JobConfig;
  last_run: JobLastRun | null;
}

export interface JobRun {
  id: number;
  job_key: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  triggered_by: string;
  duration_s: number | null;
  summary: any;
  error_message: string | null;
}

// ===== Account stats types =====
export interface AccountStats {
  account_id: number;
  broker_kind: "automated" | "manual";
  balance: string | null;
  available: string | null;
  equity: string | null;
  unrealized_pl: string | null;
  open_position_count: number | null;
  currency: string | null;
  fetched_at: string;
  source: string;
}

export interface AccountStatsPoint {
  fetched_at: string;
  balance: string | null;
  equity: string | null;
  unrealized_pl: string | null;
  currency: string | null;
  source: string;
}

// ===== Admin stocks types =====
export interface AdminStockListItem {
  id: number;
  ticker: string;
  exchange_code: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  currency: string | null;
  country: string | null;
  isin: string | null;
  active: boolean;
  is_scraping_enabled: boolean;
  last_close: number | null;
  last_updated: string | null;
}

export interface AdminStockCreateRequest {
  exchange_code: string;
  ticker: string;
  company_name: string;
  isin?: string;
  marketscreener_slug?: string;
  sector?: string;
  industry?: string;
  currency?: string;
  country?: string;
  founded_year?: number;
  employees?: number;
  website?: string;
  is_scraping_enabled?: boolean;
}

// ===== Broker types =====
export interface BrokerCredentialField {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  default?: any;
}

export interface BrokerInfo {
  id: number;
  code: string;
  name: string;
  kind: "automated" | "manual";
  docs_url: string | null;
  credential_schema: BrokerCredentialField[];
}

export interface TradingAccountSummary {
  id: number;
  broker_code: string;
  broker_name: string;
  broker_kind: "automated" | "manual";
  label: string;
  currency: string | null;
  is_active: boolean;
  last_connect_status: string | null;
  last_connect_error: string | null;
  last_connect_at: string | null;
  display_metadata: Record<string, any>;
}

export interface BrokerInstrumentMapping {
  broker_code: string;
  broker_name: string;
  broker_symbol: string;
  instrument_type: string | null;
  currency: string | null;
  min_qty: string | null;
}


export interface ImportTableColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  unique: boolean;
  foreign_key: string | null;
  default: string | null;
}

export interface ImportTable {
  name: string;
  label: string;
  primary_key: string[];
  unique_constraints: string[][];
  suggested_match_columns: string[];
  columns: ImportTableColumn[];
}

export interface ImportCatalog {
  tables: ImportTable[];
}

export interface ImportPreviewRow {
  row_number: number;
  values: Record<string, string | null>;
}

export interface ImportPreview {
  import_id: string;
  filename: string;
  encoding: string;
  delimiter: string;
  row_count: number;
  headers: string[];
  sample_rows: ImportPreviewRow[];
}

export interface ImportExecuteRequest {
  import_id: string;
  table_name: string;
  mode: "update" | "insert";
  column_mapping: Record<string, string>;
  match_columns: string[];
  ignore_blank_values?: boolean;
}

export interface ImportRowLog {
  row_number: number;
  action: string;
  message: string;
}

export interface ImportExecuteResult {
  import_id: string;
  table_name: string;
  mode: string;
  encoding: string;
  delimiter: string;
  processed: number;
  inserted: number;
  updated: number;
  skipped: number;
  errors: number;
  row_logs: ImportRowLog[];
  finished_at: string;
}

// ===== Bulk CSV import (stockanalysis.com exchange exports) =====
export interface BulkImportPreview {
  headers: string[];
  header_count: number;
  row_count: number;
  has_symbol_column: boolean;
  rows_with_no_symbol: number;
  sample_tickers: string[];
  samples: Array<{
    ticker: string | null;
    company_name: string | null;
    sector: string | null;
    stock_price: string | null;
    market_cap: string | null;
    pe_ratio: string | null;
    last_report_date: string | null;
  }>;
}

export interface BulkImportRowLog {
  row_number: number;
  action: string;   // inserted | updated | skipped | error
  message: string;
}

export interface BulkImportResult {
  import_id: number;
  status: string;   // ok | failed
  rows_total: number;
  rows_inserted: number;
  rows_updated: number;
  rows_skipped: number;
  rows_errored: number;
  row_logs: BulkImportRowLog[];
}

export interface BulkImportHistoryEntry {
  id: number;
  exchange_code: string;
  user_email: string | null;
  filename: string | null;
  started_at: string;
  finished_at: string | null;
  status: string;
  rows_total: number;
  rows_inserted: number;
  rows_updated: number;
  rows_skipped: number;
  rows_errored: number;
  error_message: string | null;
}

// ===== Alerts =====
// One entry in a rule/channel schema — drives dynamic form rendering.
export interface AlertSchemaField {
  name: string;
  type: "text" | "number" | "select" | "textarea" | "password";
  label: string;
  required?: boolean;
  default?: string | number | boolean;
  options?: string[];     // for type=select
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
}

export interface AlertRuleType {
  key: string;
  label: string;
  description: string;
  params_schema: AlertSchemaField[];
}

export interface AlertChannelType {
  key: string;
  label: string;
  config_schema: AlertSchemaField[];
}

export interface AlertsMeta {
  rules: AlertRuleType[];
  channels: AlertChannelType[];
}

export interface AlertChannelInput {
  name: string;
  channel_type: string;
  config: Record<string, unknown>;
  is_active?: boolean;
}

export interface AlertChannelRow extends AlertChannelInput {
  id: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleInput {
  name: string;
  rule_type: string;
  params: Record<string, unknown>;
  stock_filter?: Record<string, unknown> | null;
  interval_seconds: number;
  cooldown_seconds: number;
  is_enabled?: boolean;
  channel_ids: number[];
}

export interface AlertRuleRow extends AlertRuleInput {
  id: number;
  is_enabled: boolean;
  last_evaluated_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertEventRow {
  id: number;
  rule_id: number;
  rule_name: string;
  stock_id: number | null;
  fired_at: string;
  title: string;
  body: string | null;
  delivery: Record<string, { status: string; error: string | null }>;
  snapshot: Record<string, unknown> | null;
}

export interface AlertsEvaluateSummary {
  rules_total: number;
  rules_evaluated: number;
  rules_skipped_interval: number;
  rules_errored: number;
  alerts_fired: number;
  alerts_skipped_cooldown: number;
}

// ===== Trading Bot =====
export interface TgSignalRow {
  id: number;
  signal_time: string;
  symbol: string;
  direction: "BUY" | "SELL";
  entry_from: number;
  entry_to: number;
  sl: number;
  tps: number[];
  parser_key: string;
  status: string;
  channel_id: number;
  channel_title: string | null;
  raw_text: string | null;
}

export interface TgRawMessageRow {
  id: number;
  channel_id: number;
  channel_title: string | null;
  tg_message_id: number;
  received_at: string;
  processed_at: string | null;
  parse_status: "pending" | "signal" | "noise" | "failed";
  parse_error: string | null;
  message_text: string | null;
}

export interface TgChannelInput {
  channel_id: number;
  channel_title: string;
  channel_username?: string | null;
  parser_key?: string;
  is_enabled?: boolean;
  notes?: string | null;
  // Strategy params (Milestone 2)
  order_position_type?: "MARKET" | "LIMIT" | "STOP";
  tp_strategy?: string;
  is_tradeable?: boolean;
  is_trusted?: boolean;
  image_url?: string | null;
}

export interface TgChannelRow extends TgChannelInput {
  id: number;
  is_enabled: boolean;
  parser_key: string;
  order_position_type: "MARKET" | "LIMIT" | "STOP";
  tp_strategy: string;
  is_tradeable: boolean;
  is_trusted: boolean;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TgResolveResult {
  channel_id: number;
  title: string;
  username: string | null;
  kind: string;
}

// ===== Trading Bot · Milestone 3 =====
export interface TgBotSettings {
  "tgbot.risk_pct_per_trade": number;
  "tgbot.max_risk_pct_per_trade": number;
  "tgbot.min_lot_size": number;
  "tgbot.lot_step": number;
  "tgbot.default_tp_level": string;
}

export interface TgBotSettingsInput {
  risk_pct_per_trade?: number;
  max_risk_pct_per_trade?: number;
  min_lot_size?: number;
  lot_step?: number;
  default_tp_level?: string;
}

export interface TgTradeAccountOption {
  account_id: number;
  broker_id: number;
  broker_code: string;
  broker_name: string;
  account_label: string;
  account_type: string | null;
  currency: string | null;
  is_active: boolean;
  resolved_symbol: string;
}

export interface TgChannelStrategy {
  order_position_type: "MARKET" | "LIMIT" | "STOP";
  tp_strategy: string;
  is_tradeable: boolean;
  is_trusted: boolean;
}

export interface TgTradeOptions {
  signal: TgSignalRow;
  settings: TgBotSettings;
  accounts: TgTradeAccountOption[];
  channel_strategy: TgChannelStrategy | null;
}

export interface TgTradeOrderLeg {
  broker_symbol: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP";
  quantity: number;
  limit_price: number | null;
  stop_loss: number;
  take_profit: number;
  tp_level: string;          // "TP1" | "TP2" | …
}

export interface TgTradeRequest {
  account_id: number;
  total_risk_pct: number;
  notes?: string | null;
  legs: TgTradeOrderLeg[];
}

export interface TgTradeResult {
  bot_trade_id: number;
  order_id: number;
  signal_id: number;
  order: any;
}

export interface TgTradeRow {
  id: number;
  signal_id: number;
  order_id: number;
  account_id: number;
  tp_level: string | null;
  risk_pct: number | null;
  trade_mode: string;
  notes: string | null;
  created_at: string;
  signal: {
    symbol: string; direction: "BUY" | "SELL";
    channel_title: string | null;
    signal_time: string;
  } | null;
  order: {
    side: string; order_type: string;
    quantity: number;
    limit_price: number | null;
    stop_loss: number | null;
    take_profit: number | null;
    status: string;
    fill_price: number | null;
    broker_order_ref: string | null;
    rejection_reason: string | null;
    placed_at: string;
    filled_at: string | null;
  } | null;
}
