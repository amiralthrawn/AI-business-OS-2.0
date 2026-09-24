import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
// Registers the server-side profile resolver used by lib/api.ts (V2 roles).
import "@/lib/server-user";

const fraunces = Fraunces({
  variable: "--font-display-src",
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
});

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: "--font-body-src",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono-src",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "AI Business OS",
  description: "Système d'exploitation d'entreprise piloté par l'IA",
};

// Deliberately minimal: fonts and the html/body shell only. The Sidebar/
// Topbar chrome lives in app/(app)/layout.tsx so that routes outside that
// group -- Onboarding -- render full-screen, with no product chrome around
// a setup wizard the user hasn't gone through yet.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${fraunces.variable} ${plusJakartaSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-bg text-text">{children}</body>
    </html>
  );
}
