"use client";

import { useState } from "react";

export interface DonutSlice {
  label: string;
  value: number; // share, any unit; slices are normalised to their total
  display: string; // formatted, e.g. "42,0 %"
  href?: string;
}

const PALETTE = ["var(--color-accent)", "#8f86e6", "#c4bff2", "var(--color-warning)", "var(--color-success)", "#b9b3a6"];

// A distribution (parts of one whole) -- only used where the whole is real,
// e.g. the cap table. Hover a slice or its legend row to highlight it.
export default function Donut({ slices, centerLabel }: { slices: DonutSlice[]; centerLabel?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const total = slices.reduce((s, x) => s + Math.max(0, x.value), 0);
  if (total <= 0 || slices.length < 2) return null;
  const R = 42;
  const C = 2 * Math.PI * R;
  const lens = slices.map((s) => (Math.max(0, s.value) / total) * C);
  const arcs = lens.map((len, i) => ({ len, offset: lens.slice(0, i).reduce((a, b) => a + b, 0) }));
  const h = hover !== null ? slices[hover] : null;

  return (
    <div className="flex flex-wrap items-center gap-6" onMouseLeave={() => setHover(null)}>
      <svg width={120} height={120} viewBox="0 0 120 120" className="animate-pop shrink-0" role="img" aria-label={centerLabel}>
        <g transform="rotate(-90 60 60)">
          {arcs.map((a, i) => (
            <circle
              key={slices[i].label}
              cx={60}
              cy={60}
              r={R}
              fill="none"
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={hover === i ? 18 : 14}
              strokeDasharray={`${Math.max(a.len - 1.5, 0.5)} ${C}`}
              strokeDashoffset={-a.offset}
              opacity={hover === null || hover === i ? 1 : 0.35}
              className="cursor-default transition-all duration-200"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </g>
        <text x={60} y={57} textAnchor="middle" className="num" fontSize="13" fontWeight={600} fill="var(--color-text)">
          {h ? h.display : slices.length}
        </text>
        <text x={60} y={72} textAnchor="middle" fontSize="9.5" fill="var(--color-text-faint)">
          {h ? "" : centerLabel ?? ""}
        </text>
      </svg>
      <ul className="min-w-[180px] flex-1 space-y-1 text-[12.5px]">
        {slices.map((s, i) => (
          <li
            key={s.label}
            onMouseEnter={() => setHover(i)}
            className={`flex items-center gap-2 rounded-md px-1.5 py-0.5 transition-colors ${hover === i ? "bg-surface-sunken" : ""}`}
          >
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="flex-1 truncate text-text">{s.label}</span>
            <span className="num text-text-soft">{s.display}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
