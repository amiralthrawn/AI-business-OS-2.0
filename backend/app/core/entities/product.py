import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class Product(Base, IdMixin, TimestampMixin):
    __tablename__ = "products"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120))
    # Float is good enough for MVP demo data; real money handling should move to Numeric.
    unit_cost: Mapped[float | None] = mapped_column(Float)

    # V2: Product becomes the central business object (brain/business_object_model.md).
    # `sku` (V1) is the internal reference; `supplier_id` (V1) stays the
    # *preferred* supplier, while every supplier able to provide it lives in
    # `product_suppliers` with its own terms. `unit_cost` (V1) is a reference
    # cost -- an ESTIMATE for margin purposes, never an actual cost.
    brand: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30))
    # List sale price, and where it comes from (a price list is DECLARED).
    sale_price: Mapped[float | None] = mapped_column(Float)
    sale_price_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)

    company: Mapped["Company"] = relationship(back_populates="products")
    supplier: Mapped["Supplier | None"] = relationship(back_populates="products")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="product")
