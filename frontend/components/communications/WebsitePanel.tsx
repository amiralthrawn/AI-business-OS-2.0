"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import AIRunSteps from "@/components/objects/AIRunSteps";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { runWebsiteAudit, setWebsiteUrl, submitWebsiteProposal } from "@/lib/api";
import type { WebsiteIssue, WebsiteState } from "@/lib/types";

const SEVERITY: Record<WebsiteIssue["severity"], { label: string; tone: "danger" | "warning" | "neutral" }> = {
  high: { label: "Important", tone: "danger" },
  medium: { label: "Moyen", tone: "warning" },
  low: { label: "Mineur", tone: "neutral" },
};
const FIELD: Record<string, string> = { title: "Titre", meta_description: "Méta-description", h1: "Titre H1", img_alt: "Texte alternatif" };

// Website intelligence: analyse -> what is wrong / why / what to change ->
// proposed changes shown as a diff -> human approval. The real site is never
// modified from here (no CMS connector): an approved change is ready to apply.
export default function WebsitePanel({ initial, canWrite, canConfigure }: { initial: WebsiteState; canWrite: boolean; canConfigure: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState(initial.website_url ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = initial.run;
  const issues = (run?.result.issues as WebsiteIssue[] | undefined) ?? [];
  const pages = (run?.result.pages as { url: string }[] | undefined) ?? [];

  async function act(key: string, fn: () => Promise<unknown>) {
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
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        {canConfigure && (
          <>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.votre-site.fr" className="w-72 rounded-xl border-[1.5px] border-border-strong px-3 py-2 text-[13px] outline-none focus:border-accent" />
            <Button variant="ghost" disabled={busy !== null} onClick={() => act("url", () => setWebsiteUrl(url.trim() || null))}>Enregistrer le site</Button>
          </>
        )}
        {canWrite && <Button loading={busy === "audit"} disabled={busy !== null} onClick={() => act("audit", runWebsiteAudit)}>{run ? "Relancer l'analyse" : "Analyser le site"}</Button>}
        <span className="text-[12px] text-text-faint">
          {initial.website_url ? `Site analysé : ${initial.website_url}` : "Aucun site configuré : l'analyse porte sur un site de démonstration."} Exploration limitée à 20 pages, robots.txt respecté.
        </span>
      </div>

      {run && <AIRunSteps run={run} title="Analyse du site web" />}

      {issues.length > 0 && (
        <section>
          <SectionLabel>Problèmes détectés ({issues.length}) sur {pages.length} page(s)</SectionLabel>
          <ul className="space-y-2">
            {issues.map((i, n) => (
              <li key={n} className="rounded-xl border border-border bg-surface px-4 py-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge label={SEVERITY[i.severity].label} tone={SEVERITY[i.severity].tone} />
                  <span className="font-medium text-text">{i.what}</span>
                  <span className="ml-auto font-mono text-[11.5px] text-text-faint">{new URL(i.url).pathname}</span>
                </div>
                <p className="mt-1 text-text-soft"><span className="text-text">Pourquoi :</span> {i.why}</p>
                <p className="text-text-soft"><span className="text-text">À changer :</span> {i.change}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {initial.proposals.length > 0 && (
        <section>
          <SectionLabel>Modifications proposées</SectionLabel>
          <div className="space-y-3">
            {initial.proposals.map((p) => (
              <Card key={p.id} className="p-5">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-semibold text-text">{FIELD[p.field] ?? p.field}</span>
                  <span className="font-mono text-[12px] text-text-faint">{new URL(p.page_url).pathname}</span>
                  <Badge
                    label={{ proposed: "Proposée", pending_validation: "En attente de validation", approved: "Approuvée — à appliquer manuellement", rejected: "Refusée" }[p.status] ?? p.status}
                    tone={p.status === "approved" ? "success" : p.status === "pending_validation" ? "warning" : "neutral"}
                  />
                  <span className="text-[11.5px] text-text-faint">généré par {p.generated_by === "rules" ? "règles" : "règles + modèle de langage"}</span>
                </div>
                <div className="mt-3 space-y-1 rounded-xl bg-surface-alt p-3 font-mono text-[12.5px]">
                  <p className="text-danger">− {p.current_value || "(vide)"}</p>
                  <p className="text-success">+ {p.proposed_value}</p>
                </div>
                <p className="mt-2 text-[12px] text-text-soft">{p.rationale}</p>
                {canWrite && (p.status === "proposed" || p.status === "rejected") && (
                  <Button variant="ghost" className="mt-3" loading={busy === p.id} disabled={busy !== null} onClick={() => act(p.id, () => submitWebsiteProposal(p.id))}>
                    Soumettre à validation
                  </Button>
                )}
              </Card>
            ))}
          </div>
          <p className="mt-2 text-[11.5px] text-text-faint">Aucune modification n&rsquo;est appliquée au site réel depuis l&rsquo;OS : sans connecteur CMS, une modification approuvée est à appliquer manuellement.</p>
        </section>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </div>
  );
}
