import Badge from "@/components/ui/Badge";
import { formatDateFR, formatTimeFR } from "@/lib/labels";
import type { AIRunView } from "@/lib/types";

const MODE: Record<AIRunView["mode"], { label: string; tone: "success" | "danger" | "warning" }> = {
  real: { label: "Données réelles", tone: "success" },
  simulated: { label: "Simulation — site/données de démonstration", tone: "danger" },
  partial: { label: "Partiel — une source n'était pas disponible", tone: "warning" },
};

// "What is the AI doing / what did it do": the steps it really executed,
// as recorded by the backend (AIRun) -- never an animated fake progress bar.
export default function AIRunSteps({ run, title }: { run: AIRunView; title: string }) {
  const mode = MODE[run.mode];
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13.5px] font-semibold text-text">{title}</p>
        <div className="flex items-center gap-2">
          <Badge label={mode.label} tone={mode.tone} />
          <span className="font-mono text-[11px] text-text-faint">
            <span className="num">{formatDateFR(run.started_at)} {formatTimeFR(run.started_at)}</span>
          </span>
        </div>
      </div>
      <ol className="mt-3 space-y-1.5">
        {run.steps.map((s, i) => (
          <li key={i} className="flex items-baseline gap-2.5 text-[13px]">
            <span className={s.status === "done" ? "text-success" : s.status === "failed" ? "text-danger" : "text-text-faint"}>
              {s.status === "done" ? "✓" : s.status === "failed" ? "✕" : "–"}
            </span>
            <span className="text-text">{s.label}</span>
            {s.detail && <span className="text-[12px] text-text-faint">{s.detail}</span>}
          </li>
        ))}
        {run.status === "running" && (
          <li className="flex items-center gap-2.5 text-[13px] text-text-soft">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> En cours…
          </li>
        )}
      </ol>
    </div>
  );
}
