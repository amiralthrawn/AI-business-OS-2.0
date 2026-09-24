import type { SupplierCandidate } from "@/lib/types";
import { fmtMoneyRange, fmtDaysRange } from "@/lib/objects";

// Total cost (x) vs lead time (y), each drawn as a RANGE (a cross of error
// bars) rather than a point pretending to be exact. Lower-left is better; the
// recommended supplier is highlighted. Suppliers with an unknown cost or lead
// time are listed under the chart instead of being placed arbitrarily.
export default function BenchmarkChart({ candidates }: { candidates: SupplierCandidate[] }) {
  const plotted = candidates.filter((c) => c.total_cost.min !== null && c.lead_time_days.min !== null);
  const missing = candidates.filter((c) => !plotted.includes(c));
  if (plotted.length === 0) {
    return <p className="text-[12.5px] text-text-faint">Pas assez de données chiffrées (coût et délai) pour placer les fournisseurs.</p>;
  }

  const W = 560, H = 260, pad = { l: 56, r: 20, t: 16, b: 40 };
  const xs = plotted.flatMap((c) => [c.total_cost.min!, c.total_cost.max ?? c.total_cost.min!]);
  const ys = plotted.flatMap((c) => [c.lead_time_days.min!, c.lead_time_days.max ?? c.lead_time_days.min!]);
  const [x0, x1] = [Math.min(...xs) * 0.95, Math.max(...xs) * 1.05 || 1];
  const [y0, y1] = [Math.max(0, Math.min(...ys) - 2), Math.max(...ys) + 2];
  const sx = (v: number) => pad.l + ((v - x0) / (x1 - x0 || 1)) * (W - pad.l - pad.r);
  const sy = (v: number) => H - pad.b - ((v - y0) / (y1 - y0 || 1)) * (H - pad.t - pad.b);

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Comparaison coût total / délai des fournisseurs">
        <line x1={pad.l} y1={H - pad.b} x2={W - pad.r} y2={H - pad.b} stroke="var(--color-border-strong)" />
        <line x1={pad.l} y1={pad.t} x2={pad.l} y2={H - pad.b} stroke="var(--color-border-strong)" />
        <text x={(W + pad.l) / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--color-text-faint)">Coût total pour la quantité (€) →</text>
        <text x={14} y={(H - pad.b) / 2} textAnchor="middle" fontSize="11" fill="var(--color-text-faint)" transform={`rotate(-90 14 ${(H - pad.b) / 2})`}>Délai (jours) →</text>
        <text className="num" x={pad.l} y={H - pad.b + 14} fontSize="10" fill="var(--color-text-faint)">{Math.round(x0).toLocaleString("fr-FR")}</text>
        <text className="num" x={W - pad.r} y={H - pad.b + 14} fontSize="10" textAnchor="end" fill="var(--color-text-faint)">{Math.round(x1).toLocaleString("fr-FR")}</text>
        <text className="num" x={pad.l - 6} y={H - pad.b} fontSize="10" textAnchor="end" fill="var(--color-text-faint)">{Math.round(y0)}</text>
        <text className="num" x={pad.l - 6} y={pad.t + 8} fontSize="10" textAnchor="end" fill="var(--color-text-faint)">{Math.round(y1)}</text>
        {plotted.map((c) => {
          const cxMin = sx(c.total_cost.min!), cxMax = sx(c.total_cost.max ?? c.total_cost.min!);
          const cyMin = sy(c.lead_time_days.min!), cyMax = sy(c.lead_time_days.max ?? c.lead_time_days.min!);
          const cx = (cxMin + cxMax) / 2, cy = (cyMin + cyMax) / 2;
          const color = c.recommended ? "var(--color-accent)" : "var(--color-text-soft)";
          const dashed = c.lead_time_days.basis !== "declared" && c.lead_time_days.basis !== "observed";
          return (
            <g key={c.supplier_id}>
              <line x1={cxMin} y1={cy} x2={cxMax} y2={cy} stroke={color} strokeWidth={2} strokeDasharray={c.total_cost.basis === "estimated" ? "4 3" : undefined} />
              <line x1={cx} y1={cyMin} x2={cx} y2={cyMax} stroke={color} strokeWidth={2} strokeDasharray={dashed ? "4 3" : undefined} />
              <circle cx={cx} cy={cy} r={c.recommended ? 7 : 5} fill={c.recommended ? "var(--color-accent)" : "var(--color-surface)"} stroke={color} strokeWidth={2} />
              <text x={cx + 10} y={cy - 8} fontSize="11.5" fontWeight={c.recommended ? 700 : 500} fill="var(--color-text)">
                {c.supplier_name}{c.recommended ? " ★" : ""}
              </text>
              <title>{`${c.supplier_name} — ${fmtMoneyRange(c.total_cost.min, c.total_cost.max)}, ${fmtDaysRange(c.lead_time_days.min, c.lead_time_days.max)}`}</title>
            </g>
          );
        })}
      </svg>
      <p className="mt-1 text-[11.5px] text-text-faint">
        Barres = fourchettes (pointillés : estimation). En bas à gauche = moins cher et plus rapide. ★ = recommandé.
        {missing.length > 0 && ` Non placés (coût ou délai inconnu) : ${missing.map((m) => m.supplier_name).join(", ")}.`}
      </p>
    </div>
  );
}
