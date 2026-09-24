import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin


class EventLogEntry(Base, IdMixin, TimestampMixin):
    """Append-only persistence of every Business Event published on the Event Bus.
    Written by a generic handler subscribed to all event types (see
    app.core.events.log_handler) so the log is a plain consumer, not something
    built into the bus itself.
    """

    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # V2: the object this event is primarily about (see
    # app.core.events.subjects), so a per-object timeline is an indexed
    # query instead of a payload scan. Null when no subject can be derived.
    subject_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
