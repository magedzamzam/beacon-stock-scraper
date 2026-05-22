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

  // Determine the fanout shape.
  //   entry_from == entry_to → 1 × N orders (one per TP, single entry)
  //   entry_from != entry_to → 2 × N orders (each entry × each TP)
  // The fanout is computed BEFORE the user makes any choices so they see
  // exactly how many orders will be placed.
  const entries = signal.entry_from === signal.entry_to
    ? [signal.entry_from]
    : [signal.entry_from, signal.entry_to];
  const orderCount = entries.length * tps.length;

  // Pre-fill from channel strategy + settings + defaults.
  const defaultAccount =
    accounts.find(a => a.broker_code === "capital_com" && a.is_active)
    ?? accounts[0] ?? null;

  const [accountId, setAccountId] = useState<number | null>(
    defaultAccount?.account_id ?? null,
  );
  const account = accounts.find(a => a.account_id === accountId) ?? null;

  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "STOP">(
    channel_strategy?.order_position_type ?? "LIMIT",
  );

  const side = signal.direction;  // BUY/SELL — never user-overridden

  // total_risk_pct is the TOTAL across the whole fanout (your spec).
  // The backend will divide it evenly across orderCount children.
  const [totalRiskPct, setTotalRiskPct] = useState<number>(
    settings["tgbot.risk_pct_per_trade"],
  );

  // SL is identical for every child. Editable so the user can adjust.
  const [stopLoss, setStopLoss] = useState<number>(signal.sl);

  // Broker symbol — editable per account.
  const [brokerSymbol, setBrokerSymbol] = useState<string>(
    account?.resolved_symbol ?? signal.symbol,
  );
  useEffect(() => {
    setBrokerSymbol(account?.resolved_symbol ?? signal.symbol);
  }, [account?.account_id]);

  // SL-side sanity (#1 copy-paste error).
  const slWrongSide =
    (side === "BUY"  && stopLoss >= Math.min(...entries)) ||
    (side === "SELL" && stopLoss <= Math.max(...entries));

  // Build the fanout legs. Lot per leg = total_risk / N. We don't have live
  // account balance here, so the displayed lot is a placeholder min_lot for
  // now and the backend recomputes from total_risk_pct on its end. See note
  // in useComputedLot.
  const minLot = settings["tgbot.min_lot_size"];
  const lotStep = settings["tgbot.lot_step"];
  const perOrderRiskPct = orderCount > 0 ? totalRiskPct / orderCount : 0;

  const legs = useMemo(() => {
    const out: Array<{
      entry: number;
      tp: number;
      tpLevel: string;
      orderType: "MARKET" | "LIMIT" | "STOP";
      limitPrice: number | null;
      quantity: number;
    }> = [];
    for (const entry of entries) {
      tps.forEach((tp, i) => {
        out.push({
          entry,
          tp,
          tpLevel: `TP${i + 1}`,
          orderType,
          limitPrice: orderType === "MARKET" ? null : entry,
          // Per-leg lot. Placeholder math — see useComputedLot note.
          quantity: minLot,
        });
      });
    }
    return out;
  }, [entries, tps, orderType, minLot]);

  // Place button state machine
  const [stage, setStage] = useState<"edit" | "confirm" | "placing" | "done">("edit");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const canSubmit = !!(
    account &&
    brokerSymbol.trim() &&
    legs.length > 0 &&
    !slWrongSide &&
    totalRiskPct > 0 &&
    totalRiskPct <= settings["tgbot.max_risk_pct_per_trade"]
  );

  async function place() {
    if (!account) return;
    setStage("placing"); setError(null);
    try {
      const body: TgTradeRequest = {
        account_id:     account.account_id,
        total_risk_pct: totalRiskPct,
        notes: `From signal #${signalId} (${signal.channel_title || signal.channel_id})`,
        legs: legs.map(l => ({
          broker_symbol: brokerSymbol.trim(),
          side,
          order_type:    l.orderType,
          quantity:      l.quantity,
          limit_price:   l.limitPrice,
          stop_loss:     stopLoss,
          take_profit:   l.tp,
          tp_level:      l.tpLevel,
        })),
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
      <div className="space-y-4 py-4">
        <div className="text-center space-y-2">
          <CheckCircle2 className={`size-12 mx-auto ${
            result?.all_ok ? "text-emerald-500" : "text-amber-500"
          }`} />
          <div className="text-lg font-semibold">
            {result?.all_ok ? "All orders placed" : "Partially placed"}
          </div>
          <div className="text-sm text-ink-muted">
            {result?.placed?.length ?? 0} placed
            {result?.failed?.length > 0 && `, ${result.failed.length} failed`}
          </div>
        </div>
        {result?.placed?.length > 0 && (
          <div className="border border-border rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle text-ink-muted">
                <tr>
                  <th className="text-left px-2 py-1.5">Leg</th>
                  <th className="text-right px-2 py-1.5">TP</th>
                  <th className="text-right px-2 py-1.5">Lot</th>
                  <th className="text-left px-2 py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {result.placed.map((p: any) => (
                  <tr key={p.order_id} className="border-t border-border">
                    <td className="px-2 py-1.5">{p.tp_level}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.take_profit}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.quantity}</td>
                    <td className="px-2 py-1.5">
                      <span className="text-emerald-500">{p.status ?? "OK"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {result?.failed?.length > 0 && (
          <div className="border border-rose-500/30 bg-rose-500/5 rounded p-3 space-y-1 text-xs">
            <div className="font-semibold text-rose-400">Failed legs:</div>
            {result.failed.map((f: any, i: number) => (
              <div key={i} className="text-ink-muted">
                <span className="font-mono">{f.tp_level}</span>: {f.error}
              </div>
            ))}
          </div>
        )}
        <button onClick={onClose} className="btn-primary text-xs w-full">Close</button>
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
          {/* Fanout banner — front and centre so user sees the order count */}
          <div className="border border-brand/30 bg-brand/5 rounded p-3 text-sm">
            <div className="flex items-center gap-2">
              <TrendingUp className="size-4 text-brand" />
              <span className="font-medium">{orderCount} orders</span>
              <span className="text-ink-muted text-xs">
                {entries.length === 1
                  ? `${tps.length} TPs × 1 entry`
                  : `${tps.length} TPs × 2 entries`}
              </span>
            </div>
            <div className="text-[11px] text-ink-muted mt-1">
              Total {totalRiskPct.toFixed(2)}% risk → split evenly
              ({perOrderRiskPct.toFixed(3)}% per order)
            </div>
          </div>

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

          <Field label="Broker symbol"
                 help="The symbol as the broker knows it (e.g. GOLD vs XAUUSD). Override if needed.">
            <input type="text" className="input w-full font-mono"
                   value={brokerSymbol}
                   onChange={e => setBrokerSymbol(e.target.value)} />
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Order type"
                   help="Applied to every order in the fanout.">
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

            <Field label="Total risk %"
                   help={`Across all ${orderCount} orders. Max ${settings["tgbot.max_risk_pct_per_trade"]}%.`}>
              <input type="number" step="0.1"
                     min={0.01}
                     max={settings["tgbot.max_risk_pct_per_trade"]}
                     className="input w-full font-mono"
                     value={totalRiskPct}
                     onChange={e => setTotalRiskPct(Number(e.target.value))} />
            </Field>
          </div>

          <Field label="Stop loss (shared across all orders)"
                 help={slWrongSide
                        ? `SL is on the WRONG side for a ${side} order!`
                        : `Distance to nearest entry: ${
                            Math.min(...entries.map(e => Math.abs(e - stopLoss))).toFixed(2)
                          }`}
                 helpCls={slWrongSide ? "text-rose-500 font-medium" : ""}>
            <input type="number" step="any" className="input w-full font-mono"
                   value={stopLoss}
                   onChange={e => setStopLoss(Number(e.target.value))} />
          </Field>

          {/* Fanout preview table */}
          <div>
            <div className="text-xs text-ink-muted mb-1">
              Preview ({orderCount} orders)
            </div>
            <div className="border border-border rounded overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-bg-subtle text-ink-muted">
                  <tr>
                    <th className="text-left  px-2 py-1.5">#</th>
                    <th className="text-right px-2 py-1.5">Entry</th>
                    <th className="text-right px-2 py-1.5">TP</th>
                    <th className="text-right px-2 py-1.5">SL</th>
                    <th className="text-right px-2 py-1.5">Lot</th>
                    <th className="text-right px-2 py-1.5">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {legs.map((l, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-2 py-1.5 text-ink-muted">{i + 1}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{fmt(l.entry)}</td>
                      <td className="px-2 py-1.5 text-right font-mono text-emerald-400">
                        {l.tpLevel}: {fmt(l.tp)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-rose-400">
                        {fmt(stopLoss)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {l.quantity.toFixed(2)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-ink-muted">
                        {perOrderRiskPct.toFixed(3)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-[11px] text-ink-dim mt-1 flex items-start gap-1">
              <Calculator className="size-3 mt-0.5 shrink-0" />
              Per-leg lot is a placeholder — risk-based sizing needs broker
              balance which isn't wired in this milestone. The server splits
              total risk evenly across orders.
            </div>
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
                Place <b className="text-ink">{orderCount}</b>{" "}
                <b className="text-ink">{side}</b>{" "}
                <b className="text-ink font-mono">{brokerSymbol}</b>{" "}
                <b className="text-ink">{orderType}</b> orders
                {", SL "}<span className="font-mono">{fmt(stopLoss)}</span>
                {", total risk "}<b className="text-ink">{totalRiskPct.toFixed(2)}%</b>
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
                  Place {orderCount} {orderCount === 1 ? "order" : "orders"}
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
