import enum
import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, LinkableMixin, TimestampMixin


class OpportunityStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    PURSUED = "pursued"
    DISMISSED = "dismissed"


class Opportunity(Base, IdMixin, TimestampMixin, LinkableMixin):
    __tablename__ = "opportunities"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus), nullable=False, default=OpportunityStatus.OPEN, index=True
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # Generated text in both interface languages, {"fr": {"title", "description"}, "en": {...}}
    # (app.core.i18n, brain/decisions.md #58); None for a text a person wrote.
    i18n: Mapped[dict | None] = mapped_column(JSON, nullable=True)
