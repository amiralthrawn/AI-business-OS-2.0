"use client";

import { useEffect, useRef, useState } from "react";

function formatEUR(value: number) {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value) + " %";
}

export default function AnimatedNumber({
  value,
  format = "number",
  durationMs = 1000,
}: {
  value: number;
  format?: "number" | "EUR" | "percent";
  durationMs?: number;
}) {
  const [display, setDisplay] = useState(0);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const reduceMotion = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reduceMotion) {
      frame.current = requestAnimationFrame(() => setDisplay(value));

      return () => {
        if (frame.current !== null) {
          cancelAnimationFrame(frame.current);
        }
      };
    }

    const start = performance.now();

    const tick = (now: number) => {
      // rAF's timestamp can precede `start` on the first frame: clamp so a
      // positive value never flashes as a negative one.
      const t = Math.max(0, Math.min(1, (now - start) / durationMs));
      const eased = 1 - Math.pow(1 - t, 3);

      setDisplay(value * eased);

      if (t < 1) {
        frame.current = requestAnimationFrame(tick);
      }
    };

    frame.current = requestAnimationFrame(tick);

    return () => {
      if (frame.current !== null) {
        cancelAnimationFrame(frame.current);
      }
    };
  }, [value, durationMs]);

  let formatted: string;

  if (format === "EUR") {
    formatted = formatEUR(display);
  } else if (format === "percent") {
    formatted = formatPercent(display);
  } else {
    formatted = new Intl.NumberFormat("fr-FR").format(
      Math.round(display)
    );
  }

  return <>{formatted}</>;
}