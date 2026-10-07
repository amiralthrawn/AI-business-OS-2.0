"use client";

import { createContext, useContext, useEffect } from "react";

export type Locale = "fr" | "en";

// Centralized interface labels (Step 28 §7) -- one dictionary, never
// per-component duplicate translations.
//
// FRENCH ONLY for now (brain/decisions.md #56): page content, backend
// analyses, risks, decisions and labels are French, so an EN switch only
// translated the chrome and produced a mixed interface. The switch is
// removed and the locale is fixed to French; the English column is kept so a
// real bilingual version can be built later from this same dictionary.
const DICT = {
  "nav.home": { fr: "Accueil", en: "Home" },
  "nav.command_center": { fr: "Centre de contrôle", en: "Command Center" },
  "nav.company_group": { fr: "Entreprise", en: "Business" },
  "nav.finance": { fr: "Finance", en: "Finance" },
  "nav.procurement": { fr: "Achats", en: "Procurement" },
  "nav.sales": { fr: "Ventes", en: "Sales" },
  "nav.data_group": { fr: "Données", en: "Data" },
  "nav.data_entities": { fr: "Fournisseurs, clients, produits", en: "Suppliers, customers, products" },
  "nav.contacts": { fr: "Contacts", en: "Contacts" },
  "nav.intelligence_group": { fr: "Intelligence", en: "Intelligence" },
  "nav.decision_intelligence": { fr: "Décisionnelle", en: "Decision Intelligence" },
  "nav.risks": { fr: "Risques", en: "Risks" },
  "nav.opportunities": { fr: "Opportunités", en: "Opportunities" },
  "nav.actions_group": { fr: "Actions", en: "Actions" },
  "nav.tasks": { fr: "Tâches", en: "Tasks" },
  "nav.activity": { fr: "Activité de l'entreprise", en: "Company activity" },
  "nav.ai_group": { fr: "IA", en: "AI" },
  "nav.ask_ai": { fr: "Demander à l'IA", en: "Ask AI" },
  "nav.configure_company": { fr: "Configurer l'entreprise", en: "Configure company" },
  "nav.configuration": { fr: "Configuration", en: "Settings" },
  "nav.live": { fr: "Données en direct", en: "Data Core · live" },
  "topbar.open_menu": { fr: "Ouvrir le menu", en: "Open menu" },
  "topbar.pending": { fr: "action(s) en attente de validation", en: "action(s) pending validation" },
  // V2 navigation (brain/navigation_v2.md)
  "nav.operations_group": { fr: "Opérations", en: "Operations" },
  "nav.steering_group": { fr: "Pilotage", en: "Steering" },
  "nav.catalog": { fr: "Catalogue & stock", en: "Catalog & stock" },
  "nav.communications": { fr: "Communications", en: "Communications" },
  "nav.intelligence": { fr: "Intelligence", en: "Intelligence" },
  "nav.actions": { fr: "Actions & validations", en: "Actions & approvals" },
  "nav.documents": { fr: "Document", en: "Document" },
  "topbar.profile": { fr: "Profil", en: "Profile" },
  // V2.1
  "nav.people": { fr: "Équipe", en: "Team" },
  "nav.direction": { fr: "Direction", en: "Leadership" },
  "topbar.no_profile": { fr: "Aucun profil (accès complet)", en: "No profile (full access)" },
} as const;

export type LabelKey = keyof typeof DICT;

interface LocaleContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: LabelKey) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

const STORAGE_KEY = "ai-business-os-locale";
const ACTIVE_LOCALE: Locale = "fr";

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const locale = ACTIVE_LOCALE;

  useEffect(() => {
    // A visitor may still have "en" stored from the former switch: forget it.
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // localStorage unavailable (private browsing, etc.) -- nothing to clean.
    }
  }, []);

  function setLocale(l: Locale) {
    // French only for now (see above): kept for API compatibility.
    void l;
  }

  function t(key: LabelKey): string {
    return DICT[key][locale];
  }

  return <LocaleContext.Provider value={{ locale, setLocale, t }}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within a LocaleProvider");
  return ctx;
}
