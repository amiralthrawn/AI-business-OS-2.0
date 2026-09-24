"use client";

import Link from "next/link";
import CreateTaskButton from "@/components/actions/CreateTaskButton";
import EmailComposer from "@/components/shared/EmailComposer";
import Card from "@/components/ui/Card";
import { formatDateFR } from "@/lib/labels";
import { entityHref } from "@/lib/related-entity";
import type { ContactListItem } from "@/lib/types";

// Same real actions as components/data/ContactCard, plus the linked
// entity and last-communication summary the Contacts page (Step 28's
// communication center) needs but the Supplier/Customer detail pages
// already show elsewhere -- kept as a separate component rather than
// overloading ContactCard's simpler (LinkedContact) contract.
export default function ContactSummaryCard({ contact }: { contact: ContactListItem }) {
  const href =
    contact.related_entity_type && contact.related_entity_id ? entityHref(contact.related_entity_type, contact.related_entity_id) : null;

  return (
    <Card className="p-5">
      <p className="font-semibold text-[14.5px] text-text">{contact.name}</p>
      <p className="mt-0.5 text-[12.5px] text-text-faint">
        {contact.role ?? "Rôle inconnu"}
        {contact.related_entity_name &&
          (href ? (
            <>
              {" "}
              &middot;{" "}
              <Link href={href} className="hover:underline">
                {contact.related_entity_name}
              </Link>
            </>
          ) : (
            <> &middot; {contact.related_entity_name}</>
          ))}
      </p>

      {contact.last_communication ? (
        <p className="mt-3 text-[12.5px] text-text-soft">
          Dernier échange&nbsp;: {contact.last_communication.subject ?? "sans objet"} &middot; <span className="num">{formatDateFR(contact.last_communication.occurred_at)}</span>
        </p>
      ) : (
        <p className="mt-3 text-[12.5px] text-text-faint">Aucun échange enregistré.</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {contact.email && (
          <EmailComposer
            to={contact.email}
            toName={contact.name}
            defaultSubject={`Contact — ${contact.name}`}
            defaultBody={`Bonjour ${contact.name.split(" ")[0]},\n\n`}
          />
        )}
        <CreateTaskButton
          defaultTitle={`Contacter ${contact.name}`}
          relatedEntityType={contact.related_entity_type ?? undefined}
          relatedEntityId={contact.related_entity_id ?? undefined}
        />
      </div>
    </Card>
  );
}
