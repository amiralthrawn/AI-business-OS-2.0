"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { recordPayment, setInstallments } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/objects";
import type { Installment, Settlement } from "@/lib/types";

const field = "rounded-xl border-[1.5px] border-border-strong bg-surface px-3 py-2 text-[13px] outline-none focus:border-accent";

export const INSTALLMENT_STATE: Record<Installment["state"], { label: string; tone: "success" | "accent" | "neutral" | "danger"; dot: string }> = {
  paid: { label: "Réglée", tone: "success", dot: "bg-success" },
  partial: { label: "Partiellement réglée", tone: "accent", dot: "bg-accent" },
  due: { label: "À venir", tone: "neutral", dot: "bg-border-strong" },
  overdue: { label: "En retard", tone: "danger", dot: "bg-danger" },
};

// Instalments as a timeline: each one says its date, amount, what settled it
// and what remains -- on hover (title) AND in plain text (touch screens).
export function InstallmentTimeline({ installments }: { installments: Installment[] }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(170px,1fr))]">
      {installments.map((i) => {
        const st = INSTALLMENT_STATE[i.state];
        return (
          <li
            key={`${i.sequence}-${i.due_at}`}
            title={`${i.label ?? "Échéance"} — ${fmtMoney(i.amount, true)} le ${fmtDate(i.due_at)} · réglé ${fmtMoney(i.settled, true)} · reste ${fmtMoney(i.remaining, true)}`}
            className={`rounded-xl border px-3 py-2.5 ${i.state === "overdue" ? "border-danger/40 bg-danger-soft/40" : "border-border bg-surface"}`}
          >
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
              <span className="truncate text-[12px] font-medium text-text">{i.label ?? `Échéance ${i.sequence}`}</span>
            </div>
            <p className="num mt-1 text-[14px] font-semibold text-text">{fmtMoney(i.amount, true)}</p>
            <p className="num text-[11.5px] text-text-faint">{fmtDate(i.due_at)}</p>
            <p className="mt-1 text-[11.5px]">
              <span className={i.state === "overdue" ? "text-danger" : i.state === "paid" ? "text-success" : "text-text-soft"}>{st.label}</span>
              {i.state === "overdue" && <span className="num text-danger"> · {i.days_late} j</span>}
              {i.remaining > 0 && i.state !== "due" && <span className="num text-text-faint"> · reste {fmtMoney(i.remaining, true)}</span>}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

function ScheduleEditor({ docId, total, onDone }: { docId: string; total: number; onDone: () => void }) {
  const [rows, setRows] = useState([{ due_at: "", amount: String(total), label: "" }]);
  const [error, setError] = useState<string | null>(null);
  const sum = rows.reduce((s, r) => s + (Number(r.amount.replace(",", ".")) || 0), 0);
  return (
    <div className="space-y-2 rounded-xl border border-border bg-surface-alt p-4">
      <p className="text-[12.5px] font-semibold text-text">Échéancier de cette facture</p>
      <p className="text-[11.5px] text-text-faint">Libre : une ou plusieurs échéances, acompte et solde… La somme doit égaler le montant de la facture.</p>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap gap-2">
          <input className={`${field} w-40`} type="date" value={r.due_at} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, due_at: e.target.value } : x)))} />
          <input className={`${field} num w-32`} inputMode="decimal" placeholder="Montant" value={r.amount} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
          <input className={`${field} min-w-[160px] flex-1`} placeholder="Libellé (ex. Acompte 30 %)" value={r.label} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
          {rows.length > 1 && (
            <button type="button" className="text-[12px] text-text-faint hover:text-danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              Retirer
            </button>
          )}
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="text-[12.5px] font-medium text-accent hover:underline" onClick={() => setRows([...rows, { due_at: "", amount: "", label: "" }])}>
          + Ajouter une échéance
        </button>
        <span className={`num text-[12px] ${Math.abs(sum - total) > 0.01 ? "text-danger" : "text-text-faint"}`}>
          Total {fmtMoney(sum, true)} / {fmtMoney(total, true)}
        </span>
        <Button
          disabled={rows.some((r) => !r.due_at || !r.amount) || Math.abs(sum - total) > 0.01}
          onClick={async () => {
            setError(null);
            try {
              await setInstallments(docId, rows.map((r) => ({ due_at: new Date(r.due_at).toISOString(), amount: Number(r.amount.replace(",", ".")), label: r.label || undefined })));
              onDone();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Erreur");
            }
          }}
        >
          Enregistrer l&rsquo;échéancier
        </Button>
      </div>
      {error && <p className="text-[12px] text-danger">{error}</p>}
    </div>
  );
}

// Invoice settlement (brain/billing.md): what is owed, what settled it
// (recorded payments + imputed credit notes), instalment by instalment.
// The invoice's "Réglée / Partiellement réglée" status follows from here.
export default function SettlementPanel({ settlement: s, docId, canWrite }: { settlement: Settlement; docId: string; canWrite: boolean }) {
  const router = useRouter();
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!s.available) {
    return (
      <section id="reglements" className="scroll-mt-6">
        <SectionLabel>Règlement</SectionLabel>
        <p className="text-[13px] text-text-faint">{s.reason}</p>
      </section>
    );
  }
  const payable = s.remaining! > 0.005 && ["issued", "approved", "partially_paid"].includes(s.status);
  return (
    <section id="reglements" className="scroll-mt-6 space-y-4">
      <SectionLabel>Règlement</SectionLabel>
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge label={s.state_label!} tone={s.state === "paid" ? "success" : s.state === "partially_paid" ? "accent" : "neutral"} />
          {s.is_late && <Badge label={`En retard · ${fmtMoney(s.overdue_amount, true)}`} tone="danger" />}
          <span className="num ml-auto text-[12px] text-text-faint">
            {s.installments_paid} / {s.installments_count} échéance{s.installments_count! > 1 ? "s" : ""} réglée{s.installments_paid! > 1 ? "s" : ""}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            ["Montant", s.total],
            ["Réglé", s.paid],
            ["Avoirs imputés", s.credited],
            ["Reste à payer", s.remaining],
          ].map(([label, value]) => (
            <div key={label as string}>
              <p className="text-[12px] text-text-soft">{label}</p>
              <p className={`figure mt-0.5 text-[20px] ${label === "Reste à payer" && (value as number) > 0 ? (s.is_late ? "text-danger" : "text-text") : ""}`}>{fmtMoney(value as number, true)}</p>
            </div>
          ))}
        </div>
        {s.next_due && (
          <p className="mt-3 text-[12.5px] text-text-soft">
            Prochaine échéance : <span className="num font-medium text-text">{fmtMoney(s.next_due.remaining, true)}</span> le <span className="num">{fmtDate(s.next_due.due_at)}</span>
            {s.next_due.label ? ` (${s.next_due.label})` : ""}
          </p>
        )}
      </Card>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-[12.5px] font-semibold text-text-soft">Échéances{s.schedule_is_default ? " — paiement unique à l'échéance de la facture" : ""}</p>
          {canWrite && s.status !== "paid" && (
            <button type="button" className="text-[12px] font-medium text-accent hover:underline" onClick={() => setEditing(!editing)}>
              {editing ? "Fermer" : "Définir un échéancier"}
            </button>
          )}
        </div>
        {editing ? <ScheduleEditor docId={docId} total={s.total!} onDone={() => { setEditing(false); router.refresh(); }} /> : <InstallmentTimeline installments={s.installments!} />}
      </div>

      {(s.payments!.length > 0 || s.credits!.length > 0) && (
        <ul className="space-y-1.5 text-[13px]">
          {s.payments!.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface px-4 py-2">
              <span className="num w-[92px] text-[12px] text-text-faint">{fmtDate(p.occurred_at)}</span>
              <span className="flex-1 text-text">{p.label ?? "Règlement"}</span>
              {p.simulated && <Badge label="Simulé" tone="danger" />}
              <span className="num font-semibold text-success">+{fmtMoney(p.amount, true)}</span>
            </li>
          ))}
          {s.credits!.map((c) => (
            <li key={c.credit_note_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface px-4 py-2">
              <span className="num w-[92px] text-[12px] text-text-faint">{fmtDate(c.applied_at)}</span>
              <Link href={`/documents/${c.credit_note_id}`} className="flex-1 text-text hover:underline">
                Avoir <span className="num">{c.number}</span> imputé
              </Link>
              <span className="num font-semibold text-accent">−{fmtMoney(c.amount, true)}</span>
            </li>
          ))}
        </ul>
      )}

      {canWrite && payable && (
        <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-surface-alt p-4">
          <div className="flex flex-col gap-1">
            <label className="text-[11.5px] text-text-faint">Montant reçu</label>
            <input className={`${field} num w-36`} inputMode="decimal" placeholder={String(s.remaining)} value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[11.5px] text-text-faint">Date</label>
            <input className={`${field} w-40`} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <Button
            loading={busy}
            disabled={!amount}
            onClick={async () => {
              setBusy(true);
              setMessage(null);
              try {
                await recordPayment({ invoice_id: docId, amount: Number(amount.replace(",", ".")), occurred_at: date ? new Date(date).toISOString() : undefined });
                setAmount("");
                router.refresh();
              } catch (err) {
                setMessage(err instanceof Error ? err.message : "Erreur");
              } finally {
                setBusy(false);
              }
            }}
          >
            Enregistrer le règlement
          </Button>
          <p className="basis-full text-[11.5px] text-text-faint">Un règlement enregistré est un paiement réellement reçu ou versé (aucune connexion bancaire). Le statut de la facture en découle.</p>
          {message && <p className="basis-full text-[12px] text-danger">{message}</p>}
        </div>
      )}
    </section>
  );
}
