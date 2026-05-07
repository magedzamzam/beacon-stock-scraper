import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtNumber(n: number | null | undefined, opts?: { digits?: number; compact?: boolean }) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const digits = opts?.digits ?? 2;
  if (opts?.compact && Math.abs(n) >= 1000) {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(n);
  }
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

export function fmtPercent(n: number | null | undefined, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtMoney(n: number | null | undefined, currency = "AED", compact = false) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const code = (currency || "").trim();
  const formatted = fmtNumber(n, { digits: 2, compact });
  return code ? `${code} ${formatted}` : formatted;
}

/**
 * Format a price with its currency, e.g. fmtPrice(1.87, 'AED') -> 'AED 1.87'.
 * Drops the prefix when no currency is known so we never print 'undefined 1.87'.
 */
export function fmtPrice(n: number | null | undefined, currency: string | null | undefined, opts?: { digits?: number; compact?: boolean }) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const code = (currency || "").trim();
  const formatted = fmtNumber(n, { digits: opts?.digits ?? 2, compact: opts?.compact });
  return code ? `${code} ${formatted}` : formatted;
}

/** Pleasant CSS class for sentiment label badges. */
export function sentimentBadgeClass(label: string | null | undefined): string {
  switch ((label || "").toLowerCase()) {
    case "positive": return "badge bg-verdict-buy/15 text-verdict-buy ring-1 ring-verdict-buy/30";
    case "negative": return "badge bg-verdict-avoid/15 text-verdict-avoid ring-1 ring-verdict-avoid/30";
    case "neutral":  return "badge bg-bg-elevated text-ink-muted ring-1 ring-border";
    default: return "";
  }
}

export function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch { return s; }
}

export function changeColor(n: number | null | undefined): string {
  if (n === null || n === undefined) return "text-ink-muted";
  if (n > 0) return "text-verdict-buy";
  if (n < 0) return "text-verdict-avoid";
  return "text-ink-muted";
}

export function verdictBadgeClass(v: string | null | undefined): string {
  switch (v) {
    case "BUY": return "badge-buy";
    case "WATCH": return "badge-watch";
    case "STAY_AWAY": return "badge-avoid";
    case "HOLD": return "badge-hold";
    case "SELL": return "badge-sell";
    case "BUY_MORE": return "badge-buymore";
    case "TRIM": return "badge-trim";
    case "STOP_LOSS": return "badge-stop";
    default: return "badge bg-bg-elevated text-ink-muted";
  }
}

export function verdictLabel(v: string | null | undefined): string {
  if (!v) return "—";
  return v.replace(/_/g, " ");
}
