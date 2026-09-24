import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class RelatedEntityType(str, enum.Enum):
    """The Data Core entities that a polymorphic record can attach to."""

    COMPANY = "company"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    PRODUCT = "product"
    TRANSACTION = "transaction"
    # V2: the business objects a Task/Risk/Contact/Communication can now
    # point at directly (e.g. a follow-up Task on a quote, a draft email).
    CONTACT = "contact"
    COMMUNICATION = "communication"
    COMMERCIAL_DOCUMENT = "commercial_document"
    # V2.1: people objects a Task can point at (a promotion proposal, an interview).
    EMPLOYEE = "employee"
    CANDIDATE = "candidate"


class ValueBasis(str, enum.Enum):
    """Where a value comes from (V2). Never collapsed: an ESTIMATED 14 days is
    not an OBSERVED 14 days, and the UI must be able to say which one it is.

    - OBSERVED: measured from real records (an invoice, a reception date).
    - DECLARED: stated by a party (a supplier quote, a catalog price, a PO).
    - ESTIMATED: computed/assumed by us (a reference unit cost, a transport guess).
    - BENCHMARK: a generic market/sector reference, not specific to this case.
    - SIMULATED: demonstration data, not from the company's real systems.
    - UNKNOWN: no usable source -- shown as unknown, never filled in."""

    OBSERVED = "observed"
    DECLARED = "declared"
    ESTIMATED = "estimated"
    BENCHMARK = "benchmark"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


class LinkableMixin:
    """Prototype compromise: a generic (type, id) pointer instead of a per-target
    foreign key, so Document/Communication/Task/Risk/Opportunity can attach to any
    Data Core entity without one join table per pair. The database cannot enforce
    a foreign key across several possible target tables, so referential integrity
    here is an application-level responsibility, not a database guarantee.
    """

    related_entity_type: Mapped[RelatedEntityType | None] = mapped_column(
        Enum(RelatedEntityType), nullable=True, index=True
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
