"use client";

import { useState } from "react";

export interface RangeBar {
  label: string; // e.g. "Dans 30 jours"
  low: number;
  high: number;
  display: string; // formatted range, e.g. "12 000 – 18 000 €"
  note?: string;
}

// Horizontal low→high bars on one shared scale, to compare RANGES without
// collapsing them to a midpoint (brain/design.md). An optional reference line
// (e.g. the declared minimum cash) is drawn across every bar. Hover/focus
// highlights a bar and shows its exact range.
export default function RangeBars({ bars, reference, referenceLabel }: { bars: RangeBar[]; reference?: number | null; referenceLabel?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (bars.length === 0) return null;
  const values = bars.flatMap((b) => [b.low, b.high]).concat(reference ?? [], 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pct = (v: number) => ((v - min) / span) * 100;

  return (
    <div className="space-y-2.5" onMouseLeave={() => setHover(null)}>
      {bars.map((b, i) => {
        const active = hover === i;
        return (
          <div
            key={b.label}
            tabIndex={0}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            className="grid grid-cols-[92px_1fr] items-center gap-3 outline-none sm:grid-cols-[110px_1fr_170px]"
          >
            <span className={`text-[12px] ${active ? "text-text" : "text-text-soft"}`}>{b.label}</span>
            <div className="relative h-[18px] rounded-full bg-surface-sunken">
              {min < 0 && <span className="absolute inset-y-0 w-px bg-border-strong" style={{ left: `${pct(0)}%` }} />}
              <span
                className={`animate-reveal absolute inset-y-[3px] rounded-full transition-opacity ${b.low < (reference ?? -Infinity) ? "bg-danger" : "bg-accent"} ${hover === null || active ? "opacity-90" : "opacity-35"}`}
                style={{ left: `${pct(b.low)}%`, width: `max(${pct(b.high) - pct(b.low)}%, 6px)`, animationDelay: `${i * 90}ms` }}
              />
              {reference != null && (
                <span className="absolute -inset-y-1 w-0 border-l-[1.5px] border-dashed border-warning" style={{ left: `${pct(reference)}%` }} title={referenceLabel} />
              )}
              {active && (
                <div className="animate-pop pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11.5px] shadow-card sm:hidden">
                  <p className="num font-semibold text-text">{b.display}</p>
                </div>
              )}
            </div>
            <span className={`num hidden text-right text-[12.5px] sm:block ${active ? "font-semibold text-text" : "text-text-soft"}`}>{b.display}</span>
            {active && b.note && <p className="col-span-full -mt-1 text-[11.5px] text-text-faint sm:col-start-2">{b.note}</p>}
          </div>
        );
      })}
      {reference != null && referenceLabel && (
        <p className="flex items-center gap-2 text-[11.5px] text-text-faint">
          <span className="inline-block h-3 w-0 border-l-[1.5px] border-dashed border-warning" /> {referenceLabel}
        </p>
      )}
    </div>
  );
}
