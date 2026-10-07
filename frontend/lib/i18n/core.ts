// Interface language, shared by Server and Client Components
// (brain/decisions.md #58). The language chosen in the FR / EN switch lives
// in the `aibos_locale` cookie: Server Components read it through
// `getI18n()` (lib/i18n/server.ts), Client Components through `useI18n()`
// (lib/i18n/client.tsx), and every API call sends it as `Accept-Language`
// so the backend generates its texts -- AI content included -- in it.
//
// What is never translated: source data (names of companies, customers,
// suppliers, people and products, references, URLs, the content of real
// emails and documents) and canonical API values ("pending", "high",
// "procurement"), which only their display localizes (`v(group, value)`).

import type { Measure } from "@/lib/types";
import { MESSAGES, type MessageKey } from "@/lib/i18n/messages";
import { VALUES, type ValueGroup } from "@/lib/i18n/values";

export type Locale = "fr" | "en";
export const LOCALES: readonly Locale[] = ["fr", "en"];
export const DEFAULT_LOCALE: Locale = "fr";
export const LOCALE_COOKIE = "aibos_locale";

export type { MessageKey, ValueGroup };
export type Vars = Record<string, string | number | null | undefined>;

export function parseLocale(value: string | null | undefined): Locale {
  return value === "en" ? "en" : DEFAULT_LOCALE;
}

const INDEX: Record<Locale, 0 | 1> = { fr: 0, en: 1 };

function interpolate(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = vars[name];
    return value === null || value === undefined ? "" : String(value);
  });
}

/** Locale-aware number, money, percentage and date formatting. */
export function makeFormat(locale: Locale) {
  const tag = locale === "en" ? "en-GB" : "fr-FR";
  const number = new Intl.NumberFormat(tag, { maximumFractionDigits: 2 });
  const euro = new Intl.NumberFormat(tag, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  const euroCents = new Intl.NumberFormat(tag, { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const to = locale === "en" ? " to " : " à ";
  const pctSuffix = locale === "en" ? "%" : " %";
  const days = locale === "en" ? "d" : "j";

  const fmt = {
    locale,
    tag,
    number: (n: number) => number.format(n),
    /** 1 234 € / €1,234 -- cents on request. */
    money: (n: number | null | undefined, cents = false) => (n === null || n === undefined ? "—" : (cents ? euroCents : euro).format(n)),
    /** "300–450 €" for a range, "520 €" for an exact amount -- never a midpoint. */
    moneyRange: (min: number | null | undefined, max: number | null | undefined) => {
      if (min === null || min === undefined) return "—";
      if (max === null || max === undefined || Math.abs(max - min) < 0.5) return euro.format(min);
      // A dash between signed numbers reads as a minus: a word instead.
      if (min < 0 || max < 0) return `${euro.format(min)}${to}${euro.format(max)}`;
      return `${euro.format(min)}–${euro.format(max)}`;
    },
    /** A ratio (0.593) as a percentage: 59,3 % / 59.3%. */
    pct: (ratio: number | null | undefined, digits = 1) =>
      ratio === null || ratio === undefined ? "—" : `${new Intl.NumberFormat(tag, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(ratio * 100)}${pctSuffix}`,
    /** A value already in percent (59.3) -- 59,3 % / 59.3%. */
    percent: (value: number, digits = 1) => `${new Intl.NumberFormat(tag, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)}${pctSuffix}`,
    pctRange: (min: number | null, max: number | null) => {
      if (min === null || max === null) return "—";
      if (Math.abs(max - min) < 0.0005) return fmt.pct(min);
      return `${new Intl.NumberFormat(tag, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(min * 100)}–${fmt.pct(max)}`;
    },
    daysRange: (min: number | null, max: number | null) => {
      if (min === null) return "—";
      if (max === null || max === min) return `${number.format(min)} ${days}`;
      return `${number.format(min)}–${number.format(max)} ${days}`;
    },
    /** 7 oct. 2026 / 7 Oct 2026 */
    date: (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(tag, { day: "numeric", month: "short", year: "numeric" }) : "—"),
    /** 07/10/2026 */
    dateNumeric: (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(tag) : "—"),
    /** 7 octobre 2026 / 7 October 2026 */
    dateLong: (iso: string | Date) => new Date(iso).toLocaleDateString(tag, { day: "numeric", month: "long", year: "numeric" }),
    /** mardi 7 octobre / Tuesday 7 October */
    weekday: (iso: string | Date) => new Date(iso).toLocaleDateString(tag, { weekday: "long", day: "numeric", month: "long" }),
    time: (iso: string) => new Date(iso).toLocaleTimeString(tag, { hour: "2-digit", minute: "2-digit" }),
    dateTime: (iso: string) => new Date(iso).toLocaleString(tag, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }),
    /** "2026-09" -> "sept. 2026" / "Sep 2026" */
    month: (month: string, short = true) => {
      const [year, m] = month.split("-").map(Number);
      return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString(tag, { month: short ? "short" : "long", year: "numeric", timeZone: "UTC" });
    },
    /** A backend Measure as text: its range or value, or its own explanation when unknown. */
    measure: (m: Measure) => {
      const isDays = m.unit === "jours" || m.unit === "days";
      const isUnits = m.unit === "unités" || m.unit === "units";
      if (m.min !== null && m.max !== null) {
        if (m.unit === "EUR") return fmt.moneyRange(m.min, m.max);
        if (isDays) return fmt.daysRange(m.min, m.max);
        return m.min === m.max ? number.format(m.min) : `${number.format(m.min)}–${number.format(m.max)}`;
      }
      if (m.value !== null) {
        if (m.unit === "EUR") return fmt.money(m.value, true);
        if (m.unit === "/100") return `${number.format(m.value)}/100`;
        return `${number.format(m.value)}${m.unit && !isUnits ? ` ${m.unit}` : ""}`;
      }
      return m.text ?? (locale === "en" ? "Unknown" : "Inconnu");
    },
  };
  return fmt;
}

export type Format = ReturnType<typeof makeFormat>;

export interface I18n {
  locale: Locale;
  /** A message of the dictionary, with {placeholders}. */
  t: (key: MessageKey, vars?: Vars) => string;
  /** Same, for a key built at runtime (falls back to `fallback`, then the key). */
  tk: (key: string, vars?: Vars, fallback?: string) => string;
  /** Display label of a canonical API value: v("taskStatus", "pending_validation"). */
  v: (group: ValueGroup, value: string | null | undefined) => string;
  f: Format;
}

export function createI18n(locale: Locale): I18n {
  const i = INDEX[locale];
  const messages = MESSAGES as Record<string, readonly [string, string]>;
  return {
    locale,
    t: (key, vars) => interpolate(messages[key]?.[i] ?? key, vars),
    tk: (key, vars, fallback) => interpolate(messages[key]?.[i] ?? fallback ?? key, vars),
    v: (group, value) => {
      if (value === null || value === undefined || value === "") return "—";
      const entry = (VALUES[group] as Record<string, readonly [string, string]>)[value];
      return entry ? entry[i] : value;
    },
    f: makeFormat(locale),
  };
}
