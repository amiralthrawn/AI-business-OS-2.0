"""Ingestion / Mapping: the one place a normalized external object (from any
provider, mock or real) is turned into Data Core rows.

    Connector -> fetch -> normalize -> ingest -> Data Core

Deterministic and idempotent: re-running ingestion for the same external
item is a no-op (matched by `(source, external_id)` on Communication/
Document), never a duplicate. Contains no business intelligence -- it does
not classify, prioritize or decide anything about what it imports; that is
Observation/Interpretation/Decision's job, run separately and later, not
triggered by this module.

Entity resolution is deliberately conservative: an inbound email/inquiry
only ever links to an EXISTING Supplier/Customer when its email domain (or,
for a Website inquiry, its stated company name) reliably matches an
existing one -- normalized, substring-based, never fuzzy. No Supplier,
Customer or Opportunity is ever created from this data. When nothing
matches, the Contact is left genuinely unresolved (`related_entity_type`/
`related_entity_id` both `None`) rather than guessed -- see brain/connectors.md.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.connectors.base import SyncResult
from app.connectors.calendar.base import CalendarProvider
from app.connectors.email.base import EmailProvider
from app.connectors.website.base import WebsiteProvider
from app.core.entities import Communication, CommunicationDirection, Contact, Customer, Document, RelatedEntityType, Supplier

DEFAULT_CALENDAR_WINDOW = timedelta(days=30)

_MIN_MATCH_LENGTH = 4  # avoids a too-short slug (e.g. "the") matching broadly


def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _email_domain_slug(email: str) -> str:
    domain = email.rsplit("@", 1)[-1]
    first_label = domain.split(".")[0]
    return _normalize(first_label)


def _match_known_entity(
    session: Session, company_id: uuid.UUID, *, email: str, company_hint: str | None = None
) -> tuple[RelatedEntityType, uuid.UUID] | tuple[None, None]:
    """A reliable-only match: the email's domain, or an explicitly stated
    company name, must appear as a substring of (or contain) an existing
    Supplier/Customer's own name. Never creates anything; returns
    `(None, None)` -- an honestly unresolved identity -- when nothing
    matches with enough confidence."""

    candidates = [_email_domain_slug(email)]
    if company_hint:
        candidates.append(_normalize(company_hint))
    candidates = [c for c in candidates if len(c) >= _MIN_MATCH_LENGTH]
    if not candidates:
        return None, None

    for supplier in session.query(Supplier).filter_by(company_id=company_id).all():
        normalized = _normalize(supplier.name)
        if any(c in normalized or normalized in c for c in candidates):
            return RelatedEntityType.SUPPLIER, supplier.id

    for customer in session.query(Customer).filter_by(company_id=company_id).all():
        normalized = _normalize(customer.name)
        if any(c in normalized or normalized in c for c in candidates):
            return RelatedEntityType.CUSTOMER, customer.id

    return None, None


def _resolve_contact(
    session: Session, company_id: uuid.UUID, *, name: str | None, email: str, company_hint: str | None = None
) -> Contact:
    """Finds the existing Contact for this external identity (matched by
    email within the company) or creates one -- resolved to a Supplier/
    Customer when `_match_known_entity` finds one, left as an unresolved
    external contact otherwise. Never creates a Supplier, Customer or
    Opportunity."""

    existing = session.query(Contact).filter_by(company_id=company_id, email=email).first()
    if existing is not None:
        return existing

    related_entity_type, related_entity_id = _match_known_entity(session, company_id, email=email, company_hint=company_hint)
    contact = Contact(
        company_id=company_id,
        name=name or email,
        email=email,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    session.add(contact)
    session.commit()
    return contact


def _already_ingested(session: Session, model, source: str, external_id: str) -> bool:
    return session.query(model).filter_by(source=source, external_id=external_id).first() is not None


def ingest_email(session: Session, provider: EmailProvider, company_id: uuid.UUID) -> SyncResult:
    source = "mock_email"
    messages = provider.list_messages()
    created = 0
    skipped = 0

    for message in messages:
        if _already_ingested(session, Communication, source, message.external_id):
            skipped += 1
            continue

        counterparty_email = message.sender if message.direction == "inbound" else (
            message.recipients[0] if message.recipients else message.sender
        )
        contact = _resolve_contact(session, company_id, name=None, email=counterparty_email)

        communication = Communication(
            company_id=company_id,
            channel="email",
            direction=CommunicationDirection.INBOUND if message.direction == "inbound" else CommunicationDirection.OUTBOUND,
            subject=message.subject,
            body=message.body,
            occurred_at=message.timestamp,
            related_entity_type=contact.related_entity_type,
            related_entity_id=contact.related_entity_id,
            source=source,
            external_id=message.external_id,
            # V2 email workflow fields: who, which thread, sent vs received.
            status="received" if message.direction == "inbound" else "sent",
            contact_id=contact.id,
            from_address=message.sender,
            to_address=", ".join(message.recipients),
            thread_key=message.thread_id,
        )
        session.add(communication)

        for filename in message.attachments:
            session.add(
                Document(
                    company_id=company_id,
                    title=filename,
                    document_type="email_attachment",
                    related_entity_type=contact.related_entity_type,
                    related_entity_id=contact.related_entity_id,
                    source=source,
                    external_id=f"{message.external_id}:{filename}",
                )
            )
        created += 1

    session.commit()
    return SyncResult(connector="email", fetched=len(messages), created=created, updated=0, skipped=skipped)


def ingest_calendar(
    session: Session,
    provider: CalendarProvider,
    company_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SyncResult:
    source = "mock_calendar"
    now = datetime.now(timezone.utc)
    start = start or (now - DEFAULT_CALENDAR_WINDOW)
    end = end or (now + DEFAULT_CALENDAR_WINDOW)

    events = provider.list_events(start, end)
    created = 0
    skipped = 0

    for event in events:
        if _already_ingested(session, Communication, source, event.external_id):
            skipped += 1
            continue

        related_entity_type, related_entity_id = None, None
        for attendee_email in event.attendees:
            contact = _resolve_contact(session, company_id, name=None, email=attendee_email)
            if contact.related_entity_type is not None:
                related_entity_type, related_entity_id = contact.related_entity_type, contact.related_entity_id
                break

        session.add(
            Communication(
                company_id=company_id,
                channel="calendar",
                # A calendar event isn't inherently inbound/outbound the way
                # a message is; OUTBOUND ("the company's own recorded
                # activity") is used consistently for every calendar-sourced
                # Communication -- an arbitrary but documented convention
                # (see brain/connectors.md), not a judgment about the event.
                direction=CommunicationDirection.OUTBOUND,
                subject=event.title,
                body=event.description,
                occurred_at=event.start,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
                source=source,
                external_id=event.external_id,
                status="sent",
            )
        )
        created += 1

    session.commit()
    return SyncResult(connector="calendar", fetched=len(events), created=created, updated=0, skipped=skipped)


def ingest_website(session: Session, provider: WebsiteProvider, company_id: uuid.UUID) -> SyncResult:
    source = "mock_website"
    inquiries = provider.list_inquiries()
    created = 0
    skipped = 0

    for inquiry in inquiries:
        if _already_ingested(session, Communication, source, inquiry.external_id):
            skipped += 1
            continue

        contact = _resolve_contact(
            session, company_id, name=inquiry.name, email=inquiry.email, company_hint=inquiry.company
        )

        session.add(
            Communication(
                company_id=company_id,
                channel="website",
                direction=CommunicationDirection.INBOUND,
                subject=inquiry.subject,
                body=inquiry.message,
                occurred_at=inquiry.timestamp,
                related_entity_type=contact.related_entity_type,
                related_entity_id=contact.related_entity_id,
                source=source,
                external_id=inquiry.external_id,
                # The inquiry's own sub-classification (e.g. "contact_form"
                # vs "quote_form") -- previously discarded here, a real gap
                # found by the step 23 audit (see brain/business_domains.md).
                channel_detail=inquiry.source,
                status="received",
                contact_id=contact.id,
            )
        )
        created += 1
        # Closes the loop with the source system after a successful import --
        # bookkeeping for the external system, not a business decision about
        # the inquiry itself (which stays entirely unclassified here).
        provider.mark_processed(inquiry.external_id)

    session.commit()
    return SyncResult(connector="website", fetched=len(inquiries), created=created, updated=0, skipped=skipped)


def sync_connector(session: Session, connector_type: str, provider: object, company_id: uuid.UUID) -> SyncResult:
    """The one dispatcher `POST /connectors/{type}/sync` calls: provider ->
    fetch -> normalize -> ingest -> summary, generic over which connector
    type it's given."""

    if connector_type == "email":
        return ingest_email(session, provider, company_id)
    if connector_type == "calendar":
        return ingest_calendar(session, provider, company_id)
    if connector_type == "website":
        return ingest_website(session, provider, company_id)
    raise KeyError(f"Unknown connector type: '{connector_type}'")
