// V2 display helpers for business objects: the nature of a value, ranges,
// document statuses. One place, so "estimated" never reads like a fact
// anywhere (brain/decisions.md #34).

import type { BadgeTone } from "@/components/ui/Badge";
import type { Confidence, DocumentKind, MarginView, Measure, ObjectType, Role, ValueBasis } from "@/lib/types";

export const BASIS_LABEL: Record<ValueBasis, string> = {
  observed: "Réel",
  declared: "Déclaré",
  estimated: "Estimé",
  benchmark: "Référence marché",
  simulated: "Simulé",
  unknown: "Inconnu",
};

export const BASIS_HINT: Record<ValueBasis, string> = {
  observed: "Mesuré sur des pièces réelles (facture validée, réception, stock compté).",
  declared: "Annoncé par une partie (devis, catalogue, commande) — pas encore constaté.",
  estimated: "Calculé ou supposé par le système — une estimation, pas un fait.",
  benchmark: "Référence générique, non spécifique à ce cas.",
  simulated: "Donnée de démonstration — ne provient pas de vos systèmes réels.",
  unknown: "Aucune source exploitable.",
};

export const BASIS_TONE: Record<ValueBasis, BadgeTone> = {
  observed: "success",
  declared: "accent",
  estimated: "warning",
  benchmark: "neutral",
  simulated: "danger",
  unknown: "neutral",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "confiance élevée",
  medium: "confiance moyenne",
  low: "confiance faible",
  none: "sans confiance",
};

export const COST_BASIS_LABEL: Record<MarginView["cost_basis"], { label: string; tone: BadgeTone }> = {
  actual: { label: "Marge réelle", tone: "success" },
  partial: { label: "Partiellement réelle", tone: "accent" },
  estimated: { label: "Marge estimée", tone: "warning" },
  incomplete: { label: "Incomplète — coût inconnu", tone: "danger" },
};

export const COST_KIND_LABEL: Record<string, string> = {
  transport: "Transport",
  customs: "Douane",
  insurance: "Assurance",
  handling: "Manutention",
  other: "Autre coût",
};

export const ROLE_LABEL: Record<Role, string> = {
  director: "Direction",
  sales: "Commercial",
  procurement: "Achats",
  operations: "Opérations",
  hr: "RH",
  employee: "Employé",
};

const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const euroCents = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });

export function fmtNumber(n: number): string {
  return number.format(n);
}

export function fmtMoney(n: number | null | undefined, cents = false): string {
  if (n === null || n === undefined) return "—";
  return (cents ? euroCents : euro).format(n);
}

/** "300–450 €" for a range, "520 €" for an exact amount -- never a midpoint. */
export function fmtMoneyRange(min: number | null | undefined, max: number | null | undefined): string {
  if (min === null || min === undefined) return "—";
  if (max === null || max === undefined || Math.abs(max - min) < 0.5) return fmtMoney(min);
  // A dash between signed numbers reads as a minus ("-42 856–-18 456"): use "à".
  const sep = min < 0 || max < 0 ? " à " : "–";
  return `${euro.format(min).replace(/\s?€/, "")}${sep}${euro.format(max)}`;
}

export function fmtPctRange(min: number | null, max: number | null): string {
  if (min === null || max === null) return "—";
  const f = (v: number) => `${(v * 100).toFixed(1).replace(".", ",")} %`;
  return Math.abs(max - min) < 0.0005 ? f(min) : `${(min * 100).toFixed(1).replace(".", ",")}–${f(max)}`;
}

export function fmtDaysRange(min: number | null, max: number | null): string {
  if (min === null) return "—";
  if (max === null || max === min) return `${fmtNumber(min)} j`;
  return `${fmtNumber(min)}–${fmtNumber(max)} j`;
}

/** A Measure as text: its range or value, or its explanation when unknown. */
export function fmtMeasure(m: Measure): string {
  if (m.min !== null && m.max !== null) {
    if (m.unit === "EUR") return fmtMoneyRange(m.min, m.max);
    if (m.unit === "jours") return fmtDaysRange(m.min, m.max);
    return m.min === m.max ? fmtNumber(m.min) : `${fmtNumber(m.min)}–${fmtNumber(m.max)}`;
  }
  if (m.value !== null) {
    if (m.unit === "EUR") return fmtMoney(m.value, true);
    if (m.unit === "/100") return `${fmtNumber(m.value)}/100`;
    return `${fmtNumber(m.value)}${m.unit && m.unit !== "unités" ? ` ${m.unit}` : ""}`;
  }
  return m.text ?? "Inconnu";
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

export const DOCUMENT_KIND_SHORT: Record<DocumentKind, string> = {
  customer_request: "Demande",
  customer_quote: "Devis",
  customer_order: "Commande",
  customer_delivery: "Livraison",
  customer_invoice: "Facture",
  purchase_request: "Demande d'achat",
  supplier_quote: "Devis fournisseur",
  purchase_order: "Commande fournisseur",
  reception: "Réception",
  supplier_invoice: "Facture fournisseur",
  customer_credit_note: "Avoir",
  supplier_credit_note: "Avoir fournisseur",
};

// Status tone: finished well / needs someone / finished badly / in progress.
const GOOD = new Set(["won", "accepted", "confirmed", "delivered", "invoiced", "closed", "paid", "selected", "ordered", "received", "approved", "decided", "validated", "applied", "refunded"]);
const WAITING = new Set(["sent", "requested", "consulting", "comparing", "quoting", "negotiating", "qualifying", "shipped", "expected", "pending_validation", "acknowledged", "submitted", "partially_paid", "issued"]);
const BAD = new Set(["lost", "rejected", "expired", "cancelled", "declined", "disputed"]);

export function statusTone(status: string): BadgeTone {
  if (GOOD.has(status)) return "success";
  if (WAITING.has(status)) return "warning";
  if (BAD.has(status)) return "neutral";
  return "accent";
}

export const OBJECT_TYPE_ICON_LABEL: Record<ObjectType, string> = {
  commercial_document: "Document",
  customer: "Client",
  supplier: "Fournisseur",
  product: "Produit",
  contact: "Contact",
  communication: "Message",
  document: "Fichier",
  transaction: "Écriture",
  task: "Tâche",
  risk: "Risque",
  opportunity: "Opportunité",
  employee: "Employé",
  candidate: "Candidat",
};

/** Permission check against GET /users/me's list (mirrors app/access/policy.py). */
export function can(permissions: string[] | undefined, permission: string): boolean {
  return !!permissions?.includes(permission);
}

/** Years elapsed since a date, one decimal (e.g. an employee's tenure). */
export function yearsSince(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return ((Date.now() - new Date(iso).getTime()) / (365 * 864e5)).toFixed(1);
}
