import Link from "next/link";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import { fmtDate, fmtMoney, statusTone } from "@/lib/objects";
import type { DocumentSummary } from "@/lib/types";

// A list of commercial documents: number, what, who (linked), status, amount.
export default function DocumentList({ documents, empty, showKind = true }: { documents: DocumentSummary[]; empty: string; showKind?: boolean }) {
  if (documents.length === 0) return <EmptyState message={empty} />;
  return (
    <ul className="space-y-2">
      {documents.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-3 text-[13px] transition-colors hover:border-border-strong">
          <Link href={`/documents/${d.id}`} className="min-w-[150px] font-mono text-[12.5px] font-semibold text-text hover:text-accent-strong">
            {d.number}
          </Link>
          <Link href={`/documents/${d.id}`} className="min-w-0 flex-1 truncate text-text-soft hover:text-text">
            {showKind && <span className="text-text-faint">{d.kind_label} · </span>}
            {d.title ?? `${d.line_count} ligne(s)`}
          </Link>
          {d.party && (
            <Link href={d.party.href} className="text-[12.5px] text-text-soft underline-offset-2 hover:text-text hover:underline">
              {d.party.name}
            </Link>
          )}
          <Badge label={d.status_label} tone={statusTone(d.status)} />
          <span className="w-[92px] text-right font-mono text-[12.5px] font-semibold text-text" title={d.total_is_complete ? undefined : "Montant incomplet : une ligne n'a pas de prix"}>
            {d.total !== null ? fmtMoney(d.total) : "—"}
          </span>
          <span className="num w-[92px] text-right text-[11.5px] text-text-faint">{fmtDate(d.issued_at)}</span>
        </li>
      ))}
    </ul>
  );
}
