import Link from "next/link";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import { formatDateFR } from "@/lib/labels";
import type { Mailbox, MailboxOverview } from "@/lib/types";

// Honest status: "connected" only when a real provider delivered to the
// address (never today -- every registered provider is a demo one).
export const MAILBOX_STATUS: Record<Mailbox["status"], { label: string; tone: "success" | "warning" | "neutral" }> = {
  connected: { label: "Connectée", tone: "success" },
  demo: { label: "Démonstration", tone: "warning" },
  not_configured: { label: "Non configurée", tone: "neutral" },
};

// Functional mailboxes (brain/communications.md "Boîtes fonctionnelles"): a
// classification of the messages already in the base, by role. The address
// (sales@, rfq@…) names the role; no real mailbox is claimed or connected.
export default function Mailboxes({ overview, active, href }: { overview: MailboxOverview; active?: string; href: (box: string) => string }) {
  const groups = Array.from(new Set(overview.mailboxes.map((m) => m.group)));
  const demoProviders = overview.providers.filter((p) => p.demo).map((p) => p.connector);
  return (
    <section className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {groups.flatMap((g) =>
          overview.mailboxes
            .filter((m) => m.group === g)
            .map((m) => {
              const st = MAILBOX_STATUS[m.status];
              return (
                <Link key={m.key} href={href(m.key)} className="group">
                  <Card className={`h-full p-4 transition-colors ${active === m.key ? "border-accent bg-accent-soft/40" : "group-hover:border-border-strong"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-text-faint">{m.group}</p>
                      <Badge label={st.label} tone={st.tone} />
                    </div>
                    <p className="mt-1.5 flex items-baseline gap-2">
                      <span className="num text-[15px] font-semibold text-text">{m.address}</span>
                      <span className="truncate text-[12.5px] text-text-soft">{m.label}</span>
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-text-soft">
                      <span>
                        <span className="num font-semibold text-text">{m.message_count}</span> message{m.message_count !== 1 ? "s" : ""}
                      </span>
                      <span className={m.awaiting_reply > 0 ? "text-warning" : ""}>
                        <span className="num font-semibold">{m.awaiting_reply}</span> sans réponse
                      </span>
                      {m.last_at && (
                        <span className="text-text-faint">
                          dernier le <span className="num">{formatDateFR(m.last_at)}</span>
                        </span>
                      )}
                    </div>
                  </Card>
                </Link>
              );
            }),
        )}
      </div>
      <p className="text-[11.5px] leading-relaxed text-text-faint">
        {overview.method} Les adresses indiquent un rôle, pas une boîte existante
        {demoProviders.length ? ` ; fournisseurs actifs : démonstration (${demoProviders.join(", ")})` : ""}. Rendez-vous et notes internes ({overview.excluded_count}) ne sont pas classés.
      </p>
    </section>
  );
}
