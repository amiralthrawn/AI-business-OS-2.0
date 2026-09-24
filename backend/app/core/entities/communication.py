import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, LinkableMixin, TimestampMixin


class CommunicationDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Communication(Base, IdMixin, TimestampMixin, LinkableMixin):
    __tablename__ = "communications"
    __table_args__ = (Index("ix_communications_source_external_id", "source", "external_id", unique=True),)

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[CommunicationDirection] = mapped_column(Enum(CommunicationDirection), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Provenance for anything ingested by app.connectors (step 21) -- `None`
    # for a Communication created directly (e.g. by a human, or the seed
    # script's own demonstrative rows predating connectors). `source` names
    # the connector+provider (e.g. "mock_email"); `external_id` is that
    # provider's own id for the record, unique together so a second sync
    # of the same external item is a no-op rather than a duplicate row --
    # never real personal data, just an opaque provider-assigned id.
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A sub-classification of `channel`, when the originating system provides
    # one (step 23B) -- e.g. a WebsiteInquiry's own `source` ("contact_form"
    # vs "quote_form"), which the ingestion layer was previously discarding
    # (a real gap found by the step 23 audit). Deliberately generic, not a
    # "lead source" or Marketing field: just one more fact from the external
    # object, carried through instead of dropped. `None` whenever the
    # originating system doesn't distinguish sub-types.
    channel_detail: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # V2 email workflow. `status`: "received" | "sent" | "draft" |
    # "pending_validation" | "rejected". A draft is a Communication row from
    # the start, so its links to quotes/orders/contacts exist before sending.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received", server_default="received", index=True)
    # The person on the other side (V1 gap: a Communication only knew its
    # Supplier/Customer, never who wrote it -- brain/frontend_api_contract.md).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True, index=True)
    from_address: Mapped[str | None] = mapped_column(String(255))
    to_address: Mapped[str | None] = mapped_column(String(500))
    thread_key: Mapped[str | None] = mapped_column(String(255), index=True)
    # Which assisted workflow produced a draft ("follow_up", "rfq_price", ...).
    purpose: Mapped[str | None] = mapped_column(String(40))
