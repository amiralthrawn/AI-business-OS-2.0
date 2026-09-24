import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class ProductSupplier(Base, IdMixin, TimestampMixin):
    """The terms under which one supplier can provide one product (V2). A
    product has many of these -- `Product.supplier_id` (V1) is kept as the
    *preferred* supplier and always has a matching row here.

    Every term carries its basis: a catalog price the supplier sent a year
    ago is DECLARED with a low confidence, not a fact."""

    __tablename__ = "product_suppliers"
    __table_args__ = (Index("ix_product_suppliers_pair", "product_id", "supplier_id", unique=True),)

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=False, index=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(120))
    unit_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    price_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    moq: Mapped[float | None] = mapped_column(Float)
    spq: Mapped[float | None] = mapped_column(Float)
    lead_time_min_days: Mapped[float | None] = mapped_column(Float)
    lead_time_max_days: Mapped[float | None] = mapped_column(Float)
    lead_time_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.UNKNOWN)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    country_of_origin: Mapped[str | None] = mapped_column(String(120))
    certifications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When these terms were last confirmed by the supplier -- drives confidence.
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")

    product: Mapped["Product"] = relationship()
    supplier: Mapped["Supplier"] = relationship()


class StockKind(str, enum.Enum):
    """Three different things, never summed together:
    - PHYSICAL: units we hold (our warehouse).
    - SUPPLIER: units a supplier says it holds for us to buy.
    - POTENTIAL: units announced as available elsewhere (e.g. a website or
      marketplace listing) -- the least reliable."""

    PHYSICAL = "physical"
    SUPPLIER = "supplier"
    POTENTIAL = "potential"


class StockPosition(Base, IdMixin, TimestampMixin):
    """A stock quantity at a point in time, from a named source. The natural
    key (product, kind, supplier, location) is what an import upserts on,
    so a CSV/API source can be re-imported without duplicates."""

    __tablename__ = "stock_positions"
    __table_args__ = (
        Index("ix_stock_positions_key", "product_id", "kind", "supplier_id", "location", unique=True),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False, index=True)
    kind: Mapped[StockKind] = mapped_column(Enum(StockKind), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True, index=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "manual" | "csv:<file name>" | "api:<system>" -- where the number came from.
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(120))

    product: Mapped["Product"] = relationship()
    supplier: Mapped["Supplier | None"] = relationship()
