import Link from "next/link";
import { TRANSACTION_STATUS_LABEL, TRANSACTION_TYPE_LABEL, formatDateFR, formatEUR } from "@/lib/labels";
import type { TransactionRead } from "@/lib/types";

interface TransactionRowProps {
  transaction: TransactionRead;
  party?: "supplier" | "customer" | "auto";
  linkParty?: boolean;
  showProduct?: boolean;
}

export default function TransactionRow({ transaction: t, party = "auto", linkParty = false, showProduct = false }: TransactionRowProps) {
  const name = party === "customer" ? t.customer_name : party === "supplier" ? t.supplier_name : t.supplier_name ?? t.customer_name;
  const href = party === "customer" || (party === "auto" && t.customer_id) ? `/data/customers/${t.customer_id}` : `/data/suppliers/${t.supplier_id}`;

  return (
    <li className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3.5 text-[13.5px]">
      <div>
        <span className="font-semibold text-text">
          {linkParty && name ? (
            <Link href={href} className="hover:underline">
              {name}
            </Link>
          ) : (
            name ?? "Partie inconnue"
          )}
        </span>
        <p className="mt-0.5 text-[12px] text-text-faint">
          {TRANSACTION_TYPE_LABEL[t.type] ?? t.type} &middot; {TRANSACTION_STATUS_LABEL[t.status] ?? t.status}
          {showProduct && t.product_name && (
            <>
              {" "}
              &middot;{" "}
              <Link href={`/data/products/${t.product_id}`} className="hover:underline">
                {t.product_name}
              </Link>
            </>
          )}{" "}
          &middot; <span className="num">{formatDateFR(t.occurred_at)}</span>
        </p>
      </div>
      <span className="font-mono font-semibold text-text">{formatEUR(t.amount)}</span>
    </li>
  );
}
