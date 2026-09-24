"use client";

import { useEffect, useState } from "react";
import { searchObjects } from "@/lib/api";
import type { ObjectSummary, ObjectType } from "@/lib/types";

// One search box for every "pick an existing object" need (customer or
// product while quoting, supplier to consult, object to link an email to),
// backed by GET /objects/search.
export default function ObjectPicker({
  types,
  placeholder = "Rechercher…",
  onPick,
  autoFocus = false,
}: {
  types: ObjectType[];
  placeholder?: string;
  onPick: (item: ObjectSummary) => void;
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ObjectSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const typesKey = types.join(",");

  useEffect(() => {
    if (q.trim().length < 1) return;
    let cancelled = false;
    const handle = setTimeout(async () => {
      setLoading(true);
      try {
        const found = await searchObjects(q.trim(), typesKey.split(",") as ObjectType[]);
        if (!cancelled) setResults(found);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [q, typesKey]);

  const shown = q.trim() ? results : [];

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="w-full rounded-lg border-[1.5px] border-border-strong px-3 py-2 text-[13.5px] outline-none focus:border-accent"
      />
      {q.trim() && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-xl border border-border bg-surface shadow-card">
          {loading && shown.length === 0 && <li className="px-3 py-2 text-[12.5px] text-text-faint">Recherche…</li>}
          {!loading && shown.length === 0 && <li className="px-3 py-2 text-[12.5px] text-text-faint">Aucun résultat.</li>}
          {shown.map((item) => (
            <li key={`${item.type}-${item.id}`}>
              <button
                type="button"
                onClick={() => {
                  onPick(item);
                  setQ("");
                  setResults([]);
                }}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-[13px] hover:bg-surface-sunken"
              >
                <span className="truncate text-text">{item.title}</span>
                <span className="shrink-0 text-[11px] text-text-faint">{item.kind_label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
