import { cookies } from "next/headers";
import { type I18n, LOCALE_COOKIE, type Locale, createI18n, parseLocale } from "@/lib/i18n/core";

// Server side of the interface language (lib/i18n/core.ts): Server
// Components read the `aibos_locale` cookie of the incoming request.

export async function getLocale(): Promise<Locale> {
  return parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
}

export async function getI18n(): Promise<I18n> {
  return createI18n(await getLocale());
}
