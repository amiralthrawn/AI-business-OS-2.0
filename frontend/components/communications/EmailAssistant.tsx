"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ObjectPicker from "@/components/objects/ObjectPicker";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { analyzeCommunication, candidateFromEmail, createDocument, createDraft, linkObjects } from "@/lib/api";
import type { CommunicationDetail, EmailAnalysis, ObjectSummary } from "@/lib/types";

const PURPOSES: { key: string; label: string }[] = [
  { key: "reply", label: "Répondre" },
  { key: "follow_up", label: "Relancer" },
  { key: "brochure", label: "Envoyer une brochure" },
  { key: "nda", label: "Proposer un NDA" },
];

// AI assistance on one message: understand it (intents, referenced objects),
// link it to the right business objects, and prepare what comes next. It only
// ever PREPARES -- a draft is sent after human validation, never before.
export default function EmailAssistant({ message, canWrite }: { message: CommunicationDetail; canWrite: boolean }) {
  const router = useRouter();
  const [analysis, setAnalysis] = useState<EmailAnalysis | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(null);
    }
  }

  const link = (target: ObjectSummary, origin: "manual" | "ai_suggested") =>
    run(`link-${target.id}`, async () => {
      await linkObjects({ source_type: "communication", source_id: message.id, target_type: target.type, target_id: target.id, relation: "concerns", origin });
      setAnalysis((a) => (a ? { ...a, suggested_links: a.suggested_links.filter((s) => s.id !== target.id) } : a));
      router.refresh();
    });

  const draft = (purpose: string) =>
    run(`draft-${purpose}`, async () => {
      const created = await createDraft(purpose === "reply" ? { purpose, reply_to_id: message.id } : { purpose, reply_to_id: message.id, object_type: message.party?.type, object_id: message.party?.id });
      router.push(`/communications?tab=drafts&message=${created.id}`);
    });

  const createRequest = () =>
    run("create-request", async () => {
      const doc = await createDocument({
        kind: "customer_request",
        ...(message.party?.type === "customer" ? { customer_id: message.party.id } : { new_customer: { name: message.contact?.name ?? message.from_address ?? "Nouveau prospect", status: "prospect" } }),
        title: message.subject ?? undefined,
        lines: [],
      });
      await linkObjects({ source_type: "communication", source_id: message.id, target_type: "commercial_document", target_id: doc.id, relation: "concerns", origin: "manual" });
      router.push(`/documents/${doc.id}`);
    });

  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-semibold text-text">Assistance IA</p>
        <Button variant="ghost" loading={busy === "analyze"} onClick={() => run("analyze", async () => setAnalysis(await analyzeCommunication(message.id)))}>
          {analysis ? "Réanalyser" : "Analyser le message"}
        </Button>
      </div>

      {analysis && (
        <div className="space-y-3 text-[13px]">
          <p className="rounded-xl bg-surface-alt px-4 py-3 text-text-soft">
            {analysis.summary}
            <span className="mt-1 block text-[11px] text-text-faint">{analysis.generated_by === "rules" ? "Analyse par règles (aucun modèle de langage configuré)." : "Résumé rédigé par le modèle de langage, à partir de règles vérifiables."}</span>
          </p>
          {analysis.intents.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {analysis.intents.map((i) => <Badge key={i.key} label={i.label} tone="accent" />)}
            </div>
          )}
          {analysis.intents.some((i) => i.key === "application") && canWrite && (
            <Button
              variant="ghost"
              loading={busy === "candidate"}
              onClick={() =>
                run("candidate", async () => {
                  const candidate = await candidateFromEmail(message.id);
                  router.push(`/people?tab=recruitment&candidate=${candidate.id}`);
                })
              }
            >
              Créer la fiche candidat
            </Button>
          )}
          {analysis.suggested_links.length > 0 && (
            <div>
              <p className="mb-1.5 text-[12px] font-semibold text-text-soft">Objets probablement concernés</p>
              <ul className="space-y-1.5">
                {analysis.suggested_links.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2">
                    <Link href={s.href ?? "#"} className="text-text hover:underline">{s.title}</Link>
                    <span className="text-[11.5px] text-text-faint">{s.kind_label} · {s.matched}</span>
                    {canWrite && (
                      <button type="button" disabled={busy !== null} onClick={() => link(s, "ai_suggested")} className="text-[12px] font-semibold text-accent-strong hover:underline">
                        Lier
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {canWrite && (
        <>
          <div>
            <p className="mb-1.5 text-[12px] font-semibold text-text-soft">Préparer (brouillon soumis à validation avant envoi)</p>
            <div className="flex flex-wrap gap-2">
              {PURPOSES.map((p) => (
                <Button key={p.key} variant="ghost" loading={busy === `draft-${p.key}`} disabled={busy !== null} onClick={() => draft(p.key)}>
                  {p.label}
                </Button>
              ))}
              {message.direction === "inbound" && (
                <Button variant="ghost" loading={busy === "create-request"} disabled={busy !== null} onClick={createRequest}>
                  Créer une demande client
                </Button>
              )}
            </div>
          </div>
          <div>
            {linking ? (
              <div className="max-w-md">
                <ObjectPicker types={["customer", "supplier", "contact", "product", "commercial_document"]} placeholder="Lier à : client, fournisseur, devis, commande…" autoFocus onPick={(o) => { setLinking(false); link(o, "manual"); }} />
              </div>
            ) : (
              <button type="button" onClick={() => setLinking(true)} className="text-[12.5px] font-medium text-accent-strong hover:underline">
                + Lier ce message à un objet
              </button>
            )}
          </div>
        </>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </Card>
  );
}
