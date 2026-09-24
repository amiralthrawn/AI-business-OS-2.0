import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin


class TransactionType(str, enum.Enum):
    PURCHASE_ORDER = "purchase_order"
    INVOICE = "invoice"
    SALES_ORDER = "sales_order"


class TransactionStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


class Transaction(Base, IdMixin, TimestampMixin):
    """A unified transaction record (purchase order, invoice, or sales order),
    discriminated by `type` rather than modeled as separate tables for the MVP."""

    __tablename__ = "transactions"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=True, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("products.id"), nullable=True, index=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False, index=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), nullable=False, default=TransactionStatus.DRAFT, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Promised delivery date for a purchase_order, used to measure supplier
    # delivery performance (delay = occurred_at - expected_at). Null for
    # transaction types where "delivery" doesn't apply (sales_order, invoice)
    # or where the promise date was never recorded.
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # V2: a Transaction is the posted *ledger fact* V1's analytics read; a
    # CommercialDocument is the workflow object. When a document posts a
    # fact (order confirmed, goods received) the fact points back to it, so
    # every number in Finance/Intelligence can be traced to its document.
    # Null for V1/seed transactions that predate documents.
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("commercial_documents.id"), nullable=True, index=True
    )
    source_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("commercial_document_lines.id"), nullable=True, index=True
    )
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)

    supplier: Mapped["Supplier | None"] = relationship(back_populates="transactions")
    customer: Mapped["Customer | None"] = relationship(back_populates="transactions")
    product: Mapped["Product | None"] = relationship(back_populates="transactions")
