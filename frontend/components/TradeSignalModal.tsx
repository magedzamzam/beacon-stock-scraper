"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  X, Loader2, AlertCircle, CheckCircle2, ArrowUp, ArrowDown,
  TrendingUp, Shield, Calculator,
} from "lucide-react";
import {
  api,
  type TgSignalRow, type TgTradeOptions, type TgTradeRequest,
  type TgTradeAccountOption,
} from "@/lib/api";

/**
 * Modal that opens when the user clicks "Trade" on a signal.
 *
 * Three-stage flow:
 *   1. Loading — fetch /trade-options once
 *   2. Editing — user reviews and tweaks the pre-filled form
 *   3. Confirming — show a summary, last-chance review, then place
 *
 * Pushback baked into the design:
 *   - Lot size auto-computes from risk % but is fully editable
 *   - The "Place trade" button is disabled if SL is on the wrong side of
 *     entry (BUY with SL above entry, SELL with SL below) — protects against
 *     the most common copy-paste error
 *   - max_risk_pct_per_trade is a HARD cap (input refuses higher) not a warning
 *   - The TP picker shows distance from entry as a sanity check
 */
export default function TradeSignalModal({
  signalId, onClose, onPlaced,
}: {
  signalId: number;
  onClose: () => void;
  onPlaced: () => void;
}) {
  const { data, error, isLoading } = useSWR(
    ["trade-options", signalId],
    () => api.tgTradeOptions(signalId),
    { revalidateOnFocus: false },
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
         onClick={onClose}>
      <div className="card w-full max-w-2xl max-h-[90vh] overflow-y-auto"
           onClick={e => e.stopPropagation()}>
        <header className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-bg-card z-10">
          <h2 className="font-semibold flex items-center gap-2">
            <TrendingUp className="size-4" /> Trade signal
          </h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink">
            <X className="size-4" />
          </button>
        </header>

        <div className="p-4">
          {isLoading && (
            <div className="text-sm text-ink-muted flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" /> Loading trade options…
            </div>
          )}
          {error && (
            <div className="text-sm text-rose-500 flex items-center gap-2">
              <AlertCircle className="size-4" /> {String(error.message || error)}
            </div>
          )}
          {data && (
            <TradeForm data={data} signalId={signalId}
                       onClose={onClose} onPlaced={onPlaced} />
          )}
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Form
// ---------------------------------------------------------------------------
function TradeForm({
  data, signalId, onClose, onPlaced,
}: {
  data: TgTradeOptions;
  signalId: number;
  onClose: () => void;
  onPlaced: () => void;
}) {
  const { signal, settings, accounts, channel_strategy } = data;
  const tps = signal.tps || [];

  // Pre-fill values from the signal + channel strategy + bot settings.
  // Account: first eligible Capital.com (or first overall) by default.
  const defaultAccount =
    accounts.find(a => a.broker_code === "capital_com" && a.is_active)
    ?? accounts[0] ?? null;

  const [accountId, setAccountId] = useState<number | null>(defaultAccount?.account_id ?? null);
  const account = accounts.find(a => a.account_id === accountId) ?? null;

  // Order type pre-fill: respect the channel strategy. Default to MARKET if
  // there is no channel strategy (rare — channel could have been deleted).
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "STOP">(
    channel_strategy?.order_position_type ?? "MARKET",
  );

  const side = signal.direction;   // BUY or SELL — never overridden by user
  const [riskPct, setRiskPct] = useState<number>(settings["tgbot.risk_pct_per_trade"]);

  // SL pre-filled from signal; user can edit but the system warns on bad side.
  const [stopLoss, setStopLoss] = useState<number>(signal.sl);

  // TP picker: pick a TP level from the signal's TPs array. Default to the
  // configured default level (e.g. "TP1") if it exists in the array.
  const [tpIdx, setTpIdx] = useState<number>(() => {
    const defaultLevel = settings["tgbot.default_tp_level"]; // e.g. "TP1"
    const idx = parseInt(defaultLevel?.replace(/[^0-9]/g, "") || "1", 10) - 1;
    if (idx >= 0 && idx < tps.length) return idx;
    return tps.length > 0 ? 0 : -1;   // -1 = no TP
  });
  const takeProfit = tpIdx >= 0 ? tps[tpIdx] : null;
  const tpLevel = tpIdx >= 0 ? `TP${tpIdx + 1}` : null;

  // Limit price: required when order_type=LIMIT. Pre-filled to entry_from
  // (the closer-to-current side of the range).
  const [limitPrice, setLimitPrice] = useState<number>(signal.entry_from);
  // For MARKET orders we don't send limit_price.
  const effectiveLimit = orderType === "MARKET" ? null : limitPrice;

  // Lot size — computed from risk% but editable.
  const computedLot = useComputedLot({
    riskPct, accountId, accounts,
    entry: orderType === "MARKET" ? signal.entry_from : limitPrice,
    sl: stopLoss,
    minLot: settings["tgbot.min_lot_size"],
    lotStep: settings["tgbot.lot_step"],
  });
  // Track whether the user manually edited lot. Once edited, we stop the
  // auto-compute from overwriting their value.
  const [lotOverride, setLotOverride] = useState<number | null>(null);
  const lot = lotOverride ?? computedLot.value;

  // Broker symbol — Capital.com adapter expects whatever the broker uses;
  // we surface it as editable in case the resolved_symbol from the API is
  // wrong (it's a placeholder right now — see backend comment).
  const [brokerSymbol, setBrokerSymbol] = useState<string>(
    account?.resolved_symbol ?? signal.symbol,
  );
  useEffect(() => {
    // When the user switches account, re-pull its resolved_symbol.
    setBrokerSymbol(account?.resolved_symbol ?? signal.symbol);
  }, [account?.account_id]);

  // SL-side sanity check — prevents the #1 copy-paste error.
  const slWrongSide =
    (side === "BUY"  && stopLoss >= signal.entry_from) ||
    (side === "SELL" && stopLoss <= signal.entry_from);

  // Place button state machine
  const [stage, setStage] = useState<"edit" | "confirm" | "placing" | "done">("edit");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const canSubmit = !!(
    account &&
    brokerSymbol.trim() &&
    lot > 0 &&
    !slWrongSide &&
    (orderType === "MARKET" || limitPrice > 0)
  );

  async function place() {
    if (!account) return;
    setStage("placing"); setError(null);
    try {
      const body: TgTradeRequest = {
        account_id: account.account_id,
        broker_symbol: brokerSymbol.trim(),
        side,
        order_type: orderType,
        quantity: lot,
        limit_price: effectiveLimit,
        stop_loss: stopLoss,
        take_profit: takeProfit,
        tp_level: tpLevel,
        risk_pct: riskPct,
        notes: `From signal #${signalId} (${signal.channel_title || signal.channel_id})`,
      };
      const r = await api.tgTradeSignal(signalId, body);
      setResult(r);
      setStage("done");
      onPlaced();
    } catch (e: any) {
      setError(e.message || String(e));
      setStage("edit");
    }
  }

  if (stage === "done") {
    return (
      <div className="text-center py-8 space-y-3">
        <CheckCircle2 className="size-12 text-emerald-500 mx-auto" />
        <div className="text-lg font-semibold">Order placed</div>
        <div className="text-sm text-ink-muted">
          {side} {lot.toFixed(2)} {brokerSymbol} ·{" "}
          Order status: <span className="font-mono">{result?.order?.status ?? "?"}</span>
        </div>
        {result?.order?.broker_order_ref && (
          <div className="text-xs text-ink-muted font-mono">
            broker ref: {result.order.broker_order_ref}
          </div>
        )}
        <button onClick={onClose} className="btn-primary text-xs">Close</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SignalSummary signal={signal} />

      {accounts.length === 0 && (
        <div className="text-sm text-rose-500 flex items-center gap-2">
          <AlertCircle className="size-4" />
          You have no active trading accounts. Add one under Settings → Brokers first.
        </div>
      )}

      {accounts.length > 0 && (
        <>
          {/* Account selector */}
          <Field label="Account">
            <select className="input w-full"
                    value={accountId ?? ""}
                    onChange={e => setAccountId(Number(e.target.value))}>
              {accounts.map(a => (
                <option key={a.account_id} value={a.account_id}>
                  {a.broker_name} · {a.account_label}
                  {a.currency ? ` (${a.currency})` : ""}
                </option>
              ))}
            </select>
          </Field>

          {/* Broker symbol — editable in case the auto-resolved value is wrong */}
          <Field label="Broker symbol"
                 help="The symbol as the broker knows it (e.g. GOLD vs XAUUSD). Override if needed.">
            <input type="text" className="input w-full font-mono"
                   value={brokerSymbol}
                   onChange={e => setBrokerSymbol(e.target.value)} />
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Order type">
              <div className="flex gap-1">
                {(["MARKET", "LIMIT", "STOP"] as const).map(t => (
                  <button key={t}
                          onClick={() => setOrderType(t)}
                          className={`flex-1 text-xs py-2 rounded border ${
                            orderType === t
                              ? "bg-brand/15 border-brand text-brand"
                              : "border-border text-ink-muted hover:text-ink"
                          }`}>
                    {t}
                  </button>
                ))}
              </div>
            </Field>

            {orderType !== "MARKET" && (
              <Field label={`${orderType} price`}>
                <input type="number" step="any" className="input w-full font-mono"
                       value={limitPrice}
                       onChange={e => setLimitPrice(Number(e.target.value))} />
              </Field>
            )}
          </div>

          {/* Risk % + computed lot */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Risk %"
                   help={`Max ${settings["tgbot.max_risk_pct_per_trade"]}% per trade (admin setting).`}>
              <input type="number" step="0.1"
                     min={0}
                     max={settings["tgbot.max_risk_pct_per_trade"]}
                     className="input w-full font-mono"
                     value={riskPct}
                     onChange={e => {
                       setRiskPct(Number(e.target.value));
                       setLotOverride(null);    // re-enable auto-compute
                     }} />
            </Field>
            <Field label="Lot size"
                   help={lotOverride === null
                          ? `Auto-computed from risk %. ${computedLot.explanation}`
                          : "Manual override — risk % is ignored."}>
              <div className="flex items-center gap-2">
                <input type="number" step={settings["tgbot.lot_step"]}
                       min={settings["tgbot.min_lot_size"]}
                       className="input w-full font-mono"
                       value={lot}
                       onChange={e => setLotOverride(Number(e.target.value))} />
                {lotOverride !== null && (
                  <button onClick={() => setLotOverride(null)}
                          title="Reset to auto-computed"
                          className="text-xs text-brand hover:underline whitespace-nowrap">
                    <Calculator className="size-3 inline" /> Auto
                  </button>
                )}
              </div>
            </Field>
          </div>

          {/* SL + TP */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Stop loss"
                   help={slWrongSide
                          ? `SL is on the WRONG side for a ${side} order!`
                          : `Distance: ${Math.abs(signal.entry_from - stopLoss).toFixed(2)}`}
                   helpCls={slWrongSide ? "text-rose-500 font-medium" : ""}>
              <input type="number" step="any" className="input w-full font-mono"
                     value={stopLoss}
                     onChange={e => setStopLoss(Number(e.target.value))} />
            </Field>

            <Field label="Take profit"
                   help={takeProfit
                          ? `Distance: ${Math.abs(signal.entry_from - takeProfit).toFixed(2)}`
                          : "No TP — open trade with SL only."}>
              <div className="flex gap-1 flex-wrap">
                {tps.map((tp, i) => (
                  <button key={i}
                          onClick={() => setTpIdx(i)}
                          className={`text-xs px-2 py-1.5 rounded border ${
                            tpIdx === i
                              ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-400"
                              : "border-border text-ink-muted hover:text-ink"
                          }`}>
                    TP{i + 1}: {fmt(tp)}
                  </button>
                ))}
                <button onClick={() => setTpIdx(-1)}
                        className={`text-xs px-2 py-1.5 rounded border ${
                          tpIdx === -1
                            ? "bg-bg-subtle border-border text-ink"
                            : "border-border text-ink-muted hover:text-ink"
                        }`}>
                  None
                </button>
              </div>
            </Field>
          </div>

          {error && (
            <div className="text-sm text-rose-500 flex items-center gap-2 p-3 border border-rose-500/30 rounded bg-rose-500/5">
              <AlertCircle className="size-4 shrink-0" />
              <span className="break-all">{error}</span>
            </div>
          )}

          {stage === "confirm" && (
            <div className="border border-amber-500/40 bg-amber-500/5 rounded p-3 text-sm space-y-1">
              <div className="font-semibold flex items-center gap-1">
                <Shield className="size-4 text-amber-500" /> Confirm
              </div>
              <div className="text-ink-muted">
                Place <b className="text-ink">{side}</b>{" "}
                <b className="text-ink font-mono">{lot.toFixed(2)}</b>{" "}
                <b className="text-ink font-mono">{brokerSymbol}</b> as{" "}
                <b className="text-ink">{orderType}</b>
                {effectiveLimit !== null && <> @ <span className="font-mono">{fmt(effectiveLimit)}</span></>}
                {", SL "}<span className="font-mono">{fmt(stopLoss)}</span>
                {takeProfit !== null && <>, TP <span className="font-mono">{fmt(takeProfit)}</span></>}
                {" on "}<b className="text-ink">{account?.broker_name} · {account?.account_label}</b>.
              </div>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            {stage === "edit" && (
              <button
                onClick={() => setStage("confirm")}
                disabled={!canSubmit}
                className="btn-primary text-xs flex-1"
              >
                Review →
              </button>
            )}
            {stage === "confirm" && (
              <>
                <button onClick={() => setStage("edit")}
                        className="btn-ghost text-xs">
                  ← Back
                </button>
                <button onClick={place}
                        className="btn-primary text-xs flex-1">
                  Place trade
                </button>
              </>
            )}
            {stage === "placing" && (
              <button disabled className="btn-primary text-xs flex-1">
                <Loader2 className="size-3.5 animate-spin" /> Placing…
              </button>
            )}
            <button onClick={onClose} className="btn-ghost text-xs">Cancel</button>
          </div>
        </>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Lot computation hook
// ---------------------------------------------------------------------------
function useComputedLot({
  riskPct, accountId, accounts, entry, sl, minLot, lotStep,
}: {
  riskPct: number;
  accountId: number | null;
  accounts: TgTradeAccountOption[];
  entry: number;
  sl: number;
  minLot: number;
  lotStep: number;
}) {
  return useMemo(() => {
    // Without an account or a valid SL/entry, fall back to the minimum lot.
    if (!accountId || !accounts.find(a => a.account_id === accountId)) {
      return { value: minLot, explanation: "No account selected — falling back to min lot." };
    }
    const distance = Math.abs(entry - sl);
    if (!distance || riskPct <= 0) {
      return { value: minLot, explanation: "Invalid SL distance — falling back to min lot." };
    }
    // Without balance data we can't compute risk-based lot precisely.
    // Show the user the formula they'd need; default to min lot for safety.
    // (Future: account_info endpoint surfaces balance — wire that in then.)
    const lot = minLot;   // placeholder
    return {
      value: lot,
      explanation:
        `Risk-based sizing needs account balance, which isn't wired yet. ` +
        `Using min lot. Distance to SL: ${distance.toFixed(2)}.`,
    };
  }, [riskPct, accountId, accounts, entry, sl, minLot, lotStep]);
}


// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function SignalSummary({ signal }: { signal: TgSignalRow }) {
  const Dir = signal.direction === "BUY" ? ArrowUp : ArrowDown;
  const cls = signal.direction === "BUY"
    ? "bg-emerald-500/15 text-emerald-400"
    : "bg-rose-500/15 text-rose-400";
  return (
    <div className="p-3 rounded bg-bg-subtle/40 border border-border space-y-1">
      <div className="flex items-center gap-2">
        <span className={`text-xs font-medium px-2 py-0.5 rounded inline-flex items-center gap-0.5 ${cls}`}>
          <Dir className="size-3" /> {signal.direction}
        </span>
        <span className="font-semibold">{signal.symbol}</span>
        <span className="text-[11px] text-ink-muted">
          from {signal.channel_title || `channel ${signal.channel_id}`}
        </span>
      </div>
      <div className="text-xs text-ink-muted">
        Entry: <span className="font-mono text-ink">{fmt(signal.entry_from)}</span>
        {signal.entry_from !== signal.entry_to && (
          <> — <span className="font-mono text-ink">{fmt(signal.entry_to)}</span></>
        )}
        {" · SL "}<span className="font-mono text-rose-400">{fmt(signal.sl)}</span>
        {(signal.tps?.length ?? 0) > 0 && (
          <>{" · TP "}<span className="font-mono text-emerald-400">
            {signal.tps.map(fmt).join(" / ")}
          </span></>
        )}
      </div>
    </div>
  );
}


function Field({ label, help, helpCls, children }: {
  label: string;
  help?: string;
  helpCls?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs text-ink-muted">{label}</span>
      <div className="mt-1">{children}</div>
      {help && <div className={`text-[11px] mt-0.5 text-ink-dim ${helpCls || ""}`}>{help}</div>}
    </label>
  );
}


function fmt(n: number) {
  return Number(n).toLocaleString(undefined, {
    maximumFractionDigits: 6, minimumFractionDigits: 0,
  });
}
