"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import SectionLabel from "@/components/objects/SectionLabel";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { reportNonconformity } from "@/lib/api";
import { fmtDate } from "@/lib/objects";
import type { DocumentLine, Fulfilment } from "@/lib/types";

const field = "rounded-xl border-[1.5px] border-border-strong bg-surface px-3 py-2 text-[13px] outline-none focus:border-accent";
const fmtQty = (n: number) => n.toLocaleString("fr-FR", { maximumFractionDigits: 2 });

const STATE_TONE: Record<Fulfilment["state"], "success" | "accent" | "warning" | "neutral"> = {
  complete: "success",
  partial: "warning",
  in_transit: "accent",
  planned: "neutral",
  not_started: "neutral",
};

// Where the goods are, line by line: ordered / shipped / delivered-received /
// still to come, with the delivery documents (planned vs actual date, delay,
// carrier, tracking). Only document statuses count -- nothing is shown as
// shipped or received without the corresponding recorded event.
export function FulfilmentView({ f, currentId }: { f: Fulfilment; currentId?: string }) {
  const doneLabel = f.kind === "delivery" ? "Livré" : "Reçu";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge label={f.state_label} tone={STATE_TONE[f.state]} />
        {f.is_late && <Badge label="En retard" tone="danger" />}
        {f.nonconforming_total > 0 && <Badge label={`${fmtQty(f.nonconforming_total)} non conforme(s)`} tone="danger" />}
        {f.promised_at && <span className="text-[12px] text-text-faint">Promis le <span className="num">{fmtDate(f.promised_at)}</span></span>}
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[560px] text-[12.5px]">
          <thead className="text-left text-text-faint">
            <tr className="border-b border-border">
              <th className="px-4 py-2 font-medium">Article</th>
              <th className="px-4 py-2 text-right font-medium">Commandé</th>
              <th className="px-4 py-2 text-right font-medium">En transit</th>
              <th className="px-4 py-2 text-right font-medium">{doneLabel}</th>
              <th className="px-4 py-2 text-right font-medium">Reste</th>
              <th className="px-4 py-2 font-medium">Avancement</th>
            </tr>
          </thead>
          <tbody>
            {f.lines.map((l) => {
              const pct = l.ordered ? Math.min(1, l.done / l.ordered) : 0;
              const transit = l.ordered ? Math.min(1 - pct, l.in_transit / l.ordered) : 0;
              return (
                <tr key={l.key} className="border-b border-border last:border-0 hover:bg-surface-alt">
                  <td className="px-4 py-2 text-text">
                    {l.label}
                    {l.nonconforming > 0 && <span className="num ml-2 text-[11.5px] text-danger">dont {fmtQty(l.nonconforming)} non conforme(s)</span>}
                  </td>
                  <td className="num px-4 py-2 text-right">{fmtQty(l.ordered)}</td>
                  <td className="num px-4 py-2 text-right text-accent">{l.in_transit ? fmtQty(l.in_transit) : "—"}</td>
                  <td className="num px-4 py-2 text-right">{fmtQty(l.done)}</td>
                  <td className={`num px-4 py-2 text-right ${l.remaining > 0 ? "font-semibold text-text" : "text-text-faint"}`}>{fmtQty(l.remaining)}</td>
                  <td className="px-4 py-2">
                    <div className="flex h-2 w-28 overflow-hidden rounded-full bg-surface-sunken" title={`${doneLabel} ${Math.round(pct * 100)} % · en transit ${Math.round(transit * 100)} %`}>
                      <span className="animate-reveal bg-success" style={{ width: `${pct * 100}%` }} />
                      <span className="animate-reveal bg-accent/60" style={{ width: `${transit * 100}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      {f.documents.length > 0 && (
        <ol className="space-y-1.5">
          {f.documents.map((d) => (
            <li key={d.id} className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border px-4 py-2.5 text-[12.5px] ${d.id === currentId ? "border-accent bg-accent-soft/40" : "border-border bg-surface"}`}>
              <Link href={`/documents/${d.id}`} className="num font-medium text-text hover:underline">{d.number}</Link>
              <Badge label={d.status_label} tone={d.status === "delivered" || d.status === "received" ? "success" : d.status === "shipped" ? "accent" : "neutral"} />
              <span className="text-text-faint">
                prévu <span className="num">{fmtDate(d.planned_at)}</span>
                {d.done_at && (
                  <>
                    {" · "}réel <span className="num">{fmtDate(d.done_at)}</span>
                  </>
                )}
              </span>
              {d.late_days > 0 && <span className="num text-danger">+{d.late_days} j</span>}
              {(d.carrier || d.tracking_number) && (
                <span className="text-text-soft">
                  {d.carrier}
                  {d.tracking_number && <span className="num ml-1.5 text-text-faint">{d.tracking_number}</span>}
                </span>
              )}
              {d.nonconforming_lines > 0 && <Badge label="Non-conformité" tone="danger" />}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function NonconformityForm({ docId, lines }: { docId: string; lines: DocumentLine[] }) {
  const router = useRouter();
  const [lineId, setLineId] = useState(lines[0]?.id ?? "");
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const line = lines.find((l) => l.id === lineId);
  return (
    <div className="space-y-2 rounded-xl border border-border bg-surface-alt p-4">
      <p className="text-[12.5px] font-semibold text-text">Signaler une non-conformité</p>
      <div className="flex flex-wrap gap-2">
        <select className={field} value={lineId} onChange={(e) => setLineId(e.target.value)}>
          {lines.map((l) => (
            <option key={l.id} value={l.id}>
              {l.product_name ?? l.description ?? "Article"} ({fmtQty(l.quantity)})
            </option>
          ))}
        </select>
        <input className={`${field} num w-28`} inputMode="decimal" placeholder={`Qté ≤ ${line ? fmtQty(line.quantity) : ""}`} value={qty} onChange={(e) => setQty(e.target.value)} />
        <input className={`${field} min-w-[220px] flex-1`} placeholder="Défaut constaté" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button
          disabled={!lineId || !qty || !note.trim()}
          onClick={async () => {
            setMessage(null);
            try {
              const res = await reportNonconformity(docId, { line_id: lineId, quantity: Number(qty.replace(",", ".")), note });
              setMessage(res.risk_created ? "Non-conformité enregistrée : un risque et sa tâche de revue ont été créés dans Intelligence." : "Non-conformité mise à jour (risque déjà ouvert).");
              router.refresh();
            } catch (err) {
              setMessage(err instanceof Error ? err.message : "Erreur");
            }
          }}
        >
          Enregistrer
        </Button>
      </div>
      <p className="text-[11.5px] text-text-faint">Ensuite : « Créer avoir » (client) ou « Créer avoir fournisseur » (réclamation) ne reprend que les quantités non conformes.</p>
      {message && <p className="text-[12px] text-text-soft">{message}</p>}
    </div>
  );
}

export default function FulfilmentPanel({ fulfilment, docId, lines, canReport, isPhysicalDoc }: { fulfilment: Fulfilment | null | undefined; docId: string; lines: DocumentLine[]; canReport: boolean; isPhysicalDoc: boolean }) {
  const flagged = lines.filter((l) => (l.quantity_nonconforming ?? 0) > 0);
  return (
    <section id="suivi" className="scroll-mt-6 space-y-4">
      <SectionLabel>{isPhysicalDoc ? "Suivi de la commande" : "Suivi des livraisons"}</SectionLabel>
      {fulfilment ? <FulfilmentView f={fulfilment} currentId={docId} /> : <p className="text-[13px] text-text-faint">Aucune commande rattachée : pas de suivi de quantités.</p>}
      {flagged.length > 0 && (
        <ul className="space-y-1 text-[12.5px]">
          {flagged.map((l) => (
            <li key={l.id} className="rounded-lg bg-danger-soft/50 px-3 py-2 text-text">
              <span className="num font-semibold">{fmtQty(l.quantity_nonconforming ?? 0)}</span> × {l.product_name ?? l.description ?? "article"} non conforme(s) — {l.nonconformity_note}
            </li>
          ))}
        </ul>
      )}
      {isPhysicalDoc && canReport && lines.length > 0 && <NonconformityForm docId={docId} lines={lines} />}
    </section>
  );
}
