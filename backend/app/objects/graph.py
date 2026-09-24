"""The relationship graph (V2): "what is this object related to?", answered
the same way for every object type, whatever storage holds the relation.

Three storages, one read model (brain/business_object_model.md):
1. Foreign keys -- a document's customer, a line's product, a posted
   Transaction's source document, a product's suppliers (ProductSupplier).
2. V1's LinkableMixin pointer -- a Task/Risk/Opportunity/Contact/
   Communication/file pointing at one object.
3. ObjectLink rows -- typed many-to-many relations (document chain,
   email <-> quote, ...).

Consumers (the contextual API behind every object page, the margin engine
walking a deal's documents, the AI Orchestrator traversing
order -> product -> supplier -> purchase order) never know which storage a
relation uses. Adding a relation = adding it here once.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.entities import (
    CommercialDocument,
    CommercialDocumentLine,
    Communication,
    Contact,
    Document,
    ObjectLink,
    Opportunity,
    Product,
    ProductSupplier,
    Risk,
    Task,
    Transaction,
    TransactionType,
)
from app.objects.registry import LINKABLE_TO_TYPE, OBJECT_TYPES, get_object

MAX_PER_SOURCE = 50


@dataclass(frozen=True)
class Edge:
    type: str
    id: uuid.UUID
    relation: str  # e.g. "customer", "product", "derived_from", "concerns"
    direction: str  # "out" (this object points to it) | "in" (it points to this object)


def _dedupe(edges: list[Edge]) -> list[Edge]:
    seen: set[tuple[str, uuid.UUID]] = set()
    unique: list[Edge] = []
    for edge in edges:
        key = (edge.type, edge.id)
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    return unique


def _linkable_in(session: Session, obj_type: str, obj_id: uuid.UUID) -> list[Edge]:
    """Every V1 LinkableMixin row pointing at this object."""

    linkable = OBJECT_TYPES[obj_type].linkable
    if linkable is None:
        return []
    edges: list[Edge] = []
    for model, key in ((Task, "task"), (Risk, "risk"), (Opportunity, "opportunity"), (Contact, "contact"), (Communication, "communication"), (Document, "document")):
        rows = (
            session.query(model.id)
            .filter(model.related_entity_type == linkable, model.related_entity_id == obj_id)
            .order_by(model.created_at.desc())
            .limit(MAX_PER_SOURCE)
            .all()
        )
        edges += [Edge(key, row.id, "concerns", "in") for row in rows]
    return edges


def _linkable_out(obj) -> list[Edge]:
    target_type = getattr(obj, "related_entity_type", None)
    target_id = getattr(obj, "related_entity_id", None)
    if target_type is None or target_id is None or target_type not in LINKABLE_TO_TYPE:
        return []
    return [Edge(LINKABLE_TO_TYPE[target_type], target_id, "concerns", "out")]


def _object_links(session: Session, obj_type: str, obj_id: uuid.UUID) -> list[Edge]:
    rows = (
        session.query(ObjectLink)
        .filter(
            or_(
                (ObjectLink.source_type == obj_type) & (ObjectLink.source_id == obj_id),
                (ObjectLink.target_type == obj_type) & (ObjectLink.target_id == obj_id),
            )
        )
        .all()
    )
    edges: list[Edge] = []
    for link in rows:
        if link.source_type == obj_type and link.source_id == obj_id:
            edges.append(Edge(link.target_type, link.target_id, link.relation, "out"))
        else:
            edges.append(Edge(link.source_type, link.source_id, link.relation, "in"))
    return edges


def _documents_where(session: Session, *criteria) -> list[Edge]:
    rows = (
        session.query(CommercialDocument.id)
        .filter(*criteria)
        .order_by(CommercialDocument.created_at.desc())
        .limit(MAX_PER_SOURCE)
        .all()
    )
    return [Edge("commercial_document", row.id, "document", "in") for row in rows]


def _transactions_where(session: Session, *criteria) -> list[Edge]:
    rows = session.query(Transaction.id).filter(*criteria).order_by(Transaction.occurred_at.desc()).limit(20).all()
    return [Edge("transaction", row.id, "transaction", "in") for row in rows]


def _structural(session: Session, obj_type: str, obj) -> list[Edge]:
    edges: list[Edge] = []
    if obj_type == "commercial_document":
        if obj.customer_id:
            edges.append(Edge("customer", obj.customer_id, "customer", "out"))
        if obj.supplier_id:
            edges.append(Edge("supplier", obj.supplier_id, "supplier", "out"))
        if obj.contact_id:
            edges.append(Edge("contact", obj.contact_id, "contact", "out"))
        edges += [Edge("product", line.product_id, "product", "out") for line in obj.lines if line.product_id]
        edges += _transactions_where(session, Transaction.source_document_id == obj.id)
    elif obj_type == "product":
        supplier_ids = [row.supplier_id for row in session.query(ProductSupplier.supplier_id).filter_by(product_id=obj.id).all()]
        if obj.supplier_id and obj.supplier_id not in supplier_ids:
            supplier_ids.insert(0, obj.supplier_id)
        edges += [Edge("supplier", sid, "supplier", "out") for sid in supplier_ids]
        line_doc_ids = session.query(CommercialDocumentLine.document_id).filter_by(product_id=obj.id).distinct().limit(MAX_PER_SOURCE).all()
        edges += [Edge("commercial_document", row.document_id, "document", "in") for row in line_doc_ids]
        customer_ids = (
            session.query(Transaction.customer_id)
            .filter(Transaction.product_id == obj.id, Transaction.type == TransactionType.SALES_ORDER, Transaction.customer_id.isnot(None))
            .distinct()
            .all()
        )
        edges += [Edge("customer", row.customer_id, "customer", "in") for row in customer_ids]
        edges += _transactions_where(session, Transaction.product_id == obj.id)
    elif obj_type == "supplier":
        product_ids = [row.product_id for row in session.query(ProductSupplier.product_id).filter_by(supplier_id=obj.id).all()]
        product_ids += [row.id for row in session.query(Product.id).filter_by(supplier_id=obj.id).all() if row.id not in product_ids]
        edges += [Edge("product", pid, "product", "out") for pid in product_ids]
        edges += _documents_where(session, CommercialDocument.supplier_id == obj.id)
        edges += _transactions_where(session, Transaction.supplier_id == obj.id)
    elif obj_type == "customer":
        edges += _documents_where(session, CommercialDocument.customer_id == obj.id)
        product_ids = (
            session.query(Transaction.product_id)
            .filter(Transaction.customer_id == obj.id, Transaction.product_id.isnot(None))
            .distinct()
            .all()
        )
        edges += [Edge("product", row.product_id, "product", "out") for row in product_ids]
        edges += _transactions_where(session, Transaction.customer_id == obj.id)
    elif obj_type == "contact":
        edges += [Edge("communication", c.id, "communication", "in") for c in session.query(Communication.id).filter_by(contact_id=obj.id).order_by(Communication.occurred_at.desc()).limit(MAX_PER_SOURCE).all()]
        edges += _documents_where(session, CommercialDocument.contact_id == obj.id)
    elif obj_type == "communication":
        if obj.contact_id:
            edges.append(Edge("contact", obj.contact_id, "contact", "out"))
    elif obj_type == "employee":
        # Work assigned to the person, and deals they own (via their user profile).
        edges += [Edge("task", row.id, "assigned", "in") for row in session.query(Task.id).filter(Task.assignee_employee_id == obj.id).order_by(Task.created_at.desc()).limit(MAX_PER_SOURCE).all()]
        if obj.user_id:
            edges += _documents_where(session, CommercialDocument.owner_user_id == obj.user_id)
    elif obj_type == "candidate":
        if obj.communication_id:
            edges.append(Edge("communication", obj.communication_id, "application", "out"))
    elif obj_type == "transaction":
        for attr, key in (("customer_id", "customer"), ("supplier_id", "supplier"), ("product_id", "product"), ("source_document_id", "commercial_document")):
            if getattr(obj, attr):
                edges.append(Edge(key, getattr(obj, attr), key if key != "commercial_document" else "source_document", "out"))
    return edges


def related_edges(session: Session, obj_type: str, obj_id: uuid.UUID) -> list[Edge]:
    obj = get_object(session, obj_type, obj_id)
    edges = _structural(session, obj_type, obj) + _object_links(session, obj_type, obj_id) + _linkable_out(obj) + _linkable_in(session, obj_type, obj_id)
    return [e for e in _dedupe(edges) if not (e.type == obj_type and e.id == obj_id)]


# --- Document chain (the "affaire") ---------------------------------------


def document_parents(session: Session, doc_id: uuid.UUID) -> list[uuid.UUID]:
    rows = session.query(ObjectLink.target_id).filter_by(source_type="commercial_document", source_id=doc_id, relation="derived_from", target_type="commercial_document").all()
    return [row.target_id for row in rows]


def document_children(session: Session, doc_id: uuid.UUID) -> list[uuid.UUID]:
    rows = session.query(ObjectLink.source_id).filter_by(target_type="commercial_document", target_id=doc_id, relation="derived_from", source_type="commercial_document").all()
    return [row.source_id for row in rows]


def document_chain(session: Session, doc_id: uuid.UUID) -> list[CommercialDocument]:
    """Every document connected to this one through `derived_from` links, in
    both directions -- the whole deal: request, quotes, order, purchase
    requests, supplier quotes, POs, receptions, invoices. Bounded BFS."""

    seen: set[uuid.UUID] = {doc_id}
    frontier = [doc_id]
    while frontier and len(seen) < 200:
        next_frontier: list[uuid.UUID] = []
        for current in frontier:
            for neighbor in document_parents(session, current) + document_children(session, current):
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
    docs = session.query(CommercialDocument).filter(CommercialDocument.id.in_(seen)).all()
    return sorted(docs, key=lambda d: d.created_at)


def document_ancestry(session: Session, doc_id: uuid.UUID) -> list[CommercialDocument]:
    """The path from the deal's root down to this document (first parent at
    each step) -- the breadcrumb answering "where does this come from?"."""

    path: list[CommercialDocument] = []
    current: uuid.UUID | None = doc_id
    visited: set[uuid.UUID] = set()
    while current is not None and current not in visited:
        visited.add(current)
        doc = session.get(CommercialDocument, current)
        if doc is None:
            break
        path.append(doc)
        parents = document_parents(session, current)
        current = parents[0] if parents else None
    return list(reversed(path))


def neighbors_of_type(session: Session, obj_type: str, obj_id: uuid.UUID, wanted: str) -> list[uuid.UUID]:
    return [e.id for e in related_edges(session, obj_type, obj_id) if e.type == wanted]


__all__ = [
    "Edge",
    "related_edges",
    "document_chain",
    "document_ancestry",
    "document_parents",
    "document_children",
    "neighbors_of_type",
]
