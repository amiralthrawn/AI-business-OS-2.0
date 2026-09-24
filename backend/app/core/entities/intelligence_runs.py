"""Records of AI work whose steps the user can watch (V2.1): supplier
sourcing and website analysis. A run stores what was really done, step by
step, and whether it ran on real inputs or on simulated demonstration data
(`mode`) -- the UI never shows a fake progress bar."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class SourcingLead(Base, IdMixin, TimestampMixin):
    """A potential supplier found for a purchase request -- with its
    provenance. Never a Supplier until a human converts it; a price is only
    recorded when the source states one (DECLARED by that source), otherwise
    it stays UNKNOWN."""

    __tablename__ = "sourcing_leads"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    purchase_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("commercial_documents.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("products.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(120))
    # "existing_supplier" | "web_search" | "manual"
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    snippet: Mapped[str | None] = mapped_column(Text)
    found_price: Mapped[float | None] = mapped_column(Float)
    price_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.UNKNOWN)
    # Other facts as the source stated them: {"moq": ..., "lead_time": "...", "certifications": [...]}
    facts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # "new" | "contacted" | "converted" | "discarded"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AIRun(Base, IdMixin, TimestampMixin):
    """One execution of an observable AI job ("sourcing", "website_audit"):
    its steps as they really happened, its mode and its result."""

    __tablename__ = "ai_runs"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # "real" | "simulated" | "partial" (e.g. web search not configured)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running | done | failed
    target: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # [{"label": str, "status": "done"|"skipped"|"failed", "detail": str|None, "at": iso}]
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class WebsiteChangeProposal(Base, IdMixin, TimestampMixin):
    """A change the AI proposes on the company's website (title, meta
    description, heading, image alt...). current -> proposed is the diff a
    human reviews; approval goes through the V1 HITL. In this MVP nothing is
    ever written to the real site: approval marks it ready to apply."""

    __tablename__ = "website_change_proposals"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_runs.id"), nullable=False, index=True)
    page_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    field: Mapped[str] = mapped_column(String(30), nullable=False)  # "title" | "meta_description" | "h1" | "img_alt"
    current_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(20), nullable=False, default="rules")
    # "proposed" | "pending_validation" | "approved" | "rejected"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=True)
