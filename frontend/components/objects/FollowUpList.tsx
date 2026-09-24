"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import { createDraft } from "@/lib/api";
import { fmtDate } from "@/lib/objects";
import type { FollowUpItem } from "@/lib/types";

// Everything waiting on someone, computed when the page is opened (no
// scheduler). One click prepares the follow-up; nothing leaves before a
// human validates it.
export default function FollowUpList({ items, note, canDraft }: { items: FollowUpItem[]; note: string; canDraft: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function prepare(item: FollowUpItem) {
    setBusy(item.object.id);
    setError(null);
    try {
      const draft =
        item.object.type === "communication"
          ? await createDraft({ purpose: "reply", reply_to_id: item.object.id })
          : await createDraft({ purpose: item.purpose, object_type: "commercial_document", object_id: item.object.id });
      router.push(`/communications?tab=drafts&message=${draft.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-text-faint">{note}</p>
      {items.length === 0 ? (
        <EmptyState message="Rien à relancer pour l'instant." />
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={`${item.object.type}-${item.object.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-3 text-[13px]">
              <Badge label={item.overdue_days > 0 ? `En retard de ${Math.round(item.overdue_days)} j` : "Bientôt"} tone={item.overdue_days > 0 ? "danger" : "warning"} />
              <span className="text-text-soft">{item.reason}</span>
              <Link href={item.object.href ?? "#"} className="min-w-0 flex-1 truncate font-medium text-text hover:underline">
                {item.object.title}
              </Link>
              {item.party && <span className="text-[12.5px] text-text-faint">{item.party}</span>}
              <span className="text-[11.5px] text-text-faint">échéance <span className="num">{fmtDate(item.due_at)}</span></span>
              <button
                type="button"
                disabled={!canDraft || busy !== null}
                onClick={() => prepare(item)}
                title={canDraft ? "Brouillon préparé par l'IA, envoyé seulement après validation" : "Votre rôle ne permet pas de préparer des emails"}
                className="rounded-lg border-[1.5px] border-border-strong px-3 py-1.5 text-[12.5px] font-semibold text-text hover:border-text-faint disabled:opacity-50"
              >
                {busy === item.object.id ? "Préparation…" : item.object.type === "communication" ? "Préparer la réponse" : "Préparer la relance"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </div>
  );
}
