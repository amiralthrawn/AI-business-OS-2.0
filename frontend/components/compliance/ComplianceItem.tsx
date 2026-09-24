"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import BasisBadge from "@/components/objects/BasisBadge";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { askExpert, createComplianceRequest, getComplianceRecommendation } from "@/lib/api";
import { fmtDate, fmtMoneyRange } from "@/lib/objects";
import type { ComplianceRecommendation, ComplianceRequest, ValueBasis } from "@/lib/types";

// One compliance matter: request -> analysis -> recommendation -> action.
// Asking an expert prepares a draft email (validated before sending);
// nothing is ordered or paid.
export default function ComplianceItem({ item, canWrite }: { item: ComplianceRequest; canWrite: boolean }) {
  const router = useRouter();
  const [reco, setReco] = useState<ComplianceRecommendation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function analyse() {
    setBusy("reco");
    try {
      setReco(await getComplianceRecommendation(item.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-semibold text-text">{item.title}</span>
        <Badge label={item.category_label} tone="accent" />
        {item.overdue && <Badge label="Échéance dépassée" tone="danger" />}
        {!item.open && <Badge label="Clos" tone="neutral" />}
        <span className="ml-auto text-[12px] text-text-faint">échéance <span className="num">{fmtDate(item.due_at)}</span></span>
      </div>
      {item.description && <p className="mt-1.5 text-[13px] text-text-soft">{item.description}</p>}
      <p className="mt-1 text-[12px] text-text-faint">
        Liés : {item.linked.commercial_document ?? 0} document(s) commercial(aux), {item.linked.communication ?? 0} message(s) ·{" "}
        <Link href={`/actions/tasks?task=${item.id}`} className="text-accent-strong hover:underline">voir la tâche</Link>
      </p>
      {item.open && !reco && (
        <Button variant="ghost" className="mt-3" loading={busy === "reco"} onClick={analyse}>
          Analyser la demande
        </Button>
      )}
      {reco && (
        <div className="mt-4 rounded-xl bg-surface-alt px-4 py-3 text-[13px]">
          <p className="text-text">{reco.statement}</p>
          {reco.options.map((o) => (
            <div key={o.supplier_id} className="mt-2 flex flex-wrap items-center gap-2">
              <Link href={`/data/suppliers/${o.supplier_id}`} className="font-medium text-text hover:underline">{o.name}</Link>
              <span>Honoraires estimés : <span className="num">{o.fee_min !== null ? fmtMoneyRange(o.fee_min, o.fee_max) : "non estimables"}</span></span>
              <BasisBadge basis={o.basis as ValueBasis} confidence={o.confidence} />
              {canWrite && (
                <Button
                  variant="ghost"
                  loading={busy === o.supplier_id}
                  disabled={!o.has_contact || busy !== null}
                  title={o.has_contact ? "Brouillon envoyé seulement après validation" : "Aucun contact email pour ce cabinet"}
                  onClick={async () => {
                    setBusy(o.supplier_id);
                    try {
                      const { draft_id } = await askExpert(item.id, o.supplier_id);
                      router.push(`/communications?tab=drafts&message=${draft_id}`);
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Erreur");
                      setBusy(null);
                    }
                  }}
                >
                  Préparer la demande d&rsquo;intervention
                </Button>
              )}
            </div>
          ))}
          {reco.note && <p className="mt-2 text-[11.5px] text-text-faint">{reco.note}</p>}
        </div>
      )}
      {error && <p className="mt-2 text-[12.5px] text-danger">{error}</p>}
    </Card>
  );
}

export function NewComplianceRequest({ categories }: { categories: Record<string, string> }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("contract_review");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const field = "rounded-xl border-[1.5px] border-border-strong px-3 py-2 text-[13px] outline-none focus:border-accent";
  return (
    <Card className="space-y-2 p-5">
      <p className="text-[13px] font-semibold text-text">Nouvelle demande</p>
      <div className="flex flex-wrap gap-2">
        <input className={`${field} flex-1`} placeholder="Objet (ex. Revoir le contrat fournisseur)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <select className={field} value={category} onChange={(e) => setCategory(e.target.value)}>
          {Object.entries(categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <textarea className={`${field} w-full`} rows={2} placeholder="Contexte" value={description} onChange={(e) => setDescription(e.target.value)} />
      <Button
        disabled={!title.trim()}
        onClick={async () => {
          await createComplianceRequest({ title: title.trim(), category, description: description || undefined, due_at: due ? new Date(due).toISOString() : undefined });
          setTitle("");
          setDescription("");
          router.refresh();
        }}
      >
        Créer la demande
      </Button>
    </Card>
  );
}
