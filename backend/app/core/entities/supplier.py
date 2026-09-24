import uuid

from sqlalchemy import JSON, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin


class Supplier(Base, IdMixin, TimestampMixin):
    __tablename__ = "suppliers"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120))
    # V2: supplier-level DECLARED terms (a product-level ProductSupplier row
    # overrides them). Performance is never stored here: it is OBSERVED,
    # computed from real purchase orders by app.core.analytics.
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    certifications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # V2.1: an outside expert is a supplier of services, not a new entity.
    # "goods" (default) | "law_firm" | "accounting_firm" | "insurance_advisor" | "expert".
    supplier_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="goods", server_default="goods")
    # DECLARED hourly fee range of an expert, used to estimate a request's fees.
    fee_rate_min: Mapped[float | None] = mapped_column(Float)
    fee_rate_max: Mapped[float | None] = mapped_column(Float)

    company: Mapped["Company"] = relationship(back_populates="suppliers")
    products: Mapped[list["Product"]] = relationship(back_populates="supplier")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="supplier")
