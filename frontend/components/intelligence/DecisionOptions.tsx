"use client";

import { useState } from "react";
import CreateTaskButton from "@/components/actions/CreateTaskButton";
import Badge from "@/components/ui/Badge";
import type { RelatedEntityType } from "@/lib/types";

type Option = { label: string; expected_benefit: string; trade_offs: string };

// The options the Decision engine produced, each one openable to read its
// expected benefit and trade-offs, and turnable into a REAL task. Choosing an
// option is never persisted as if it had been executed.
export default function DecisionOptions({
  options,
  chosen,
  entityType,
  entityId,
}: {
  options: Option[];
  chosen: string | null;
  entityType?: RelatedEntityType | null;
  entityId?: string | null;
}) {
  const recommendedIndex = options.findIndex((o) => chosen?.includes(o.label));
  const [openOption, setOpenOption] = useState<number | null>(recommendedIndex >= 0 ? recommendedIndex : null);

  return (
    <div className="space-y-2">
      {options.map((option, i) => {
        const isOpen = openOption === i;
        const isRecommended = i === recommendedIndex;
        return (
          <div key={i} className={`rounded-xl border-[1.5px] transition-colors ${isOpen ? "border-accent" : "border-border-strong"}`}>
            <button
              type="button"
              onClick={() => setOpenOption(isOpen ? null : i)}
              aria-expanded={isOpen}
              className={`flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left transition-colors ${isOpen ? "bg-accent-soft" : "hover:bg-surface-sunken"}`}
            >
              <span className="flex flex-wrap items-center gap-2 text-[13.5px] font-semibold text-text">
                {option.label}
                {isRecommended && <Badge label="recommandée par l'OS" tone="success" />}
              </span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={`shrink-0 text-text-faint transition-transform ${isOpen ? "rotate-180" : ""}`}>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {isOpen && (
              <div className="animate-reveal space-y-2.5 border-t border-border px-4 py-3.5">
                <p className="text-[12.5px] text-text-soft">
                  <span className="font-semibold text-text">Bénéfice attendu&nbsp;: </span>
                  {option.expected_benefit}
                </p>
                {option.trade_offs && (
                  <p className="text-[12.5px] text-text-faint">
                    <span className="font-semibold text-text-soft">Compromis&nbsp;: </span>
                    {option.trade_offs}
                  </p>
                )}
                <CreateTaskButton defaultTitle={option.label} relatedEntityType={entityType ?? undefined} relatedEntityId={entityId ?? undefined} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
