"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { addBankAccount, monitorCash, updateFinanceSettings } from "@/lib/api";

const field = "rounded-xl border-[1.5px] border-border-strong px-3 py-2 text-[13px] outline-none focus:border-accent";

export function AccountForm() {
  const router = useRouter();
  const [f, setF] = useState({ name: "", bank_name: "", kind: "current", identifier: "", balance: "" });
  const [message, setMessage] = useState<string | null>(null);
  return (
    <Card className="space-y-2 p-5">
      <p className="text-[13px] font-semibold text-text">Ajouter un compte, une carte ou un prêt</p>
      <div className="flex flex-wrap gap-2">
        <input className={field} placeholder="Nom" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className={field} placeholder="Banque" value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} />
        <select className={field} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="current">Compte courant</option>
          <option value="savings">Épargne</option>
          <option value="card">Carte</option>
          <option value="loan">Prêt</option>
        </select>
        <input className={field} placeholder="IBAN / n° de carte" value={f.identifier} onChange={(e) => setF({ ...f, identifier: e.target.value })} />
        <input className={field} placeholder="Solde (déclaré)" value={f.balance} onChange={(e) => setF({ ...f, balance: e.target.value })} />
        <Button
          disabled={!f.name.trim()}
          onClick={async () => {
            try {
              const res = await addBankAccount({ ...f, balance: Number(f.balance.replace(",", ".")) || 0, identifier: f.identifier || undefined });
              setMessage(`Compte ajouté (${res.masked_identifier ?? "sans identifiant"}).`);
              setF({ name: "", bank_name: "", kind: "current", identifier: "", balance: "" });
              router.refresh();
            } catch (err) {
              setMessage(err instanceof Error ? err.message : "Erreur");
            }
          }}
        >
          Ajouter
        </Button>
      </div>
      <p className="text-[11.5px] text-text-faint">Seuls les 4 derniers caractères de l&rsquo;IBAN ou de la carte sont conservés. Aucune connexion bancaire : le solde est déclaré.</p>
      {message && <p className="text-[12.5px] text-text-soft">{message}</p>}
    </Card>
  );
}

export function CashMonitor() {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant="ghost"
        onClick={async () => {
          const res = await monitorCash();
          setMessage(res.risk_created ? "Risque de trésorerie créé dans Intelligence (tâche de revue associée)." : res.reason ?? "Aucun risque.");
          router.refresh();
        }}
      >
        Contrôler la projection
      </Button>
      {message && <span className="text-[12.5px] text-text-soft">{message}</span>}
    </div>
  );
}

export function FinanceSettingsForm({ initial }: { initial: { min_cash?: number | null; declared_valuation?: number | null; revenue_multiple_min?: number | null; revenue_multiple_max?: number | null } }) {
  const router = useRouter();
  const [f, setF] = useState({
    min_cash: initial.min_cash?.toString() ?? "",
    declared_valuation: initial.declared_valuation?.toString() ?? "",
    revenue_multiple_min: initial.revenue_multiple_min?.toString() ?? "",
    revenue_multiple_max: initial.revenue_multiple_max?.toString() ?? "",
  });
  const [saved, setSaved] = useState(false);
  const num = (v: string) => (v.trim() ? Number(v.replace(",", ".")) : null);
  return (
    <Card className="space-y-2 p-5">
      <p className="text-[13px] font-semibold text-text">Paramètres déclarés par la direction</p>
      <div className="flex flex-wrap gap-2">
        <input className={field} placeholder="Trésorerie minimum (€)" value={f.min_cash} onChange={(e) => setF({ ...f, min_cash: e.target.value })} />
        <input className={field} placeholder="Valorisation déclarée (€)" value={f.declared_valuation} onChange={(e) => setF({ ...f, declared_valuation: e.target.value })} />
        <input className={field} placeholder="Multiple de CA min" value={f.revenue_multiple_min} onChange={(e) => setF({ ...f, revenue_multiple_min: e.target.value })} />
        <input className={field} placeholder="Multiple de CA max" value={f.revenue_multiple_max} onChange={(e) => setF({ ...f, revenue_multiple_max: e.target.value })} />
        <Button
          variant="ghost"
          onClick={async () => {
            await updateFinanceSettings({ min_cash: num(f.min_cash), declared_valuation: num(f.declared_valuation), revenue_multiple_min: num(f.revenue_multiple_min), revenue_multiple_max: num(f.revenue_multiple_max) });
            setSaved(true);
            router.refresh();
          }}
        >
          Enregistrer
        </Button>
      </div>
      {saved && <p className="text-[12px] text-success">Enregistré.</p>}
    </Card>
  );
}
