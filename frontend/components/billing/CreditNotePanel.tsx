"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { applyCreditNote, recordRefund, requestCreditValidation } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/objects";
import type { CreditView, DocumentKind } from "@/lib/types";

type Step = { key: string; label: string; hint: string };

const CUSTOMER_STEPS: Step[] = [
  { key: "draft", label: "Préparé", hint: "Créé en interne, pas encore proposé." },
  { key: "submitted", label: "Soumis au client", hint: "En attente de sa réponse." },
  { key: "answer", label: "Réponse du client", hint: "Acceptation ou refus, enregistré par une personne." },
  { key: "validated", label: "Validé", hint: "Validation interne (Human-in-the-loop)." },
  { key: "applied", label: "Imputé", hint: "Déduit une seule fois du compte client." },
  { key: "refunded", label: "Remboursé", hint: "Seulement si le client avait déjà payé." },
];
const SUPPLIER_STEPS: Step[] = [
  { key: "requested", label: "Avoir demandé", hint: "Réclamation envoyée au fournisseur." },
  { key: "answer", label: "Réponse du fournisseur", hint: "Confirmation ou refus, enregistré par une personne." },
  { key: "applied", label: "Imputé", hint: "Déduit une seule fois de ce que nous lui devons." },
];

function stepIndex(kind: DocumentKind, status: string): number {
  const order = kind === "customer_credit_note" ? ["draft", "submitted", "answer", "validated", "applied", "refunded"] : ["requested", "answer", "applied"];
  const key = ["accepted", "rejected", "confirmed"].includes(status) ? "answer" : status === "cancelled" ? "draft" : status;
  return order.indexOf(key);
}

// A credit note's life, honestly: created ≠ proposed ≠ accepted ≠ validated ≠
// imputed. The balance only moves at "Imputé", and only once.
export default function CreditNotePanel({ credit: c, kind, docId, canSales, canFinance }: { credit: CreditView; kind: DocumentKind; docId: string; canSales: boolean; canFinance: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const steps = kind === "customer_credit_note" ? CUSTOMER_STEPS : SUPPLIER_STEPS;
  const current = stepIndex(kind, c.status);
  const refused = c.status === "rejected";
  const needsRefund = c.refund_due > 0 || c.refund !== null;

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setMessage(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section id="avoir" className="scroll-mt-6 space-y-4">
      <SectionLabel>{kind === "customer_credit_note" ? "Cycle de l'avoir" : "Réclamation fournisseur"}</SectionLabel>
      <Card className="p-5">
        <ol className="flex flex-wrap items-start gap-y-3">
          {steps
            .filter((s) => s.key !== "refunded" || needsRefund)
            .map((s, i, arr) => {
              const done = i < current || (i === current && ["applied", "refunded", "validated"].includes(s.key));
              const here = i === current;
              const answerLabel = s.key === "answer" && current >= i ? (refused ? "Refusé" : kind === "customer_credit_note" ? "Accepté" : "Confirmé") : s.label;
              return (
                <li key={s.key} className="flex min-w-[120px] flex-1 items-start gap-2" title={s.hint}>
                  <span
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                      refused && s.key === "answer" ? "bg-danger text-white" : done ? "bg-success text-white" : here ? "bg-accent text-white" : "bg-surface-sunken text-text-faint"
                    }`}
                  >
                    {done && !(refused && s.key === "answer") ? "✓" : i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className={`text-[12.5px] ${here || done ? "font-semibold text-text" : "text-text-faint"}`}>{answerLabel}</p>
                    <p className="text-[11px] text-text-faint">{s.hint}</p>
                  </div>
                  {i < arr.length - 1 && <span className="mt-2.5 hidden h-px flex-1 bg-border md:block" />}
                </li>
              );
            })}
        </ol>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-[12px] text-text-soft">Montant de l&rsquo;avoir</p>
            <p className="figure mt-0.5 text-[20px]">{fmtMoney(c.amount, true)}</p>
          </div>
          {c.application && (
            <>
              <div>
                <p className="text-[12px] text-text-soft">{c.application.invoice_id ? "Déduit de la facture" : "Crédit laissé sur le compte"}</p>
                <p className="figure mt-0.5 text-[20px]">{fmtMoney(c.application.invoice_id ? c.application.applied_amount : c.amount, true)}</p>
              </div>
              <div>
                <p className="text-[12px] text-text-soft">À rembourser</p>
                <p className={`figure mt-0.5 text-[20px] ${c.refund_due > 0 ? "text-warning" : ""}`}>{fmtMoney(c.application.refund_amount, true)}</p>
                {c.refund && <p className="text-[11.5px] text-success">Remboursé le <span className="num">{fmtDate(c.refund.occurred_at)}</span></p>}
              </div>
            </>
          )}
        </div>
        <p className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px] text-text-soft">
          <Badge label={c.counts_in_balance ? "Compté dans le solde" : "Non compté dans le solde"} tone={c.counts_in_balance ? "success" : "neutral"} />
          {c.effect}
        </p>
        {c.invoice && (
          <p className="mt-1 text-[12px] text-text-faint">
            Facture concernée : <Link href={`/documents/${c.invoice.id}#reglements`} className="num text-text-soft hover:underline">{c.invoice.number}</Link> ({c.invoice.status_label})
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {c.validation_task_id && (
            <Link href="/actions/tasks" className="rounded-xl border-[1.5px] border-warning/60 bg-warning-soft px-3 py-2 text-[12.5px] font-medium text-warning">
              Validation interne en attente → Actions &amp; validations
            </Link>
          )}
          {c.can_request_validation && (
            <Button variant="ghost" loading={busy === "validate"} disabled={!canSales} title={canSales ? undefined : "Réservé aux ventes"} onClick={() => run("validate", () => requestCreditValidation(docId))}>
              Soumettre à la validation interne
            </Button>
          )}
          {c.can_apply && (
            <Button loading={busy === "apply"} disabled={!canFinance} title={canFinance ? undefined : "Réservé à la finance"} onClick={() => run("apply", () => applyCreditNote(docId))}>
              {kind === "customer_credit_note" ? "Imputer au compte client" : "Imputer sur la facture fournisseur"}
            </Button>
          )}
          {c.can_refund && (
            <Button loading={busy === "refund"} disabled={!canFinance} title={canFinance ? undefined : "Réservé à la finance"} onClick={() => run("refund", () => recordRefund(docId))}>
              Enregistrer le remboursement ({fmtMoney(c.refund_due, true)})
            </Button>
          )}
        </div>
        {c.can_refund && <p className="mt-2 text-[11.5px] text-text-faint">Enregistrez le remboursement une fois le virement réellement effectué : aucune opération bancaire n&rsquo;est déclenchée par le logiciel.</p>}
        {message && <p className="mt-2 text-[12px] text-danger">{message}</p>}
      </Card>
    </section>
  );
}
