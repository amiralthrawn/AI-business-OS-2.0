"use client";

import { useState } from "react";

export interface SparkPoint {
  label: string; // the period, e.g. "mars 2026"
  value: number;
  display?: string; // formatted value for the tooltip
  note?: string; // e.g. "mois en cours, partiel"
}

// A small, honest trend line under an indicator. Only real points are drawn
// (callers pass real series -- see lib/series.ts; nothing is interpolated or
// extrapolated). Hover (or focus) shows the value and its period; the line
// draws in on mount unless the user prefers reduced motion (globals.css).
// Legacy `points: number[]` still renders a static direction-only line.
export default function Sparkline({
  points,
  series,
  tone = "text-text-soft",
  width = 74,
  height = 26,
  ariaLabel,
}: {
  points?: number[];
  series?: SparkPoint[];
  tone?: string;
  width?: number;
  height?: number;
  ariaLabel?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const data: SparkPoint[] = series ?? (points ?? []).map((v) => ({ label: "", value: v }));
  if (data.length < 2) return null;

  const values = data.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const xy = data.map((p, i) => ({ x: i * step, y: height - ((p.value - min) / range) * (height - 6) - 3 }));
  const d = `M ${xy.map((c) => `${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" L ")}`;
  const interactive = Boolean(series);
  const h = hover !== null ? data[hover] : null;

  return (
    <div className="relative inline-block" onMouseLeave={() => setHover(null)}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={`${tone} overflow-visible`}
        fill="none"
        role="img"
        aria-label={ariaLabel}
        onMouseMove={(e) => {
          if (!interactive) return;
          const box = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - box.left) / box.width) * (data.length - 1));
          setHover(Math.max(0, Math.min(data.length - 1, i)));
        }}
      >
        <path d={d} pathLength={1} className="animate-chart-draw" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity={hover !== null ? 0.55 : 1} />
        {interactive && <circle cx={xy[xy.length - 1].x} cy={xy[xy.length - 1].y} r={2.2} fill="currentColor" />}
        {hover !== null && (
          <>
            <line x1={xy[hover].x} x2={xy[hover].x} y1={0} y2={height} stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" opacity={0.5} />
            <circle cx={xy[hover].x} cy={xy[hover].y} r={3.4} fill="var(--color-surface)" stroke="currentColor" strokeWidth="2" />
          </>
        )}
      </svg>
      {h && (
        <div
          className="animate-pop pointer-events-none absolute top-full z-20 mt-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11.5px] shadow-card"
          style={{ left: xy[hover!].x }}
        >
          <p className="text-text-faint">{h.label}</p>
          <p className="num font-semibold text-text">{h.display ?? h.value}</p>
          {h.note && <p className="text-[10.5px] text-text-faint">{h.note}</p>}
        </div>
      )}
    </div>
  );
}
