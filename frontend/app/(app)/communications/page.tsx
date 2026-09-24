import Link from "next/link";
import { ChannelsPanel, PeoplePanel } from "@/components/communications/ContactsAndChannels";
import DraftEditor from "@/components/communications/DraftEditor";
import Mailboxes from "@/components/communications/Mailboxes";
import { FollowUpPerformancePanel } from "@/components/communications/Performance";
import EmailAssistant from "@/components/communications/EmailAssistant";
import WebsitePanel from "@/components/communications/WebsitePanel";
import FollowUpList from "@/components/objects/FollowUpList";
import ObjectSignals from "@/components/objects/ObjectSignals";
import RelatedObjects from "@/components/objects/RelatedObjects";
import WorkspaceTabs from "@/components/objects/WorkspaceTabs";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";
import { getCommunication, getFollowUpPerformance, getFollowUps, getMailboxes, getMe, getObjectContext, getWebsite, listCommunications, listMailbox } from "@/lib/api";
import { formatDateFR, formatTimeFR } from "@/lib/labels";
import { can } from "@/lib/objects";
import type { CommunicationRow, MailboxRow } from "@/lib/types";

export const dynamic = "force-dynamic";

const TABS = [
  { key: "mailboxes", label: "Boîtes" },
  { key: "inbox", label: "Réception" },
  { key: "sent", label: "Envoyés" },
  { key: "drafts", label: "Brouillons & validation" },
  { key: "followups", label: "Relances & suivi" },
  { key: "contacts", label: "Contacts" },
  { key: "channels", label: "Canaux & campagnes" },
  { key: "website", label: "Site web & SEO" },
];
const CHANNELS = [
  { key: "", label: "Tous" },
  { key: "email", label: "Email" },
  { key: "website", label: "Site web" },
  { key: "calendar", label: "Rendez-vous" },
];
const STATUS_LABEL: Record<string, { label: string; tone: "warning" | "success" | "accent" | "neutral" }> = {
  draft: { label: "Brouillon", tone: "accent" },
  pending_validation: { label: "À valider", tone: "warning" },
  rejected: { label: "Refusé", tone: "neutral" },
  sent: { label: "Envoyé", tone: "success" },
};

function href(params: Record<string, string | undefined>) {
  const search = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
  return `/communications?${search.toString()}`;
}

// Communications hub (V2): every exchange (email, website, appointments) as a
// business object linked to the customers, suppliers, quotes and orders it
// concerns, with AI assistance that prepares and never sends on its own.
export default async function CommunicationsPage({ searchParams }: { searchParams: Promise<{ tab?: string; message?: string; channel?: string; box?: string }> }) {
  const sp = await searchParams;
  const tab = TABS.some((t) => t.key === sp.tab) ? sp.tab! : "mailboxes";
  const me = await getMe().catch(() => null);
  const canWrite = can(me?.permissions, "write:communications");

  const box = tab === "sent" ? "sent" : tab === "drafts" ? "drafts" : "inbox";
  const inMailboxes = tab === "mailboxes";
  const listing = ["inbox", "sent", "drafts"].includes(tab) || (inMailboxes && Boolean(sp.box || sp.message));
  const [messages, followUps, performance, overview] = await Promise.all([
    inMailboxes
      ? sp.box
        ? listMailbox(sp.box).catch(() => [] as MailboxRow[])
        : Promise.resolve([] as MailboxRow[])
      : listing
        ? listCommunications(box, sp.channel || undefined).catch(() => [] as CommunicationRow[])
        : Promise.resolve([] as CommunicationRow[]),
    tab === "followups" ? getFollowUps().catch(() => null) : Promise.resolve(null),
    tab === "followups" ? getFollowUpPerformance().catch(() => null) : Promise.resolve(null),
    inMailboxes ? getMailboxes().catch(() => null) : Promise.resolve(null),
  ]);
  const rows = messages as (CommunicationRow & Partial<Pick<MailboxRow, "needs_reply" | "mailbox_reason">>)[];

  return (
    <main className="space-y-8 p-8 md:p-12">
      <PageHeader title="Communications" description="Emails, demandes du site et rendez-vous — reliés aux clients, fournisseurs, devis et commandes qu'ils concernent." />
      <WorkspaceTabs active={tab} tabs={TABS.map((t) => ({ ...t, href: href({ tab: t.key }) }))} />

      {inMailboxes && (overview ? <Mailboxes overview={overview} active={sp.box} href={(key) => href({ tab, box: key })} /> : <EmptyState message="Boîtes indisponibles." />)}

      {listing && (
        <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_1fr]">
          <div className="space-y-3">
            {tab === "inbox" && (
              <div className="flex flex-wrap gap-1.5">
                {CHANNELS.map((c) => (
                  <Link key={c.key} href={href({ tab, channel: c.key || undefined })} className={`rounded-lg px-2.5 py-1 text-[12px] ${(sp.channel ?? "") === c.key ? "bg-accent-soft font-semibold text-accent-strong" : "text-text-soft hover:bg-surface-sunken"}`}>
                    {c.label}
                  </Link>
                ))}
              </div>
            )}
            {inMailboxes && !sp.box ? (
              <EmptyState message="Choisissez une boîte." hint="Chaque boîte regroupe les messages existants selon une règle affichée." />
            ) : rows.length === 0 ? (
              <EmptyState message={tab === "drafts" ? "Aucun brouillon." : inMailboxes ? "Aucun message dans cette boîte." : "Aucun message."} hint={tab === "drafts" ? "Préparez un email depuis un devis, une commande, un fournisseur ou une relance." : undefined} />
            ) : (
              <ul className="space-y-1.5">
                {rows.map((m) => (
                  <li key={m.id}>
                    <Link
                      href={href({ tab, channel: sp.channel, box: sp.box, message: m.id })}
                      className={`block rounded-xl border px-4 py-3 transition-colors ${sp.message === m.id ? "border-accent bg-accent-soft/40" : "border-border bg-surface hover:border-border-strong"}`}
                    >
                      <div className="flex items-center justify-between gap-2 text-[11.5px] text-text-faint">
                        <span className="truncate">{m.direction === "inbound" ? m.contact?.name ?? m.from_address : `À ${m.to_address ?? "—"}`}</span>
                        <span className="num shrink-0">{formatDateFR(m.occurred_at)}</span>
                      </div>
                      <p className="mt-0.5 truncate text-[13.5px] font-medium text-text">{m.subject ?? "(sans objet)"}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {m.party && <span className="text-[12px] text-text-soft">{m.party.title}</span>}
                        {m.channel !== "email" && <Badge label={m.channel === "website" ? "Site web" : m.channel === "calendar" ? "Rendez-vous" : m.channel} tone="neutral" />}
                        {STATUS_LABEL[m.status] && tab !== "sent" && <Badge label={STATUS_LABEL[m.status].label} tone={STATUS_LABEL[m.status].tone} />}
                        {m.needs_reply && <Badge label="Sans réponse" tone="warning" />}
                      </div>
                      {m.mailbox_reason && <p className="mt-1 text-[11px] text-text-faint">Classé : {m.mailbox_reason}</p>}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>{sp.message ? <MessagePane id={sp.message} canWrite={canWrite} canSubmit={can(me?.permissions, "action:submit_email")} /> : <EmptyState message="Sélectionnez un message." hint="Vous verrez à quoi il est lié, l'historique de l'échange et ce que l'IA peut préparer." />}</div>
        </div>
      )}

      {tab === "followups" && performance && <FollowUpPerformancePanel perf={performance} />}
      {tab === "followups" && followUps && <FollowUpList items={followUps.items} note={followUps.note} canDraft={canWrite} />}
      {tab === "contacts" && <PeoplePanel />}
      {tab === "channels" && <ChannelsPanel />}
      {tab === "website" && <Website canWrite={canWrite} canConfigure={can(me?.permissions, "write:settings")} />}
    </main>
  );
}

async function MessagePane({ id, canWrite, canSubmit }: { id: string; canWrite: boolean; canSubmit: boolean }) {
  let message;
  try {
    message = await getCommunication(id);
  } catch {
    return <EmptyState message="Message introuvable." />;
  }
  const context = await getObjectContext("communication", id).catch(() => null);
  const isDraft = ["draft", "pending_validation", "rejected"].includes(message.status);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <p className="text-[11.5px] uppercase tracking-wide text-text-faint">
          {message.direction === "inbound" ? "Reçu" : isDraft ? "Brouillon" : "Envoyé"} · <span className="num">{formatDateFR(message.occurred_at)} {formatTimeFR(message.occurred_at)}</span>
          {message.source === "mock_email" && message.direction === "outbound" && " · envoi simulé (démonstration)"}
          {message.source?.startsWith("simulated") && " · message simulé (démonstration)"}
        </p>
        <h2 className="mt-1.5 font-display text-[22px] italic text-text">{message.subject ?? "(sans objet)"}</h2>
        <p className="mt-1.5 text-[13px] text-text-soft">
          {message.direction === "inbound" ? `De ${message.contact?.name ?? message.from_address ?? "expéditeur inconnu"}` : `À ${message.to_address ?? "destinataire à renseigner"}`}
          {message.party && (
            <>
              {" · "}
              <Link href={message.party.href ?? "#"} className="font-medium text-text hover:underline">{message.party.title}</Link> <span className="text-text-faint">({message.party.kind_label})</span>
            </>
          )}
        </p>
        {!isDraft && message.body && <p className="mt-4 whitespace-pre-line text-[13.5px] leading-relaxed text-text">{message.body}</p>}
      </Card>

      {isDraft ? <DraftEditor key={message.id} draft={message} canWrite={canWrite} canSubmit={canSubmit} /> : <EmailAssistant message={message} canWrite={canWrite} />}

      {context && <ObjectSignals signals={context.intelligence} />}
      {context && <RelatedObjects groups={context.related} title="Lié à" />}

      {message.thread.length > 0 && (
        <section>
          <p className="mb-2 text-[12.5px] font-semibold text-text-soft">Dans le même échange</p>
          <ul className="space-y-1.5">
            {message.thread.map((t) => (
              <li key={t.id}>
                <Link href={href({ tab: t.direction === "inbound" ? "inbox" : "sent", message: t.id })} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-2.5 text-[13px] hover:border-border-strong">
                  <span className="truncate">{t.subject ?? "(sans objet)"}</span>
                  <span className="shrink-0 text-[11.5px] text-text-faint">{t.direction === "inbound" ? "reçu" : "envoyé"} · <span className="num">{formatDateFR(t.occurred_at)}</span></span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

async function Website({ canWrite, canConfigure }: { canWrite: boolean; canConfigure: boolean }) {
  const state = await getWebsite().catch(() => null);
  if (!state) return <EmptyState message="Analyse du site indisponible." />;
  return <WebsitePanel initial={state} canWrite={canWrite} canConfigure={canConfigure} />;
}
