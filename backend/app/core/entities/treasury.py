import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class BankAccount(Base, IdMixin, TimestampMixin):
    """A company account, card or loan (V2.1 director finance). NOT a bank:
    a declared balance at a date, the movements known on it, and a
    deterministic projection. Only a MASKED identifier is ever stored (last
    digits of an IBAN or card) -- never a full account or card number."""

    __tablename__ = "bank_accounts"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(160))
    # "current" | "savings" | "card" | "loan"
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="current")
    masked_identifier: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    # Balance at `balance_as_of`. A loan's balance is the outstanding principal (positive).
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    balance_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    balance_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interest_rate: Mapped[float | None] = mapped_column(Float)
    maturity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "manual" | "simulated" | "import:<file>" -- never a live bank connection in this MVP.
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")


class CashMovement(Base, IdMixin, TimestampMixin):
    """Money in or out of an account: ACTUAL (happened), PLANNED (committed:
    a loan instalment, a tax payment) or ESTIMATED (expected, not committed).
    Receivables/payables from commercial documents are NOT copied here --
    the treasury view reads them from the documents themselves."""

    __tablename__ = "cash_movements"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("bank_accounts.id"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # "in" | "out"
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # "actual" | "planned" | "estimated"
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # "customer_payment" | "supplier_payment" | "customer_refund" | "salary" | "tax" | "loan" | "rent" | "other"
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    label: Mapped[str | None] = mapped_column(String(255))
    counterparty: Mapped[str | None] = mapped_column(String(160))
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("commercial_documents.id"), nullable=True)
    # The paying/paid party. A customer payment with a customer but no
    # document is received and attributed but NOT YET reconciled with an
    # invoice ("à rapprocher"); `document_id` set = allocated to that invoice
    # (or, for a refund, to the credit note it pays back).
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")


class Shareholder(Base, IdMixin, TimestampMixin):
    """A line of the cap table. Percentages are always computed from shares;
    `economic_rights_pct` records a different economic share (e.g. carry)
    only when one has been declared."""

    __tablename__ = "shareholders"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # "founder" | "executive" | "employee" | "investor" | "other"
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="founder")
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    share_class: Mapped[str] = mapped_column(String(30), nullable=False, default="ordinaires")
    economic_rights_pct: Mapped[float | None] = mapped_column(Float)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    notes: Mapped[str | None] = mapped_column(Text)
