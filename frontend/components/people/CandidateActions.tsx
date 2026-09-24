"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/ui/Button";
import { candidateFromEmail, createDraft, updateCandidate } from "@/lib/api";

// Candidate actions. "Proposer un entretien" prepares an email draft that
// goes through validation before it is sent -- no meeting is booked here.
export default function CandidateActions(props: { mode: "extract"; communicationId: string } | { mode: "manage"; candidateId: string; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (props.mode === "extract") {
    return (
      <Button variant="ghost" loading={busy === "x"} onClick={() => run("x", async () => { await candidateFromEmail(props.communicationId); router.refresh(); })}>
        Créer la fiche candidat
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        loading={busy === "invite"}
        disabled={busy !== null || props.status === "interview_proposed"}
        onClick={() => run("invite", async () => {
          const draft = await createDraft({ purpose: "interview_invite", object_type: "candidate", object_id: props.candidateId });
          router.push(`/communications?tab=drafts&message=${draft.id}`);
        })}
      >
        Proposer un entretien
      </Button>
      {props.status === "new" && (
        <Button variant="ghost" loading={busy === "short"} disabled={busy !== null} onClick={() => run("short", async () => { await updateCandidate(props.candidateId, "shortlisted"); router.refresh(); })}>
          Présélectionner
        </Button>
      )}
      {props.status !== "rejected" && (
        <Button variant="ghost" loading={busy === "rej"} disabled={busy !== null} onClick={() => run("rej", async () => { await updateCandidate(props.candidateId, "rejected"); router.refresh(); })}>
          Écarter
        </Button>
      )}
      <span className="text-[11.5px] text-text-faint">L&rsquo;invitation est un brouillon, envoyé seulement après validation.</span>
      {error && <p className="w-full text-[12.5px] text-danger">{error}</p>}
    </div>
  );
}
