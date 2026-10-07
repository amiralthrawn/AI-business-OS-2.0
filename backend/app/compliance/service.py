"""Compliance (V2.1, brain/compliance.md) -- deliberately NOT a legal module.

A compliance matter is a Task (domain "compliance", a `category`, a due
date), linked through the object graph to the documents and emails it is
about. An outside expert (law firm, accounting firm, insurance advisor) is
a Supplier with a `supplier_kind` and a DECLARED hourly rate range. This
module only adds the missing piece:

    Compliance request -> analysis -> recommendation (which expertise, which
    expert, estimated fees as a range) -> action (a draft request email,
    sent only after human validation). Nothing is ordered or paid.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.i18n import text_of, tx
from app.actions.service import ActionsService
from app.core.analytics import _as_aware_utc
from app.core.entities import Contact, RelatedEntityType, Supplier, Task, TaskStatus
from app.core.events.bus import EventBus
from app.objects.graph import related_edges

COMPLIANCE_DOMAIN = "compliance"

# category -> ((French label, English label), expert kind needed or None, benchmark hours range)
CATEGORIES: dict[str, tuple[tuple[str, str], str | None, tuple[float, float]]] = {
    "contract_review": (("Contrat à vérifier", "Contract to review"), "law_firm", (2, 5)),
    "nda": (("NDA", "NDA"), "law_firm", (1, 2)),
    "legal_request": (("Demande juridique", "Legal request"), "law_firm", (3, 8)),
    "regulatory": (("Obligation réglementaire", "Regulatory obligation"), "law_firm", (4, 10)),
    "accounting_request": (("Demande comptable / fiscale", "Accounting / tax request"), "accounting_firm", (2, 6)),
    "insurance": (("Assurance", "Insurance"), "insurance_advisor", (1, 3)),
    "renewal": (("Renouvellement / échéance", "Renewal / deadline"), None, (0, 0)),
    "other": (("Autre", "Other"), None, (0, 0)),
}
EXPERT_KINDS: dict[str, tuple[str, str]] = {  # (French, English)
    "law_firm": ("cabinet d'avocats", "law firm"),
    "accounting_firm": ("cabinet comptable", "accounting firm"),
    "insurance_advisor": ("courtier / conseil en assurance", "insurance broker / advisor"),
    "expert": ("expert externe", "external expert"),
}


def expert_kind_label(kind: str) -> str:
    return tx(*EXPERT_KINDS[kind]) if kind in EXPERT_KINDS else kind


def category_label(category: str | None) -> str:
    return tx(*CATEGORIES.get(category or "other", CATEGORIES["other"])[0])
# Hourly-rate BENCHMARKS used only when an expert has declared none.
BENCHMARK_RATES: dict[str, tuple[float, float]] = {
    "law_firm": (150, 350),
    "accounting_firm": (80, 180),
    "insurance_advisor": (0, 0),  # usually paid by commission: no fee estimate
    "expert": (100, 250),
}


class ComplianceError(ValueError):
    pass


def create_request(
    session: Session, event_bus: EventBus, company_id: uuid.UUID, *, title: str, category: str,
    description: str | None, due_at: datetime | None,
) -> Task:  # fmt: skip
    if category not in CATEGORIES:
        raise ComplianceError(tx("Catégorie inconnue", "Unknown category"))
    task = ActionsService(session, event_bus).create_manual_task(
        company_id=company_id, title=title, description=description, domain=COMPLIANCE_DOMAIN, requires_decision=category != "renewal",
    )  # fmt: skip
    task.category = category
    task.due_at = due_at
    session.commit()
    return task


@dataclass
class ExpertOption:
    supplier_id: uuid.UUID
    name: str
    kind: str
    fee_min: float | None
    fee_max: float | None
    basis: str
    confidence: str
    has_contact: bool


def recommend(session: Session, task: Task) -> dict:
    _, expert_kind, (h_min, h_max) = CATEGORIES.get(task.category or "other", CATEGORIES["other"])
    label = category_label(task.category)
    if expert_kind is None:
        return {"needs_expert": False, "statement": tx("Cette demande peut être traitée en interne (suivi d'échéance).", "This request can be handled internally (deadline follow-up)."), "options": []}

    experts = session.query(Supplier).filter_by(company_id=task.company_id, supplier_kind=expert_kind).all()
    options = []
    for e in experts:
        if e.fee_rate_min is not None and e.fee_rate_max is not None:
            rate, basis, confidence = (e.fee_rate_min, e.fee_rate_max), "estimated", "medium"
        else:
            rate, basis, confidence = BENCHMARK_RATES[expert_kind], "benchmark", "low"
        fee = (round(h_min * rate[0], -1), round(h_max * rate[1], -1)) if rate[1] else (None, None)
        has_contact = session.query(Contact.id).filter_by(related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=e.id).filter(Contact.email.isnot(None)).first() is not None
        options.append(ExpertOption(e.id, e.name, expert_kind, fee[0], fee[1], basis if fee[0] is not None else "unknown", confidence if fee[0] is not None else "none", has_contact))
    statement = tx(
        f"Cette demande ({label.lower()}) semble nécessiter l'intervention d'un {expert_kind_label(expert_kind)}.",
        f"This request ({label.lower()}) seems to require a {expert_kind_label(expert_kind)}.",
    )
    if not options:
        statement += tx(" Aucun cabinet de ce type n'est enregistré : ajoutez-le comme fournisseur de services.", " No firm of this type is recorded: add it as a service provider.")
    return {
        "needs_expert": True,
        "expert_kind": expert_kind,
        "expert_kind_label": expert_kind_label(expert_kind),
        "statement": statement,
        "hours_benchmark": [h_min, h_max],
        "options": [asdict(o) for o in options],
        "note": tx("Honoraires = heures de référence pour ce type de demande × taux horaire (déclaré par le cabinet, sinon référence marché). Estimation, pas un devis.", "Fees = reference hours for this type of request × hourly rate (declared by the firm, otherwise market reference). An estimate, not a quote."),
    }


def list_requests(session: Session, company_id: uuid.UUID) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = []
    for t in session.query(Task).filter_by(company_id=company_id, domain=COMPLIANCE_DOMAIN).all():
        edges = related_edges(session, "task", t.id)
        due = _as_aware_utc(t.due_at) if t.due_at else None
        open_ = t.status not in {TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.EXECUTED, TaskStatus.REJECTED}
        rows.append(
            {
                "id": t.id, "title": text_of(t, "title"), "description": text_of(t, "description"), "category": t.category,
                "category_label": category_label(t.category), "status": t.status.value,
                "due_at": t.due_at, "overdue": bool(open_ and due and due < now), "open": open_,
                "linked": {k: sum(1 for e in edges if e.type == k) for k in ("commercial_document", "communication", "document")},
            }
        )  # fmt: skip
    return sorted(rows, key=lambda r: (not r["open"], r["due_at"] is None, _as_aware_utc(r["due_at"]) if r["due_at"] else now))
