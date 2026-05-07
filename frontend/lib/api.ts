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
}

export interface PriceHistoryPoint {
  trading_date: string;
  close: number | null;
  volume: number | null;
}

export interface NewsItem {
  id: number;
  news_date: string;
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

// ===== CSV import (admin) =====
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

export interface ImportPreview {
  import_id: string;
  filename: string;
  encoding: string;
  delimiter: string;
  row_count: number;
  headers: string[];
  sample_rows: Array<{ row_number: number; values: Record<string, string | null> }>;
}

export interface ImportRowLog {
  row_number: number;
  outcome: "inserted" | "updated" | "skipped" | "error";
  message: string;
}

export interface ImportExecuteRequest {
  import_id: string;
  table_name: string;
  mode: "update" | "insert";
  column_mapping: Record<string, string>;
  match_columns: string[];
  ignore_blank_values?: boolean;
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
  addPosition: (stock_id: number, quantity: number, avg_entry_price: number, entry_date?: string, notes?: string) =>
    request<Position>("/portfolio", {
      method: "POST",
      body: JSON.stringify({ stock_id, quantity, avg_entry_price, entry_date, notes }),
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

  // ===== Brokers / accounts =====
  listBrokers: () =>
    request<Array<{ id: number; code: string; name: string; kind: "automated" | "manual"; docs_url: string | null;
                    credential_schema: Array<{ key: string; label: string; type: string; required?: boolean; default?: any }> }>>(
      "/accounts/brokers",
    ),

  listAccounts: () =>
    request<Array<{ id: number; broker_code: string; broker_name: string; broker_kind: "automated" | "manual";
                    label: string; currency: string | null; is_active: boolean;
                    last_connect_status: string | null; last_connect_error: string | null;
                    last_connect_at: string | null; display_metadata: Record<string, any> }>>(
      "/accounts",
    ),

  createAccount: (body: { broker_code: string; label: string; currency?: string;
                          credentials?: Record<string, any>; display_metadata?: Record<string, any> }) =>
    request<any>("/accounts", { method: "POST", body: JSON.stringify(body) }),

  deleteAccount: (id: number) => request<any>(`/accounts/${id}`, { method: "DELETE" }),

  testAccount: (id: number) => request<{ ok: boolean; message: string }>(`/accounts/${id}/test`, { method: "POST" }),

  accountInfo: (id: number) =>
    request<{ account_id: string; balance: string | null; available: string | null; currency: string | null }>(
      `/accounts/${id}/info`,
    ),

  accountPositions: (id: number, refresh = false) =>
    request<Array<any>>(`/accounts/${id}/positions${refresh ? "?refresh=true" : ""}`),

  // ===== Orders =====
  placeOrder: (body: {
    account_id: number; stock_id?: number; broker_symbol?: string;
    side: "BUY" | "SELL"; order_type: "MARKET" | "LIMIT" | "STOP";
    quantity: number; limit_price?: number; stop_loss?: number; take_profit?: number; notes?: string;
  }) => request<any>("/orders", { method: "POST", body: JSON.stringify(body) }),

  listOrders: (account_id?: number) =>
    request<Array<any>>(`/orders${account_id ? `?account_id=${account_id}` : ""}`),

  cancelOrder: (id: number) => request<any>(`/orders/${id}`, { method: "DELETE" }),

  // ===== Instruments (admin maps stock <-> broker symbol) =====
  instrumentsForStock: (stock_id: number) =>
    request<Array<{ broker_code: string; broker_name: string; broker_symbol: string;
                    instrument_type: string | null; currency: string | null; min_qty: string | null }>>(
      `/instruments/by-stock/${stock_id}`,
    ),

  upsertInstrument: (body: {
    broker_code: string; broker_symbol: string; stock_id?: number;
    broker_name?: string; instrument_type?: string; currency?: string;
    min_qty?: number; is_tradeable?: boolean;
  }) => request<any>("/instruments", { method: "POST", body: JSON.stringify(body) }),

  deleteInstrument: (broker_code: string, broker_symbol: string) =>
    request<any>(`/instruments/${broker_code}/${encodeURIComponent(broker_symbol)}`, { method: "DELETE" }),

  searchBrokerInstruments: (broker_code: string, q: string) =>
    request<Array<{ broker_symbol: string; name: string; instrument_type: string | null;
                    currency: string | null; min_qty: string | null }>>(
      `/instruments/search/${broker_code}?q=${encodeURIComponent(q)}`,
    ),
  // ===== CSV import (admin) =====
  adminImportCatalog: () =>
    request<ImportTable[]>("/admin/import/catalog").then((tables) => ({ tables })),

  adminImportPreview: async (file: File): Promise<ImportPreview> => {
    const fd = new FormData();
    fd.append("file", file);
    const token = localStorage.getItem("token");
    const r = await fetch(`${API_BASE}/admin/import/preview`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  adminImportExecute: (payload: ImportExecuteRequest) =>
    request<ImportExecuteResult>("/admin/import/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
