"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useMemo, useTransition } from "react";
import { type I18n, LOCALE_COOKIE, type Locale, createI18n } from "@/lib/i18n/core";

interface LocaleContextValue extends I18n {
  setLocale: (locale: Locale) => void;
  switching: boolean;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

// The language is the server's (the `aibos_locale` cookie read by the root
// layout): switching writes the cookie and re-renders the Server Components,
// so server-rendered text, client text and API-generated text all change
// together -- never a page half in one language.
export function LocaleProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const [switching, startTransition] = useTransition();

  const value = useMemo<LocaleContextValue>(
    () => ({
      ...createI18n(locale),
      switching,
      setLocale: (next: Locale) => {
        if (next === locale) return;
        document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
        document.documentElement.lang = next;
        startTransition(() => router.refresh());
      },
    }),
    [locale, switching, router],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useI18n must be used within a LocaleProvider");
  return ctx;
}
