import { cn, verdictBadgeClass, verdictLabel } from "@/lib/utils";
import { TrendingUp, Eye, AlertTriangle, Target, ArrowDownCircle, ArrowUpCircle, Scissors, Octagon } from "lucide-react";

const ICONS: Record<string, any> = {
  BUY: TrendingUp, WATCH: Eye, STAY_AWAY: AlertTriangle,
  HOLD: Target, SELL: ArrowDownCircle, BUY_MORE: ArrowUpCircle,
  TRIM: Scissors, STOP_LOSS: Octagon,
};

export default function VerdictBadge({
  verdict, size = "sm", className,
}: { verdict: string | null | undefined; size?: "xs" | "sm" | "md"; className?: string }) {
  const Icon = verdict ? ICONS[verdict] : null;
  const sizeCls = size === "md" ? "text-sm px-2.5 py-1" : size === "xs" ? "text-[10px] px-1.5 py-0.5" : "";
  return (
    <span className={cn(verdictBadgeClass(verdict), sizeCls, className)}>
      {Icon && <Icon className={size === "xs" ? "size-3" : "size-3.5"} />}
      {verdictLabel(verdict)}
    </span>
  );
}
