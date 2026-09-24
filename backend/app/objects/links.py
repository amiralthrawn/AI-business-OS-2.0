import uuid

from sqlalchemy.orm import Session

from app.core.entities import ObjectLink
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.objects.registry import get_object

OBJECTS_LINKED = "ObjectsLinked"
OBJECTS_UNLINKED = "ObjectsUnlinked"

RELATIONS = frozenset({"derived_from", "concerns", "mentions", "attachment"})


class LinkError(ValueError):
    pass


def create_link(
    session: Session,
    *,
    company_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    relation: str,
    origin: str = "manual",
    event_bus: EventBus | None = None,
    commit: bool = True,
) -> ObjectLink:
    """Validated, idempotent link creation -- the only write path to
    ObjectLink, which is what keeps its application-level integrity: both
    ends must exist and belong to the company, and linking twice is a no-op."""

    if relation not in RELATIONS:
        raise LinkError(f"Unknown relation '{relation}'")
    if source_type == target_type and source_id == target_id:
        raise LinkError("An object cannot be linked to itself")
    for obj_type, obj_id in ((source_type, source_id), (target_type, target_id)):
        try:
            obj = get_object(session, obj_type, obj_id)
        except LookupError as exc:
            raise LinkError(str(exc)) from exc
        if getattr(obj, "company_id", company_id) != company_id:
            raise LinkError(f"{obj_type} {obj_id} belongs to another company")

    existing = (
        session.query(ObjectLink)
        .filter_by(source_type=source_type, source_id=source_id, target_type=target_type, target_id=target_id, relation=relation)
        .first()
    )
    if existing is not None:
        return existing

    link = ObjectLink(
        company_id=company_id,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
        relation=relation,
        origin=origin,
    )
    session.add(link)
    if commit:
        session.commit()
    else:
        session.flush()
    if event_bus is not None and relation != "derived_from":
        event_bus.publish(
            BusinessEvent(
                event_type=OBJECTS_LINKED,
                source="objects",
                payload={
                    "subject_type": target_type,
                    "subject_id": str(target_id),
                    "linked_type": source_type,
                    "linked_id": str(source_id),
                    "relation": relation,
                    "origin": origin,
                },
            )
        )
    return link


def delete_link(session: Session, link_id: uuid.UUID) -> None:
    link = session.get(ObjectLink, link_id)
    if link is None:
        raise LinkError("Link not found")
    if link.relation == "derived_from":
        # The document chain is traceability, not a user annotation.
        raise LinkError("A document chain link cannot be removed")
    session.delete(link)
    session.commit()
