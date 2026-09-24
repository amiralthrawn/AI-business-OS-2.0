import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin


class ObjectLink(Base, IdMixin, TimestampMixin):
    """A typed, many-to-many relation between any two business objects (V2).

    This is the third and last way two objects relate, next to plain foreign
    keys (a document's customer) and V1's single-target `LinkableMixin`
    pointer (a Task's entity). It exists for the relations the other two
    cannot express: a quote derived from a customer request AND linked to
    three emails; a purchase order fulfilling two purchase requests.
    All three are read through ONE service, `app.objects.graph` -- callers
    never care which storage a relation uses.

    Object types are the keys of `app.objects.registry` ("customer",
    "commercial_document", "communication", ...). Like LinkableMixin,
    integrity is application-level (validated on creation by
    `app.objects.links.create_link`), since a native FK cannot target
    several tables.

    Relations (`relation`): "derived_from" (document chain, source -> the
    document it was created from), "concerns" (an email/file about an
    object), "mentions" (detected reference), "attachment"."""

    __tablename__ = "object_links"
    __table_args__ = (
        Index(
            "ix_object_links_unique",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            unique=True,
        ),
        Index("ix_object_links_target", "target_type", "target_id"),
        Index("ix_object_links_source", "source_type", "source_id"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    relation: Mapped[str] = mapped_column(String(30), nullable=False)
    # "system" (created by a workflow, e.g. derive), "manual" (a human
    # linked it), "ai_suggested" (proposed by analysis, confirmed by a human).
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
