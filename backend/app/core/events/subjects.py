"""Which business object an event is primarily about (V2).

V1 left the Event Log without a structured entity link (brain/decisions.md
#20): every event type named its subject with its own payload field, so
"history of object X" meant scanning payload JSON. V2 needs a per-object
timeline everywhere (a quote's history, a supplier's history), so the log
now stores `subject_type`/`subject_id`, derived here from those same
payload conventions -- publishers do not have to change. A V2 publisher can
set `subject_type`/`subject_id` explicitly in its payload; that always wins.
"""

import uuid

# Payload keys, in priority order, naming the event's primary subject.
# The explicit V2 keys come first, then V1's generic entity pointers, then
# the per-object id fields -- most specific object before broader ones.
_KEYED_SUBJECTS: tuple[tuple[str, str], ...] = (
    ("document_id", "commercial_document"),
    ("communication_id", "communication"),
    ("product_id", "product"),
    ("supplier_id", "supplier"),
    ("customer_id", "customer"),
    ("task_id", "task"),
)


def _as_uuid(value) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def infer_subject(payload: dict) -> tuple[str | None, uuid.UUID | None]:
    if not isinstance(payload, dict):
        return None, None

    for type_key, id_key in (("subject_type", "subject_id"), ("entity_type", "entity_id"), ("related_entity_type", "related_entity_id")):
        subject_type, subject_id = payload.get(type_key), _as_uuid(payload.get(id_key))
        if subject_type and subject_id is not None:
            return str(subject_type).lower(), subject_id

    for key, subject_type in _KEYED_SUBJECTS:
        subject_id = _as_uuid(payload.get(key))
        if subject_id is not None:
            return subject_type, subject_id
    return None, None
