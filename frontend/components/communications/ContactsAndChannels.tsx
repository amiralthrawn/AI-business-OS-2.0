import { CampaignPerformancePanel } from "@/components/communications/Performance";
import ContactSummaryCard from "@/components/data/ContactSummaryCard";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import ErrorBanner from "@/components/ui/ErrorBanner";
import { getCampaignPerformance, getConnectors, getContacts } from "@/lib/api";
import { formatDateFR } from "@/lib/labels";
import type { ConnectorStatus, ContactListItem } from "@/lib/types";

// Only "email" and "website" have a real (mock) connector registered in the
// backend (app/connectors/registry.py) -- LinkedIn/Facebook/Email marketing
// have none. Never claim a connection that doesn't exist (Step 28 §4):
// those three always render "Connexion non configurée".
const CHANNEL_WIDGETS: { key: string; label: string }[] = [
  { key: "email", label: "Email" },
  { key: "website", label: "Site web" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "facebook", label: "Facebook" },
  { key: "email_marketing", label: "Email marketing" },
];

function ChannelWidget({ label, status }: { label: string; status: ConnectorStatus | undefined }) {
  const connected = !!status;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold text-[13.5px] text-text">{label}</p>
        <Badge label={connected ? "Démonstration" : "Non configuré"} tone={connected ? "warning" : "neutral"} />
      </div>
      {connected ? (
        <div className="mt-2.5 space-y-0.5">
          <p className="text-[12.5px] text-text-soft">
            <span className="num">{status.ingested_count}</span> message{status.ingested_count !== 1 ? "s" : ""} de démonstration (fournisseur simulé, aucun compte réel)
          </p>
          <p className="text-[11.5px] text-text-faint">
            {status.last_ingested_at ? `Dernier le ${formatDateFR(status.last_ingested_at)}` : "Aucun message pour l'instant"}
          </p>
        </div>
      ) : (
        <p className="mt-2.5 text-[12.5px] text-text-faint">Aucune connexion réelle configurée pour ce canal.</p>
      )}
    </Card>
  );
}

async function load() {
  const [contacts, connectors, campaigns] = await Promise.all([
    getContacts(),
    getConnectors().then((r) => r.connectors),
    getCampaignPerformance().catch(() => null),
  ]);
  return { contacts, connectors, campaigns };
}

// V2: formerly the /data/contacts page (Step 28), now two tabs of the
// Communications hub -- the same content and honesty rules, one place for
// every exchange with the outside world.
export async function ChannelsPanel() {
  let data: Awaited<ReturnType<typeof load>>;
  try {
    data = await load();
  } catch (err) {
    return <ErrorBanner message={err instanceof Error ? err.message : "Impossible de charger les canaux."} />;
  }
  const statusByConnector = new Map(data.connectors.map((c: ConnectorStatus) => [c.connector, c]));
  return (
    <div className="space-y-10">
      <section>
        <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Canaux</span>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CHANNEL_WIDGETS.map((w) => (
            <ChannelWidget key={w.key} label={w.label} status={statusByConnector.get(w.key)} />
          ))}
        </div>
      </section>

      <section>
        <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Performance des campagnes</span>
        {data.campaigns ? <CampaignPerformancePanel data={data.campaigns} /> : <EmptyState message="Campagnes indisponibles." />}
      </section>
    </div>
  );
}

export async function PeoplePanel() {
  let contacts: ContactListItem[] = [];
  try {
    contacts = await getContacts();
  } catch (err) {
    return <ErrorBanner message={err instanceof Error ? err.message : "Impossible de charger les contacts."} />;
  }
  return (
    <section>
      <span className="mb-4 block text-[11.5px] font-bold tracking-wide text-text-faint uppercase">Personnes ({contacts.length})</span>
      {contacts.length === 0 ? (
        <EmptyState message="Aucun contact pour l'instant." hint="Les contacts apparaissent ici dès qu'ils sont liés à un fournisseur ou un client." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {contacts.map((c) => (
            <ContactSummaryCard key={c.id} contact={c} />
          ))}
        </div>
      )}
    </section>
  );
}
