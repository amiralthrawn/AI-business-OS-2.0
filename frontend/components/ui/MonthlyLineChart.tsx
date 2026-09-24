"use client";

import { useMemo, useState } from "react";
import { formatEUR, formatMonthFR } from "@/lib/labels";
import type { MonthlyPoint } from "@/lib/types";

export interface ChartSeries {
  key: string;
  label: string;
  color: string; // CSS color value, e.g. "var(--color-accent)"
  points: MonthlyPoint[];
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD_X = 8;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

// A real, animated, interactive 12-month chart (Step 29 point 11) -- built
// with plain SVG rather than a new charting dependency, since one line/area
// series is all this needs. Every point comes straight from a real,
// zero-filled MonthlyPoint (see app.core.analytics.compute_monthly_series):
// a month with no data draws as zero, never omitted or interpolated.
export default function MonthlyLineChart({ series, onMonthClick }: { series: ChartSeries[]; onMonthClick?: (month: string) => void }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [pinnedIdx, setPinnedIdx] = useState<number | null>(null);

  const months = series[0]?.points.map((p) => p.month) ?? [];
  const count = months.length;

  const { xFor, yFor, zeroY, hasNegative } = useMemo(() => {
    const allValues = series.flatMap((s) => s.points.map((p) => p.total_amount));
    const min = Math.min(...allValues, 0);
    const max = Math.max(...allValues, 0, 1);
    const range = max - min || 1;
    const innerWidth = WIDTH - PAD_X * 2;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    const step = count > 1 ? innerWidth / (count - 1) : 0;
    const yFor = (v: number) => PAD_TOP + innerHeight - ((v - min) / range) * innerHeight;
    return {
      xFor: (i: number) => PAD_X + i * step,
      yFor,
      zeroY: yFor(0),
      hasNegative: min < 0,
    };
  }, [series, count]);

  if (count === 0) return null;

  const activeIdx = hoverIdx ?? pinnedIdx;

  function pathFor(points: MonthlyPoint[]): string {
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(1)} ${yFor(p.total_amount).toFixed(1)}`).join(" ");
  }

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const innerWidth = WIDTH - PAD_X * 2;
    const step = count > 1 ? innerWidth / (count - 1) : innerWidth;
    const idx = Math.max(0, Math.min(count - 1, Math.round((relX - PAD_X) / step)));
    setHoverIdx(idx);
  }

  function handleClick() {
    if (hoverIdx === null) return;
    const next = pinnedIdx === hoverIdx ? null : hoverIdx;
    setPinnedIdx(next);
    if (next !== null) onMonthClick?.(months[next]);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 text-[12px] font-medium text-text-soft">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </div>
        ))}
      </div>

      <div className="relative mt-3">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full cursor-pointer"
          onMouseMove={handleMove}
          onMouseLeave={() => setHoverIdx(null)}
          onClick={handleClick}
        >
          {hasNegative && (
            <line x1={PAD_X} x2={WIDTH - PAD_X} y1={zeroY} y2={zeroY} stroke="var(--color-border-strong)" strokeWidth="1" />
          )}

          {activeIdx !== null && (
            <line x1={xFor(activeIdx)} x2={xFor(activeIdx)} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM} stroke="var(--color-border-strong)" strokeWidth="1" strokeDasharray="3 3" />
          )}

          {series.map((s, si) => (
            <path
              key={s.key}
              d={pathFor(s.points)}
              fill="none"
              stroke={s.color}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              pathLength={1}
              className="animate-chart-draw"
              style={{ animationDelay: `${si * 0.15}s` }}
            />
          ))}

          {series.map((s) =>
            s.points.map((p, i) => (
              <circle
                key={`${s.key}-${i}`}
                cx={xFor(i)}
                cy={yFor(p.total_amount)}
                r={activeIdx === i ? 4.5 : 3}
                fill={s.color}
                className="transition-all"
              />
            ))
          )}

          {months.map((m, i) => (
            <text
              className="num"
              key={m}
              x={xFor(i)}
              y={HEIGHT - 8}
              textAnchor="middle"
              fill="var(--color-text-faint)"
              style={{ fontSize: 9.5 }}
            >
              {formatMonthFR(m).split(" ")[0]}
            </text>
          ))}
        </svg>

        {activeIdx !== null && (
          <div
            className="animate-pop pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-xl border border-border-strong bg-surface px-3 py-2 text-[12px] shadow-card"
            style={{ left: `${(xFor(activeIdx) / WIDTH) * 100}%` }}
          >
            <p className="font-semibold text-text">{formatMonthFR(months[activeIdx], false)}</p>
            {series.map((s) => (
              <p key={s.key} className="mt-0.5 flex items-center gap-1.5 text-text-soft">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s.color }} />
                {s.label}&nbsp;: <span className="font-mono font-medium text-text">{formatEUR(s.points[activeIdx].total_amount)}</span>
              </p>
            ))}
          </div>
        )}
      </div>

      {pinnedIdx !== null && (
        <div className="animate-reveal mt-4 rounded-xl border border-border bg-surface-alt p-4">
          <p className="text-[12.5px] font-semibold text-text">{formatMonthFR(months[pinnedIdx], false)}</p>
          <div className="mt-1.5 flex flex-wrap gap-x-6 gap-y-1 text-[12.5px] text-text-soft">
            {series.map((s) => (
              <span key={s.key}>
                {s.label}&nbsp;: <span className="font-mono font-medium text-text">{formatEUR(s.points[pinnedIdx].total_amount)}</span>{" "}
                ({s.points[pinnedIdx].transaction_count} transaction{s.points[pinnedIdx].transaction_count !== 1 ? "s" : ""})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
