"""A small, transverse read over the Data Core: given (entity_type, entity_id),
reconstructs the entity's direct context -- its own core attributes, its
directly related entities (Supplier<->Product, Product/Supplier/Customer<->
Transaction), any open Risks/Opportunities/Tasks pointing at it, any
Documents/Communications linked to it, and any Business Events that mention
it in the Event Log.

This is plain, structural reads only -- no Baseline, no Significance, no
Interpretation, no LLM, no scoring. It exists because step 20's audit of the
Data Core found that every higher layer (Interpretation's context assembly,
the AI Orchestrator's entity resolution, Home's Snapshot re-hydration) had
already grown its own bespoke way to gather "what's around this entity" --
this function is the one, generic, Data-Core-level version of that specific
question, for callers that need it without going through the AI capability
registry. It intentionally does NOT replace any of those existing,
already-tested code paths (see brain/data_core.md for why).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.i18n import text_of
from app.core.entities import (
    Communication,
    Contact,
    Customer,
    Document,
    Opportunity,
    OpportunityStatus,
    Product,
    RelatedEntityType,
    Risk,
    RiskStatus,
    Supplier,
    Task,
    Transaction,
)
from app.core.entities.event_log import EventLogEntry

DEFAULT_TRANSACTIONS_LIMIT = 10
DEFAULT_EVENTS_LIMIT = 10

_ENTITY_MODELS = {
    RelatedEntityType.SUPPLIER: Supplier,
    RelatedEntityType.PRODUCT: Product,
    RelatedEntityType.CUSTOMER: Customer,
}


def _transaction_summaries(session: Session, *, limit: int = DEFAULT_TRANSACTIONS_LIMIT, **filters) -> list[dict]:
    query = session.query(Transaction)
    for column, value in filters.items():
        query = query.filter(getattr(Transaction, column) == value)
    rows = query.order_by(Transaction.occurred_at.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "type": t.type.value,
            "status": t.status.value,
            "amount": t.amount,
            "currency": t.currency,
            "occurred_at": t.occurred_at,
            "supplier_id": t.supplier_id,
            "customer_id": t.customer_id,
            "product_id": t.product_id,
        }
        for t in rows
    ]


def _linked(session: Session, model, entity_type: RelatedEntityType, entity_id: uuid.UUID) -> list:
    return (
        session.query(model)
        .filter(model.related_entity_type == entity_type, model.related_entity_id == entity_id)
        .all()
    )


def _related_events(session: Session, entity_id: uuid.UUID, limit: int = DEFAULT_EVENTS_LIMIT) -> list[dict]:
    """Business Events that mention this entity anywhere in their payload.

    The Event Log (app.core.entities.event_log.EventLogEntry) has no
    structured entity link of its own -- every event type names its
    entity/entities with whatever field name makes sense for it
    (`entity_id`, `supplier_id`, `related_entity_id`, ...), a real, already
    documented inconsistency (see brain/data_core.md). Rather than add a new
    column and touch every publisher across Observation/Interpretation/
    Decision/Intelligence/Actions to populate it -- real surgery across
    layers this step is explicitly not meant to touch -- this reuses the
    exact same "does this id appear as a string value anywhere in the
    payload" scan `app.snapshot.service._recurrence_count` already uses,
    which is already proven sufficient at this dataset's scale.
    """

    target = str(entity_id)
    matches = [
        entry
        for entry in session.query(EventLogEntry).order_by(EventLogEntry.occurred_at.desc()).all()
        if target in (v for v in entry.payload.values() if isinstance(v, str))
    ]
    return [
        {"event_type": e.event_type, "source": e.source, "occurred_at": e.occurred_at}
        for e in matches[:limit]
    ]


def get_entity_context(session: Session, entity_type: RelatedEntityType, entity_id: uuid.UUID) -> dict:
    """Reconstructs a Supplier/Product/Customer's direct context from the
    Data Core: its own attributes, its directly related entities, any open
    Risks/Opportunities/Tasks attached to it, any linked Documents/
    Communications, and any Business Events that mention it.

    Returns `{"found": False, ...}` for an unknown id or an entity type this
    Data Core doesn't model relationships for (e.g. COMPANY, TRANSACTION) --
    never raises, so a caller can treat a missing entity the same way it
    would treat "nothing found" rather than as an exceptional case.
    """

    model = _ENTITY_MODELS.get(entity_type)
    entity = session.get(model, entity_id) if model is not None else None
    if entity is None:
        return {"entity_type": entity_type.value if entity_type else None, "entity_id": entity_id, "found": False}

    context: dict = {"entity_type": entity_type.value, "entity_id": entity_id, "found": True, "name": entity.name}

    if entity_type == RelatedEntityType.SUPPLIER:
        context["country"] = entity.country
        context["products"] = [{"id": p.id, "name": p.name, "sku": p.sku} for p in entity.products]
        context["transactions"] = _transaction_summaries(session, supplier_id=entity_id)
    elif entity_type == RelatedEntityType.PRODUCT:
        context["sku"] = entity.sku
        context["unit_cost"] = entity.unit_cost
        context["supplier"] = (
            {"id": entity.supplier.id, "name": entity.supplier.name} if entity.supplier is not None else None
        )
        context["transactions"] = _transaction_summaries(session, product_id=entity_id)
    elif entity_type == RelatedEntityType.CUSTOMER:
        context["country"] = entity.country
        context["transactions"] = _transaction_summaries(session, customer_id=entity_id)

    context["open_risks"] = [
        {"id": r.id, "title": text_of(r, "title"), "severity": r.severity.value}
        for r in _linked(session, Risk, entity_type, entity_id)
        if r.status == RiskStatus.OPEN
    ]
    context["open_opportunities"] = [
        {"id": o.id, "title": text_of(o, "title")}
        for o in _linked(session, Opportunity, entity_type, entity_id)
        if o.status == OpportunityStatus.OPEN
    ]
    context["tasks"] = [
        {"id": t.id, "title": text_of(t, "title"), "status": t.status.value}
        for t in _linked(session, Task, entity_type, entity_id)
    ]
    context["documents"] = [
        {"id": d.id, "title": d.title, "document_type": d.document_type}
        for d in _linked(session, Document, entity_type, entity_id)
    ]
    context["communications"] = [
        {"id": c.id, "channel": c.channel, "direction": c.direction.value, "subject": c.subject}
        for c in _linked(session, Communication, entity_type, entity_id)
    ]
    context["contacts"] = [
        {"id": p.id, "name": p.name, "role": p.role, "email": p.email, "phone": p.phone}
        for p in _linked(session, Contact, entity_type, entity_id)
    ]
    context["related_events"] = _related_events(session, entity_id)

    return context
