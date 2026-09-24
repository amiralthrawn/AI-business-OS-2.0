import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class DocumentKind(str, enum.Enum):
    """Every commercial document of both flows lives in ONE table, discriminated
    by `kind` (V2, see brain/transactional_model.md): numbering, statuses,
    lines, parties, traceability links and the contextual API are identical
    for all of them, so ten parallel tables would only duplicate that logic.

    Sales flow:       CUSTOMER_REQUEST -> CUSTOMER_QUOTE -> CUSTOMER_ORDER -> CUSTOMER_DELIVERY / CUSTOMER_INVOICE
    Procurement flow: PURCHASE_REQUEST -> SUPPLIER_QUOTE -> PURCHASE_ORDER -> RECEPTION / SUPPLIER_INVOICE

    A CUSTOMER_REQUEST is the root of an "affaire" (a deal): both the quotes
    sent to the customer and the purchase requests it triggers derive from it."""

    CUSTOMER_REQUEST = "customer_request"
    CUSTOMER_QUOTE = "customer_quote"
    CUSTOMER_ORDER = "customer_order"
    CUSTOMER_DELIVERY = "customer_delivery"
    CUSTOMER_INVOICE = "customer_invoice"
    PURCHASE_REQUEST = "purchase_request"
    SUPPLIER_QUOTE = "supplier_quote"
    PURCHASE_ORDER = "purchase_order"
    RECEPTION = "reception"
    SUPPLIER_INVOICE = "supplier_invoice"


SALES_KINDS = frozenset(
    {
        DocumentKind.CUSTOMER_REQUEST,
        DocumentKind.CUSTOMER_QUOTE,
        DocumentKind.CUSTOMER_ORDER,
        DocumentKind.CUSTOMER_DELIVERY,
        DocumentKind.CUSTOMER_INVOICE,
    }
)
PROCUREMENT_KINDS = frozenset(
    {
        DocumentKind.PURCHASE_REQUEST,
        DocumentKind.SUPPLIER_QUOTE,
        DocumentKind.PURCHASE_ORDER,
        DocumentKind.RECEPTION,
        DocumentKind.SUPPLIER_INVOICE,
    }
)


class CommercialDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "commercial_documents"
    __table_args__ = (Index("ix_commercial_documents_company_number", "company_id", "number", unique=True),)

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    kind: Mapped[DocumentKind] = mapped_column(Enum(DocumentKind), nullable=False, index=True)
    # Internal, human-readable, unique per company (e.g. "CMD-2026-0003").
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    # Free string validated per kind by app.transactions.lifecycle (each kind
    # has its own state machine; an Enum per kind would be ten enums).
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))

    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True, index=True)

    # The other party's own number for this document (the customer's PO
    # number, the supplier's quote/order number) -- traceability both ways.
    external_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    internal_reference: Mapped[str | None] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Kind-dependent promise date: quote validity, requested/promised
    # delivery date of an order, invoice due date.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the next follow-up is due (quotes, RFQs). Read-time derived "due"
    # state -- there is no scheduler (see brain/decisions.md #33).
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the physical/financial event actually happened (goods received,
    # delivered, invoice paid) -- the OBSERVED counterpart of `due_at`.
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payment_terms: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    # "manual" | "import" | "email" | "ai" -- provenance of the document itself.
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")

    lines: Mapped[list["CommercialDocumentLine"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="CommercialDocumentLine.position"
    )
    cost_items: Mapped[list["CostItem"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class CommercialDocumentLine(Base, IdMixin, TimestampMixin):
    __tablename__ = "commercial_document_lines"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commercial_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("products.id"), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit: Mapped[str | None] = mapped_column(String(30))
    # Sale price on sales documents, purchase price on procurement documents.
    unit_price: Mapped[float | None] = mapped_column(Float)
    price_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    # Supplier-side terms as quoted on this line (supplier quotes / POs).
    lead_time_min_days: Mapped[float | None] = mapped_column(Float)
    lead_time_max_days: Mapped[float | None] = mapped_column(Float)
    lead_time_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.UNKNOWN)
    moq: Mapped[float | None] = mapped_column(Float)
    spq: Mapped[float | None] = mapped_column(Float)
    # Sales lines only: the unit cost we expected when this line was priced,
    # frozen at creation (and carried quote -> order). This is the "planned"
    # side of planned-vs-actual margin: without a snapshot, later actual
    # prices would silently overwrite what was expected.
    planned_unit_cost: Mapped[float | None] = mapped_column(Float)
    planned_cost_basis: Mapped[ValueBasis | None] = mapped_column(Enum(ValueBasis), nullable=True)
    planned_cost_source: Mapped[str | None] = mapped_column(String(120))

    document: Mapped[CommercialDocument] = relationship(back_populates="lines")
    product: Mapped["Product | None"] = relationship()


class CostKind(str, enum.Enum):
    TRANSPORT = "transport"
    CUSTOMS = "customs"
    INSURANCE = "insurance"
    HANDLING = "handling"
    OTHER = "other"


class CostItem(Base, IdMixin, TimestampMixin):
    """A cost that is not a product price (transport, customs, ...), attached
    to the document that carries it. A range (`amount_min`..`amount_max`)
    plus a `basis` so an estimated 300-450 EUR transport is never shown as a
    real 375 EUR one; `amount_min == amount_max` for an exact amount."""

    __tablename__ = "cost_items"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commercial_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("commercial_document_lines.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[CostKind] = mapped_column(Enum(CostKind), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    amount_min: Mapped[float] = mapped_column(Float, nullable=False)
    amount_max: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    # Carrier name, tracking or transport-order number -- the trace of where
    # this cost comes from.
    reference: Mapped[str | None] = mapped_column(String(120))

    document: Mapped[CommercialDocument] = relationship(back_populates="cost_items")
