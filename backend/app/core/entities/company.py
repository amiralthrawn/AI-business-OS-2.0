from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin


class Company(Base, IdMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    # V2.1: the company's public website, analysed by Website Intelligence.
    website_url: Mapped[str | None] = mapped_column(String(500))

    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="company")
    customers: Mapped[list["Customer"]] = relationship(back_populates="company")
    products: Mapped[list["Product"]] = relationship(back_populates="company")
