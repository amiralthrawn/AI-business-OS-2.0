import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin


class BusinessContext(Base, IdMixin, TimestampMixin):
    """The company-specific configuration that lets the OS reason about THIS
    business rather than a generic one. See brain/business_context.md and
    brain/business_state.md for the full concept, and for what stays
    deliberately deferred (adaptive learning, sector profiles, automatic
    application of anything below without a human confirming it first).

    Every configuration field here is nullable and defaults to "not answered"
    (None / empty), not a guessed value -- an unanswered onboarding question
    must never be silently treated as a real preference.
    """

    __tablename__ = "business_contexts"

    # One BusinessContext per Company for the MVP (no multi-tenancy, no
    # per-department contexts yet -- both are natural future extensions of
    # this same table, not a different concept).
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, unique=True, index=True
    )

    # --- Declared onboarding configuration ("set up like a new iPhone") -----
    # Sector already lives on Company.industry; not duplicated here.
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Which domains the company has declared it wants watched.
    monitored_domains: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # What Home should foreground first, e.g. ["priorities", "risks", "opportunities"].
    home_focus: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Coarse notification sensitivity ("low" | "normal" | "high"). Not yet
    # wired into any detection threshold -- reserved for when Intelligence
    # rules become configurable per company instead of hardcoded.
    notification_level: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    # Free-text, leadership-declared goals (e.g. "protect margin on core
    # products", "reduce single-supplier dependency").
    stated_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Declared baselines: what the company itself considers "normal" for a
    # metric, e.g. {"margin_pct": 0.30}. Distinct from, and never conflated
    # with, a baseline observed from history (see app.core.baseline) -- a
    # target is an intention, not a measurement.
    declared_baselines: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # --- Progressively learned / human-sourced information ------------------
    # Short factual notes the system has picked up over time that don't fit a
    # structured field yet (e.g. "tends to reject cost-increase tasks under
    # 15%"). Appended to by code, never by the AI rewriting past entries --
    # this is a log, not an editable profile.
    learned_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # V2.1 director finance settings, all DECLARED by the company:
    # {"min_cash": float, "declared_valuation": float, "declared_valuation_date": str,
    #  "revenue_multiple_min": float, "revenue_multiple_max": float}.
    finance_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
