"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AIRunSteps from "@/components/objects/AIRunSteps";
import BasisBadge from "@/components/objects/BasisBadge";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { convertLead, discardLead, runSourcing } from "@/lib/api";
import { fmtMoney } from "@/lib/objects";
import type { SourcingState, ValueBasis } from "@/lib/types";

const SOURCE: Record<string, string> = { existing_supplier: "Fournisseur déjà connu", web_search: "Recherche web", manual: "Ajout manuel" };

// AI sourcing on a purchase request: potential suppliers with their
// provenance. A lead becomes a supplier only when a human converts it; it
// then joins the benchmark below as a supplier-quote request.
export default function SourcingPanel({ purchaseRequestId, initial, canAct }: { purchaseRequestId: string; initial: SourcingState; canAct: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <SectionLabel>Sourcing IA</SectionLabel>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          {canAct && (
            <Button loading={busy === "run"} disabled={busy !== null} onClick={() => run("run", async () => { await runSourcing(purchaseRequestId); })}>
              {initial.run ? "Relancer le sourcing" : "Lancer le sourcing"}
            </Button>
          )}
          <span className="text-[12px] text-text-faint">
            {initial.web_search_configured ? "Recherche web activée." : "Recherche web non configurée : seules les données internes sont explorées."} Aucun fournisseur ni prix n&rsquo;est inventé.
          </span>
        </div>
        {initial.run && <AIRunSteps run={initial.run} title="Sourcing fournisseurs" />}
        {initial.leads.length > 0 && (
          <Card className="divide-y divide-border">
            {initial.leads.map((lead) => (
              <div key={lead.id} className="flex flex-wrap items-center gap-3 p-4 text-[13px]">
                <div className="min-w-[220px] flex-1">
                  <p className="font-medium text-text">{lead.name}</p>
                  <p className="text-[12px] text-text-faint">
                    {SOURCE[lead.source_kind] ?? lead.source_kind}
                    {lead.source_url && (
                      <>
                        {" · "}
                        <a href={lead.source_url} target="_blank" rel="noreferrer" className="text-accent-strong hover:underline">source</a>
                      </>
                    )}
                    {lead.snippet ? ` · ${lead.snippet.slice(0, 120)}` : ""}
                  </p>
                </div>
                <span className="flex items-center gap-1.5">
                  <span className="num">{lead.found_price !== null ? fmtMoney(lead.found_price, true) : "Prix inconnu"}</span> <BasisBadge basis={lead.price_basis as ValueBasis} />
                </span>
                {lead.status === "converted" ? (
                  <Badge label="Consulté" tone="success" />
                ) : lead.status === "discarded" ? (
                  <Badge label="Écarté" tone="neutral" />
                ) : (
                  canAct && (
                    <span className="flex gap-2">
                      <Button variant="ghost" loading={busy === lead.id} disabled={busy !== null} onClick={() => run(lead.id, async () => { await convertLead(lead.id); })}>
                        Consulter ce fournisseur
                      </Button>
                      <button type="button" disabled={busy !== null} onClick={() => run(`d${lead.id}`, async () => { await discardLead(lead.id); })} className="text-[12px] text-text-faint hover:text-text">
                        Écarter
                      </button>
                    </span>
                  )
                )}
                {lead.supplier_id && lead.status === "converted" && <Link href={`/data/suppliers/${lead.supplier_id}`} className="text-[12px] text-accent-strong hover:underline">fiche</Link>}
              </div>
            ))}
          </Card>
        )}
        {error && <p className="text-[12.5px] text-danger">{error}</p>}
      </div>
    </section>
  );
}
