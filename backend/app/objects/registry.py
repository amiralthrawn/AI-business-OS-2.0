"""The business object registry (V2): every object type the OS can show,
link, traverse and reason about, and how to summarize one instance of it.

Keys are the object types used everywhere a type is named as a string
(ObjectLink.source_type/target_type, Event Log subjects, the contextual
API, the frontend's links). `href` is the frontend route of an object --
kept here, next to the type, so "where do I go to see X" has one answer.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.i18n import money, num, text_of, tx
from app.core.entities import (
    Candidate,
    CommercialDocument,
    Employee,
    Communication,
    Contact,
    Customer,
    Document,
    Opportunity,
    Product,
    RelatedEntityType,
    Risk,
    Supplier,
    Task,
    Transaction,
)
from app.transactions.lifecycle import KINDS, kind_label, status_label


@dataclass(frozen=True)
class ObjectSummary:
    type: str
    id: uuid.UUID
    title: str
    subtitle: str | None
    status: str | None
    status_label: str | None
    kind: str | None  # a commercial document's kind, a communication's channel
    kind_label: str
    href: str | None
    domain: str | None
    date: Any = None


def _fmt_date(value) -> str | None:
    return value.date().isoformat() if value is not None else None


def _doc(d: CommercialDocument) -> ObjectSummary:
    spec = KINDS[d.kind]
    return ObjectSummary(
        type="commercial_document",
        id=d.id,
        title=d.number + (f" · {d.title}" if d.title else ""),
        subtitle=d.external_reference and tx(f"Réf. externe {d.external_reference}", f"External ref. {d.external_reference}"),
        status=d.status,
        status_label=status_label(d.kind, d.status),
        kind=d.kind.value,
        kind_label=kind_label(d.kind),
        href=f"/documents/{d.id}",
        domain=spec.domain,
        date=d.issued_at or d.created_at,
    )


def _customer(c: Customer) -> ObjectSummary:
    return ObjectSummary(
        "customer", c.id, c.name, c.country, c.status,
        {"prospect": tx("Prospect", "Prospect"), "active": tx("Client actif", "Active customer"), "inactive": tx("Inactif", "Inactive")}.get(c.status, c.status),
        None, tx("Client", "Customer"), f"/data/customers/{c.id}", "sales", c.created_at,
    )  # fmt: skip


def _supplier(s: Supplier) -> ObjectSummary:
    return ObjectSummary(
        "supplier", s.id, s.name, s.country, None, None, None, tx("Fournisseur", "Supplier"),
        f"/data/suppliers/{s.id}", "procurement", s.created_at,
    )  # fmt: skip


def _product(p: Product) -> ObjectSummary:
    return ObjectSummary(
        "product", p.id, p.name, p.sku and tx(f"Réf. {p.sku}", f"Ref. {p.sku}"), None, None, None, tx("Produit", "Product"),
        f"/data/products/{p.id}", "catalog", p.created_at,
    )  # fmt: skip


def _contact(c: Contact) -> ObjectSummary:
    return ObjectSummary(
        "contact", c.id, c.name, c.email, None, None, None, "Contact",
        f"/communications?tab=contacts&contact={c.id}", "communications", c.created_at,
    )  # fmt: skip


def _communication(c: Communication) -> ObjectSummary:
    labels = {"received": tx("Reçu", "Received"), "sent": tx("Envoyé", "Sent"), "draft": tx("Brouillon", "Draft"), "pending_validation": tx("À valider", "To approve"), "rejected": tx("Refusé", "Rejected")}
    return ObjectSummary(
        "communication", c.id, c.subject or tx("(sans objet)", "(no subject)"), c.from_address if c.direction.value == "inbound" else c.to_address,
        c.status, labels.get(c.status, c.status), c.channel,
        {"email": "Email", "calendar": tx("Rendez-vous", "Meeting"), "website": tx("Site web", "Website"), "social": tx("Réseau social", "Social network")}.get(c.channel, c.channel),
        f"/communications?message={c.id}", "communications", c.occurred_at,
    )  # fmt: skip


def _file(d: Document) -> ObjectSummary:
    return ObjectSummary("document", d.id, d.title, d.document_type, None, None, None, tx("Fichier", "File"), d.url, None, d.created_at)


def _transaction(t: Transaction) -> ObjectSummary:
    labels = {"sales_order": tx("Vente", "Sale"), "purchase_order": tx("Achat", "Purchase"), "invoice": tx("Facture", "Invoice")}
    return ObjectSummary(
        "transaction", t.id, f"{labels.get(t.type.value, t.type.value)} · {money(t.amount, 0) if t.currency == 'EUR' else f'{num(t.amount, 0)} {t.currency}'}",
        _fmt_date(t.occurred_at), t.status.value, None, t.type.value, tx("Écriture", "Entry"),
        f"/documents/{t.source_document_id}" if t.source_document_id else "/data/transactions",
        "finance", t.occurred_at,
    )  # fmt: skip


def _task(t: Task) -> ObjectSummary:
    return ObjectSummary(
        "task", t.id, text_of(t, "title"), (text_of(t, "description") or "")[:80] or None, t.status.value, None, None, tx("Tâche", "Task"),
        f"/actions/tasks?task={t.id}", "actions", t.created_at,
    )  # fmt: skip


def _risk(r: Risk) -> ObjectSummary:
    return ObjectSummary(
        "risk", r.id, text_of(r, "title"), None, r.status.value, None, r.severity.value, tx("Risque", "Risk"),
        f"/intelligence/risks/{r.id}", "intelligence", r.created_at,
    )  # fmt: skip


def _opportunity(o: Opportunity) -> ObjectSummary:
    return ObjectSummary(
        "opportunity", o.id, text_of(o, "title"), None, o.status.value, None, None, tx("Opportunité", "Opportunity"),
        f"/intelligence/opportunities/{o.id}", "intelligence", o.created_at,
    )  # fmt: skip


def _employee(e: Employee) -> ObjectSummary:
    return ObjectSummary(
        "employee", e.id, e.full_name, " · ".join(filter(None, [e.job_title, e.department])) or None, e.status,
        {"active": tx("Actif", "Active"), "on_leave": tx("En congé", "On leave"), "left": tx("Parti", "Left")}.get(e.status, e.status), None, tx("Employé", "Employee"),
        f"/people/{e.id}", "people", e.hired_at,
    )  # fmt: skip


def _candidate(c: Candidate) -> ObjectSummary:
    labels = {"new": tx("Nouveau", "New"), "shortlisted": tx("Présélectionné", "Shortlisted"), "interview_proposed": tx("Entretien proposé", "Interview proposed"), "rejected": tx("Écarté", "Rejected"), "hired": tx("Recruté", "Hired")}
    return ObjectSummary(
        "candidate", c.id, c.full_name, c.applied_for, c.status, labels.get(c.status, c.status), None, tx("Candidat", "Candidate"),
        f"/people?tab=recruitment&candidate={c.id}", "people", c.created_at,
    )  # fmt: skip


@dataclass(frozen=True)
class ObjectType:
    key: str
    model: type
    summarize: Callable[[Any], ObjectSummary]
    # The V1 LinkableMixin enum value pointing at this type, if any.
    linkable: RelatedEntityType | None = None


OBJECT_TYPES: dict[str, ObjectType] = {
    t.key: t
    for t in (
        ObjectType("commercial_document", CommercialDocument, _doc, RelatedEntityType.COMMERCIAL_DOCUMENT),
        ObjectType("customer", Customer, _customer, RelatedEntityType.CUSTOMER),
        ObjectType("supplier", Supplier, _supplier, RelatedEntityType.SUPPLIER),
        ObjectType("product", Product, _product, RelatedEntityType.PRODUCT),
        ObjectType("contact", Contact, _contact, RelatedEntityType.CONTACT),
        ObjectType("communication", Communication, _communication, RelatedEntityType.COMMUNICATION),
        ObjectType("document", Document, _file),
        ObjectType("transaction", Transaction, _transaction, RelatedEntityType.TRANSACTION),
        ObjectType("task", Task, _task),
        ObjectType("risk", Risk, _risk),
        ObjectType("opportunity", Opportunity, _opportunity),
        ObjectType("employee", Employee, _employee, RelatedEntityType.EMPLOYEE),
        ObjectType("candidate", Candidate, _candidate, RelatedEntityType.CANDIDATE),
    )
}

LINKABLE_TO_TYPE: dict[RelatedEntityType, str] = {t.linkable: t.key for t in OBJECT_TYPES.values() if t.linkable}


class UnknownObjectError(LookupError):
    pass


def get_object(session: Session, obj_type: str, obj_id: uuid.UUID):
    object_type = OBJECT_TYPES.get(obj_type)
    if object_type is None:
        raise UnknownObjectError(f"Unknown object type '{obj_type}'")
    obj = session.get(object_type.model, obj_id)
    if obj is None:
        raise UnknownObjectError(f"{obj_type} {obj_id} not found")
    return obj


def summarize(obj_type: str, obj) -> ObjectSummary:
    return OBJECT_TYPES[obj_type].summarize(obj)
