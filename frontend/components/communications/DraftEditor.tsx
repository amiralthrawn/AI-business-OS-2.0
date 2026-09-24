"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { submitDraft, updateDraft } from "@/lib/api";
import type { CommunicationDetail } from "@/lib/types";

const field = "w-full rounded-xl border-[1.5px] border-border-strong px-4 py-2.5 text-[13.5px] outline-none focus:border-accent";

// AI draft -> human edits -> submit for validation -> (approval in Actions) -> send.
// The mock email provider records the message as sent; nothing leaves the
// machine in this MVP, and the UI says so.
export default function DraftEditor({ draft, canWrite, canSubmit }: { draft: CommunicationDetail; canWrite: boolean; canSubmit: boolean }) {
  const router = useRouter();
  const [to, setTo] = useState(draft.to_address ?? "");
  const [subject, setSubject] = useState(draft.subject ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  const [busy, setBusy] = useState<"save" | "submit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const editable = canWrite && (draft.status === "draft" || draft.status === "rejected");

  async function save() {
    setBusy("save");
    setError(null);
    try {
      await updateDraft(draft.id, { to_address: to, subject, body });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    setBusy("submit");
    setError(null);
    try {
      await updateDraft(draft.id, { to_address: to, subject, body });
      const res = await submitDraft(draft.id);
      setTaskId(res.task_id);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge label={draft.status === "pending_validation" ? "En attente de validation" : draft.status === "rejected" ? "Refusé — à reprendre" : draft.status === "sent" ? "Envoyé" : "Brouillon"} tone={draft.status === "pending_validation" ? "warning" : draft.status === "sent" ? "success" : "accent"} />
        {draft.source === "template_draft" && <span className="text-[11.5px] text-text-faint">Préparé à partir des données de l&rsquo;objet lié (aucun modèle de langage configuré).</span>}
        {draft.source === "ai_draft" && <span className="text-[11.5px] text-text-faint">Reformulé par le modèle de langage sans ajout de fait.</span>}
      </div>
      <input className={field} value={to} onChange={(e) => setTo(e.target.value)} disabled={!editable} placeholder="Destinataire (email)" />
      <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!editable} placeholder="Objet" />
      <textarea className={`${field} min-h-[260px] font-[inherit] leading-relaxed`} value={body} onChange={(e) => setBody(e.target.value)} disabled={!editable} />
      {editable && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" loading={busy === "save"} disabled={busy !== null} onClick={save}>Enregistrer</Button>
          <Button loading={busy === "submit"} disabled={busy !== null || !canSubmit || !to.trim()} onClick={submit} title={canSubmit ? undefined : "Votre rôle ne permet pas de soumettre un email"}>
            Soumettre à validation
          </Button>
          <span className="text-[11.5px] text-text-faint">Rien n&rsquo;est envoyé avant validation humaine. Envoi simulé (fournisseur email de démonstration).</span>
        </div>
      )}
      {(draft.status === "pending_validation" || taskId) && (
        <p className="text-[12.5px] text-text-soft">
          En attente de validation dans <Link href="/actions/tasks" className="font-semibold text-accent-strong hover:underline">Actions → Tâches</Link> par une personne habilitée.
        </p>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
    </Card>
  );
}
