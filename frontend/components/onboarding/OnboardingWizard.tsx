"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import Toggle from "@/components/ui/Toggle";
import { createUser, setSelectedProfile, updateBusinessContext, updateCompany } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/objects";
import type { BusinessContextRead, CompanyRead, Role } from "@/lib/types";

const SIZE_OPTIONS = ["1–10", "11–50", "51–200", "200+"];
const COUNTRY_OPTIONS = [
  { code: "FR", label: "France" },
  { code: "DE", label: "Allemagne" },
  { code: "BE", label: "Belgique" },
  { code: "CH", label: "Suisse" },
];
const DOMAIN_OPTIONS = [
  { value: "finance", label: "Finance", enabled: true },
  { value: "procurement", label: "Achats / Procurement", enabled: true },
  { value: "sales", label: "Ventes", enabled: true },
  { value: "hr", label: "Ressources humaines", enabled: false },
  { value: "marketing", label: "Marketing", enabled: false },
  { value: "supply_chain", label: "Supply Chain", enabled: false },
];
const SYSTEMS = [
  { key: "erp", label: "ERP" },
  { key: "crm", label: "CRM" },
  { key: "accounting", label: "Comptabilité" },
  { key: "ecommerce", label: "E-commerce" },
  { key: "hr", label: "RH / Paie" },
] as const;

// V2: the default sector is Travel Agency (changeable; the model stays
// generic -- products can be stays/services, suppliers hotels/carriers).
const DEFAULT_SECTOR = "Agence de voyage (Travel Agency)";
const SECTOR_OPTIONS = [DEFAULT_SECTOR, "Négoce / distribution B2B", "Industrie", "Services aux entreprises", "E-commerce"];

// V2 roles: the second part of the setup -- who is using the OS, in which
// role (brain/permissions.md). Shapes navigation, editable objects and
// the actions this person can validate.
const ROLE_OPTIONS: { role: Role; hint: string }[] = [
  { role: "director", hint: "Vue globale, valide toutes les actions" },
  { role: "sales", hint: "Demandes, devis, commandes, relances clients" },
  { role: "procurement", hint: "Demandes d'achat, fournisseurs, commandes" },
  { role: "operations", hint: "Réceptions, livraisons, stock" },
  { role: "hr", hint: "Communications et actions (RH à venir)" },
  { role: "employee", hint: "Consultation et tâches" },
];

const STEPS = ["Entreprise", "Organisation", "Systèmes actuels", "Votre rôle", "Récapitulatif"];

export default function OnboardingWizard({
  initialCompany,
  initialContext,
}: {
  initialCompany: CompanyRead | null;
  initialContext: BusinessContextRead | null;
}) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState(initialCompany?.name ?? "");
  const [industry, setIndustry] = useState(initialCompany?.industry || DEFAULT_SECTOR);
  const [userName, setUserName] = useState("");
  const [role, setRole] = useState<Role>("director");
  const [size, setSize] = useState(initialContext?.company_size ?? "11–50");
  const [country, setCountry] = useState(initialContext?.country ?? "FR");
  const [domains, setDomains] = useState<string[]>(initialContext?.monitored_domains ?? ["finance", "procurement", "sales"]);
  const [objectives, setObjectives] = useState(initialContext?.stated_objectives ?? "");
  const [systems, setSystems] = useState<Record<string, boolean>>({ erp: false, crm: false, accounting: false, ecommerce: false, hr: false });

  function toggleDomain(value: string) {
    setDomains((prev) => (prev.includes(value) ? prev.filter((d) => d !== value) : [...prev, value]));
  }

  function skipToProduct() {
    localStorage.setItem("aibos_onboarding_done", "1");
    router.push("/");
  }

  async function finish() {
    setSaving(true);
    setError(null);
    try {
      await Promise.all([
        updateCompany({ name: name.trim() || undefined, industry: industry.trim() || undefined }),
        updateBusinessContext({
          company_size: size,
          country,
          monitored_domains: domains,
          stated_objectives: objectives.trim() || undefined,
        }),
      ]);
      // Second part: the person and their role -> a profile selected for
      // every following API call (cookie read by lib/api.ts).
      const profile = await createUser({ name: userName.trim() || "Moi", role });
      setSelectedProfile(profile.id);
      localStorage.setItem("aibos_onboarding_done", "1");
      localStorage.setItem("aibos_systems", JSON.stringify(systems));
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue lors de l'enregistrement.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center bg-bg px-6 py-10">
      <div className="flex w-full max-w-3xl items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-[26px] w-[26px] items-center justify-center rounded-lg bg-accent font-display text-[13px] font-semibold text-white">B</div>
          <span className="font-display text-[15px] font-semibold">AI Business OS</span>
        </div>
        <div className="flex items-center gap-2">
          {STEPS.map((_, i) => (
            <span key={i} className={`h-[7px] rounded-full transition-all ${i === step ? "w-[22px] bg-accent" : i < step ? "w-[7px] bg-accent-strong" : "w-[7px] bg-border-strong"}`} />
          ))}
          <span className="ml-1.5 font-mono text-[11.5px] text-text-faint">
            Étape {step + 1} sur {STEPS.length}
          </span>
        </div>
      </div>

      <div key={step} className="animate-reveal mt-12 w-full max-w-[640px] rounded-[20px] border border-border bg-surface p-10 shadow-card md:p-14">
        <p className="text-[12.5px] font-semibold uppercase tracking-wide text-accent-strong">Configuration initiale</p>

        {step === 0 && (
          <>
            <h1 className="mt-3 font-display text-[32px] italic leading-tight md:text-[36px]">
              Configurons votre
              <br />
              espace de travail
            </h1>
            <p className="mt-3.5 max-w-lg text-[15px] text-text-soft">
              Quelques informations pour personnaliser AI Business OS à votre activité. Vous pourrez tout modifier plus
              tard dans Configuration.
            </p>

            <div className="mt-9">
              <label className="mb-2 block text-[13px] font-semibold text-text">Nom de l&rsquo;entreprise</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="ex. Acme Manufacturing"
                className="w-full rounded-xl border-[1.5px] border-border-strong px-4 py-3.5 text-[17px] font-semibold outline-none focus:border-accent"
              />
            </div>

            <div className="mt-7">
              <label className="mb-2 block text-[13px] font-semibold text-text">Secteur d&rsquo;activité</label>
              <input
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="ex. Fabrication industrielle"
                className="w-full rounded-xl border-[1.5px] border-border-strong px-4 py-3 text-[14.5px] outline-none focus:border-accent"
              />
              <div className="mt-2.5 flex flex-wrap gap-2">
                {SECTOR_OPTIONS.map((opt) => (
                  <Chip key={opt} label={opt} selected={industry === opt} onClick={() => setIndustry(opt)} />
                ))}
              </div>
            </div>

            <div className="mt-7">
              <label className="mb-2 block text-[13px] font-semibold text-text">Taille de l&rsquo;entreprise</label>
              <div className="flex gap-2.5">
                {SIZE_OPTIONS.map((opt) => (
                  <Chip key={opt} label={opt} selected={size === opt} onClick={() => setSize(opt)} />
                ))}
              </div>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <h1 className="mt-3 font-display text-[32px] italic leading-tight md:text-[36px]">
              Comment est organisée
              <br />
              votre entreprise&nbsp;?
            </h1>
            <p className="mt-3.5 max-w-lg text-[15px] text-text-soft">Ces réponses déterminent les domaines que l&rsquo;IA surveille en priorité.</p>

            <div className="mt-9">
              <label className="mb-2 block text-[13px] font-semibold text-text">Pays</label>
              <div className="flex flex-wrap gap-2.5">
                {COUNTRY_OPTIONS.map((opt) => (
                  <Chip key={opt.code} label={opt.label} selected={country === opt.code} onClick={() => setCountry(opt.code)} />
                ))}
              </div>
            </div>

            <div className="mt-7">
              <label className="mb-2 block text-[13px] font-semibold text-text">Fonctions surveillées par l&rsquo;IA</label>
              <div className="grid grid-cols-2 gap-2.5">
                {DOMAIN_OPTIONS.map((opt) => (
                  <div key={opt.value} className="relative">
                    <Chip
                      label={opt.label}
                      selected={domains.includes(opt.value)}
                      onClick={opt.enabled ? () => toggleDomain(opt.value) : undefined}
                      icon={
                        domains.includes(opt.value) ? (
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                        ) : undefined
                      }
                    />
                    {!opt.enabled && <span className="pointer-events-none absolute -right-1 -top-2 rounded-full bg-surface-sunken px-1.5 py-0.5 text-[9px] font-semibold text-text-faint">bientôt</span>}
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[12px] text-text-faint">Vous pourrez ajuster ces informations à tout moment depuis Configuration.</p>
            </div>

            <div className="mt-7">
              <label className="mb-2 block text-[13px] font-semibold text-text">Votre objectif principal</label>
              <textarea
                value={objectives}
                onChange={(e) => setObjectives(e.target.value)}
                placeholder="ex. Protéger la marge sur nos produits clés et réduire la dépendance à un fournisseur unique."
                rows={3}
                className="w-full resize-none rounded-xl border-[1.5px] border-border-strong px-4 py-3 text-[13.5px] outline-none focus:border-accent"
              />
              <p className="mt-2 text-[12px] text-text-faint">Cet objectif oriente les recommandations de l&rsquo;IA.</p>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <h1 className="mt-3 font-display text-[30px] italic leading-tight md:text-[34px]">
              Quels systèmes utilisez-vous
              <br />
              aujourd&rsquo;hui&nbsp;?
            </h1>
            <p className="mt-3.5 max-w-lg text-[15px] text-text-soft">Indiquez vos outils actuels — nous préparerons les connexions correspondantes.</p>

            <div className="mt-5 flex items-center gap-2.5 rounded-xl bg-surface-sunken p-3.5">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-text-soft">
                <circle cx="12" cy="12" r="9" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <p className="text-[12.5px] text-text-soft">Ces connexions ne sont pas encore actives — vos réponses nous aident à préparer l&rsquo;intégration prochainement.</p>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3.5 sm:grid-cols-3">
              {SYSTEMS.map((sys) => (
                <div key={sys.key} className={`flex flex-col gap-2.5 rounded-2xl border-[1.5px] p-4 ${systems[sys.key] ? "border-accent bg-accent-soft" : "border-border-strong"}`}>
                  <div className="flex items-center justify-between">
                    <div className={`flex h-8 w-8 items-center justify-center rounded-[9px] ${systems[sys.key] ? "bg-accent text-white" : "bg-surface-sunken text-text-soft"}`}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2" /><line x1="3" y1="10" x2="21" y2="10" /></svg>
                    </div>
                    <Toggle on={!!systems[sys.key]} onChange={() => setSystems((s) => ({ ...s, [sys.key]: !s[sys.key] }))} label={sys.label} />
                  </div>
                  <div>
                    <p className="text-[13.5px] font-semibold text-text">{sys.label}</p>
                    <p className="mt-0.5 text-[11px] text-text-faint">{systems[sys.key] ? "Je l'utilise — connexion à venir" : "Non renseigné"}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-7 flex items-center justify-between rounded-xl border border-border px-4 py-3.5">
              <span className="text-[13px] text-text-soft">Devise utilisée dans vos données</span>
              <Badge label="EUR — Euro" tone="neutral" />
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <h1 className="mt-3 font-display text-[32px] italic leading-tight md:text-[36px]">
              Et vous, quel est
              <br />
              votre rôle&nbsp;?
            </h1>
            <p className="mt-3.5 max-w-lg text-[15px] text-text-soft">
              Le rôle détermine ce que vous voyez, ce que vous pouvez modifier et les actions que vous pouvez valider. D&rsquo;autres profils se créent ensuite dans Configuration.
            </p>

            <div className="mt-9">
              <label className="mb-2 block text-[13px] font-semibold text-text">Votre nom</label>
              <input
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                placeholder="ex. Camille Laurent"
                className="w-full rounded-xl border-[1.5px] border-border-strong px-4 py-3 text-[14.5px] outline-none focus:border-accent"
              />
            </div>

            <div className="mt-7 grid gap-2.5 sm:grid-cols-2">
              {ROLE_OPTIONS.map((opt) => (
                <button
                  key={opt.role}
                  type="button"
                  onClick={() => setRole(opt.role)}
                  aria-pressed={role === opt.role}
                  className={`rounded-xl border-[1.5px] px-4 py-3 text-left transition-colors ${role === opt.role ? "border-accent bg-accent-soft" : "border-border-strong hover:border-text-faint"}`}
                >
                  <span className={`block text-[13.5px] font-semibold ${role === opt.role ? "text-accent-strong" : "text-text"}`}>{ROLE_LABEL[opt.role]}</span>
                  <span className="mt-0.5 block text-[12px] text-text-faint">{opt.hint}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <div className="flex flex-col items-center text-center">
              <div className="animate-pop flex h-[52px] w-[52px] items-center justify-center rounded-full bg-success">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h1 className="mt-5 font-display text-[32px] italic leading-tight md:text-[36px]">
                Tout est prêt{name ? `, ${name}` : ""}.
              </h1>
              <p className="mt-2.5 max-w-md text-[14.5px] text-text-soft">
                Ces informations personnalisent vos tableaux de bord et les recommandations de l&rsquo;IA. Vous pourrez
                les modifier à tout moment dans Configuration.
              </p>
            </div>

            <div className="mt-9 divide-y divide-border rounded-2xl border border-border px-6">
              <RecapRow label="Secteur d'activité" value={industry || "Non renseigné"} />
              <RecapRow label="Votre profil" value={`${userName.trim() || "Moi"} · ${ROLE_LABEL[role]}`} />
              <RecapRow label="Taille de l'entreprise" value={size} />
              <RecapRow label="Pays" value={COUNTRY_OPTIONS.find((c) => c.code === country)?.label ?? country} />
              <RecapRow label="Fonctions surveillées" value={domains.map((d) => DOMAIN_OPTIONS.find((o) => o.value === d)?.label ?? d).join(" · ") || "Aucune"} />
              <RecapRow
                label="Systèmes à connecter"
                value={Object.entries(systems).filter(([, v]) => v).map(([k]) => SYSTEMS.find((s) => s.key === k)?.label ?? k).join(" · ") || "Aucun"}
              />
            </div>

            {error && <p className="mt-4 text-center text-[13px] text-danger">{error}</p>}
          </>
        )}

        <div className="mt-11 flex items-center justify-between">
          <div className="flex items-center gap-4">
            {step > 0 && (
              <button type="button" onClick={() => setStep((s) => s - 1)} className="flex items-center gap-1.5 text-[13.5px] font-medium text-text-soft hover:text-text">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
                Retour
              </button>
            )}
            <button type="button" onClick={skipToProduct} className="text-[13.5px] font-medium text-text-soft hover:text-text">
              Passer pour l&rsquo;instant
            </button>
          </div>

          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep((s) => s + 1)}>
              Continuer
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
            </Button>
          ) : (
            <Button onClick={finish} loading={saving}>
              Entrer dans le Centre de contrôle
              {!saving && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function RecapRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3.5">
      <span className="text-[13px] text-text-faint">{label}</span>
      <span className="text-right text-[13.5px] font-semibold text-text">{value}</span>
    </div>
  );
}
