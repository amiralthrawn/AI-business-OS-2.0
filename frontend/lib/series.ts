import type { SparkPoint } from "@/components/ui/Sparkline";
import { formatEUR, formatMonthFR } from "@/lib/labels";
import type { MonthlyPoint } from "@/lib/types";

// Real monthly series -> chart points, honestly (brain/design.md "Charts").
// The backend zero-fills the last 12 calendar months and its LAST point is the
// current, still-open month. Months before the first recorded transaction are
// not history, only absence of data: they are dropped rather than drawn as
// zeros. Too few real months -> null, and the caller shows no chart.
export const MIN_MONTHS_FOR_TREND = 3;

export function realMonths(points: MonthlyPoint[] | undefined): MonthlyPoint[] {
  if (!points) return [];
  const first = points.findIndex((p) => p.transaction_count > 0);
  return first === -1 ? [] : points.slice(first);
}

// `source` names what is summed (shown in the tooltip), e.g. "commandes clients".
export function monthlySpark(points: MonthlyPoint[] | undefined, source: string): SparkPoint[] | null {
  const real = realMonths(points);
  if (real.length < MIN_MONTHS_FOR_TREND) return null;
  return real.map((p, i) => ({
    label: formatMonthFR(p.month, false),
    value: p.total_amount,
    display: `${formatEUR(p.total_amount)} · ${p.transaction_count} transaction${p.transaction_count !== 1 ? "s" : ""}`,
    note: i === real.length - 1 ? `${source} · mois en cours, partiel` : source,
  }));
}

// Last COMPLETE month vs the one before, both with recorded transactions.
// Returns null when that comparison is not supported by the data.
export function monthOverMonth(points: MonthlyPoint[] | undefined): { pct: number; label: string } | null {
  const real = realMonths(points);
  const complete = real.slice(0, -1);
  if (complete.length < 2) return null;
  const last = complete[complete.length - 1];
  const prev = complete[complete.length - 2];
  if (last.transaction_count === 0 || prev.transaction_count === 0 || prev.total_amount === 0) return null;
  return { pct: (last.total_amount - prev.total_amount) / prev.total_amount, label: `${formatMonthFR(last.month)} vs ${formatMonthFR(prev.month)}` };
}
