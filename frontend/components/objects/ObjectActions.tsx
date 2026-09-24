"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import ObjectPicker from "@/components/objects/ObjectPicker";
import Button from "@/components/ui/Button";
import { changeDocumentStatus, createDraft, deriveDocument } from "@/lib/api";
import type { ObjectAction, ObjectType } from "@/lib/types";

// "What can I do now?" -- the actions the contextual API offers for this
// object, already filtered by role server-side (a refused action stays
// visible, disabled, with its reason: the user knows it exists and why not).
export default function ObjectActions({ objectType, objectId, actions }: { objectType: ObjectType; objectId: string; actions: ObjectAction[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pickingSupplierFor, setPickingSupplierFor] = useState<ObjectAction | null>(null);

  const primary = actions.filter((a) => a.kind === "derive" || a.kind === "create" || a.kind === "navigate");
  const statuses = actions.filter((a) => a.kind === "status");
  const emails = actions.filter((a) => a.kind === "email");

  async function run(action: ObjectAction, supplierId?: string) {
    setError(null);
    if (action.kind === "derive" && action.params.needs_supplier && !supplierId) {
      setPickingSupplierFor(action);
      return;
    }
    setBusy(action.key);
    try {
      if (action.kind === "status") {
        await changeDocumentStatus(objectId, String(action.params.status));
        router.refresh();
      } else if (action.kind === "derive") {
        const doc = await deriveDocument(objectId, action.params.kind as never, supplierId);
        router.push(`/documents/${doc.id}`);
      } else if (action.kind === "email") {
        const draft = await createDraft({ purpose: String(action.params.purpose), object_type: objectType, object_id: objectId });
        router.push(`/communications?tab=drafts&message=${draft.id}`);
      } else if (action.kind === "create") {
        const params = new URLSearchParams(Object.entries(action.params).map(([k, v]) => [k, String(v)]));
        if (objectType === "supplier") params.set("supplier_id", objectId);
        router.push(`/documents/new?${params.toString()}`);
      } else if (action.kind === "navigate") {
        document.getElementById(String(action.params.anchor))?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(null);
    }
  }

  if (actions.length === 0) return null;

  const button = (a: ObjectAction, variant: "primary" | "ghost") => (
    <Button key={a.key} variant={variant} loading={busy === a.key} disabled={!a.allowed || (busy !== null && busy !== a.key)} title={a.reason ?? undefined} onClick={() => run(a)}>
      {a.label}
    </Button>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {primary.map((a) => button(a, "primary"))}
        {statuses.map((a) => button(a, "ghost"))}
      </div>
      {emails.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11.5px] font-semibold text-text-faint">Préparer avec l&rsquo;IA :</span>
          {emails.map((a) => (
            <button
              key={a.key}
              type="button"
              disabled={!a.allowed || busy !== null}
              title={a.reason ?? "Brouillon préparé, envoyé seulement après validation humaine"}
              onClick={() => run(a)}
              className="rounded-lg border border-border bg-surface-alt px-2.5 py-1.5 text-[12.5px] text-text-soft transition-colors hover:border-border-strong hover:text-text disabled:opacity-50"
            >
              ✉ {a.label}
            </button>
          ))}
        </div>
      )}
      {pickingSupplierFor && (
        <div className="max-w-md rounded-xl border-[1.5px] border-border-strong bg-surface p-4">
          <p className="mb-2 text-[12.5px] font-medium text-text-soft">{pickingSupplierFor.label} — choisir le fournisseur :</p>
          <ObjectPicker types={["supplier"]} placeholder="Nom du fournisseur…" autoFocus onPick={(s) => { const a = pickingSupplierFor; setPickingSupplierFor(null); run(a, s.id); }} />
          <button type="button" onClick={() => setPickingSupplierFor(null)} className="mt-2 text-[12px] text-text-faint hover:text-text">
            Annuler
          </button>
        </div>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </div>
  );
}
