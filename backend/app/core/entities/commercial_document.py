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
    Credit notes:     CUSTOMER_CREDIT_NOTE (from an order, delivery or invoice),
                      SUPPLIER_CREDIT_NOTE (a claim, from a PO, reception or supplier invoice)

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
    CUSTOMER_CREDIT_NOTE = "customer_credit_note"
    SUPPLIER_CREDIT_NOTE = "supplier_credit_note"


SALES_KINDS = frozenset(
    {
        DocumentKind.CUSTOMER_REQUEST,
        DocumentKind.CUSTOMER_QUOTE,
        DocumentKind.CUSTOMER_ORDER,
        DocumentKind.CUSTOMER_DELIVERY,
        DocumentKind.CUSTOMER_INVOICE,
        DocumentKind.CUSTOMER_CREDIT_NOTE,
    }
)
PROCUREMENT_KINDS = frozenset(
    {
        DocumentKind.PURCHASE_REQUEST,
        DocumentKind.SUPPLIER_QUOTE,
        DocumentKind.PURCHASE_ORDER,
        DocumentKind.RECEPTION,
        DocumentKind.SUPPLIER_INVOICE,
        DocumentKind.SUPPLIER_CREDIT_NOTE,
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
    # Deliveries / receptions: who carries the goods and their tracking
    # number, when known (declared by the carrier or the other party).
    carrier: Mapped[str | None] = mapped_column(String(120))
    tracking_number: Mapped[str | None] = mapped_column(String(120))
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
    # Deliveries / receptions only: part of `quantity` found non-conforming
    # on inspection, and what was wrong. Recorded by a person (never inferred).
    quantity_nonconforming: Mapped[float | None] = mapped_column(Float)
    nonconformity_note: Mapped[str | None] = mapped_column(String(255))

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


class PaymentInstallment(Base, IdMixin, TimestampMixin):
    """One due date of an invoice's payment schedule (an instalment, a
    deposit, the balance...). Terms are free per invoice -- no rule assumes a
    number of instalments. An invoice without rows is due in one payment at
    its `due_at`. The amounts of one invoice's rows add up to its total
    (checked by app.billing when the schedule is set)."""

    __tablename__ = "payment_installments"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commercial_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str | None] = mapped_column(String(120))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)


class CreditApplication(Base, IdMixin, TimestampMixin):
    """How a validated credit note was imputed -- written ONCE (unique per
    credit note), so a credit note can never be deducted twice.
    `applied_amount` reduced the invoice's receivable/payable;
    `refund_amount` exceeded what was still owed and must be paid back
    (recorded later as a real CashMovement)."""

    __tablename__ = "credit_applications"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commercial_documents.id"), nullable=False, unique=True, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("commercial_documents.id"), nullable=True, index=True)
    applied_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    refund_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
