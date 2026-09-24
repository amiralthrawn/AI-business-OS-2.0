import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.access.deps import CurrentUser, get_current_user
from app.access.policy import DOMAIN_VIEW_PERMISSION
from app.core.entities import (
    PROCUREMENT_KINDS,
    SALES_KINDS,
    CommercialDocument,
    Company,
    Contact,
    CostKind,
    Customer,
    DocumentKind,
    Supplier,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.domains.procurement.benchmark import benchmark_suppliers
from app.objects.graph import document_chain
from app.objects.registry import summarize
from app.transactions import service
from app.transactions.lifecycle import DERIVATIONS, KIND_WRITE_PERMISSION, KINDS, status_label
from app.transactions.margin import compute_document_margin

router = APIRouter(prefix="/documents", tags=["documents"])


# --- Schemas ----------------------------------------------------------------------------


class NewCustomerIn(BaseModel):
    name: str
    country: str | None = None
    status: str = "prospect"


class NewProductIn(BaseModel):
    name: str
    sku: str | None = None
    sale_price: float | None = None
    unit_cost: float | None = None
    brand: str | None = None
    unit: str | None = None


class LineIn(BaseModel):
    product_id: uuid.UUID | None = None
    new_product: NewProductIn | None = None
    description: str | None = None
    quantity: float = 1.0
    unit_price: float | None = None
    price_basis: ValueBasis | None = None
    lead_time_min_days: float | None = None
    lead_time_max_days: float | None = None
    lead_time_basis: ValueBasis | None = None
    moq: float | None = None
    spq: float | None = None

    def to_input(self) -> service.LineInput:
        data = self.model_dump(exclude={"new_product"})
        return service.LineInput(**data, new_product=service.NewProduct(**self.new_product.model_dump()) if self.new_product else None)


class DocumentCreateIn(BaseModel):
    kind: DocumentKind
    customer_id: uuid.UUID | None = None
    new_customer: NewCustomerIn | None = None
    supplier_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    title: str | None = None
    external_reference: str | None = None
    internal_reference: str | None = None
    due_at: datetime | None = None
    follow_up_at: datetime | None = None
    payment_terms: str | None = None
    notes: str | None = None
    lines: list[LineIn] = []
    # Optional: create this document as derived from another (e.g. a quote
    # created from a customer request page keeps the chain).
    derived_from_id: uuid.UUID | None = None


class DocumentUpdateIn(BaseModel):
    title: str | None = None
    external_reference: str | None = None
    internal_reference: str | None = None
    due_at: datetime | None = None
    follow_up_at: datetime | None = None
    payment_terms: str | None = None
    notes: str | None = None
    contact_id: uuid.UUID | None = None


class StatusIn(BaseModel):
    status: str
    occurred_at: datetime | None = None


class DeriveIn(BaseModel):
    kind: DocumentKind
    supplier_id: uuid.UUID | None = None


class LineUpdateIn(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    price_basis: ValueBasis | None = None
    lead_time_min_days: float | None = None
    lead_time_max_days: float | None = None
    lead_time_basis: ValueBasis | None = None
    moq: float | None = None
    spq: float | None = None


class CostIn(BaseModel):
    kind: CostKind
    amount_min: float
    amount_max: float | None = None
    basis: ValueBasis
    label: str | None = None
    confidence: str = "medium"
    reference: str | None = None
    line_id: uuid.UUID | None = None


# --- Helpers ----------------------------------------------------------------------------


def _get(db: Session, company: Company, doc_id: uuid.UUID) -> CommercialDocument:
    doc = db.get(CommercialDocument, doc_id)
    if doc is None or doc.company_id != company.id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return doc


def _require_view(user: CurrentUser, kind: DocumentKind) -> None:
    if not user.can(DOMAIN_VIEW_PERMISSION[KINDS[kind].domain]):
        raise HTTPException(status_code=403, detail="Votre profil n'a pas accès à ce document.")


def _require_kind(user: CurrentUser, kind: DocumentKind) -> None:
    if not user.can(KIND_WRITE_PERMISSION[kind]):
        raise HTTPException(status_code=403, detail=f"Votre rôle ne permet pas de modifier un(e) {KINDS[kind].label.lower()}.")


def _party(db: Session, doc: CommercialDocument) -> dict | None:
    if doc.customer_id:
        c = db.get(Customer, doc.customer_id)
        return {"type": "customer", "id": c.id, "name": c.name, "status": c.status, "href": f"/data/customers/{c.id}"} if c else None
    if doc.supplier_id:
        s = db.get(Supplier, doc.supplier_id)
        return {"type": "supplier", "id": s.id, "name": s.name, "href": f"/data/suppliers/{s.id}"} if s else None
    return None


def _total(doc: CommercialDocument) -> float | None:
    if any(ln.unit_price is None for ln in doc.lines) or not doc.lines:
        return None
    return round(sum(ln.quantity * ln.unit_price for ln in doc.lines), 2)


def serialize_summary(db: Session, doc: CommercialDocument) -> dict:
    spec = KINDS[doc.kind]
    return {
        "id": doc.id,
        "kind": doc.kind.value,
        "kind_label": spec.label,
        "domain": spec.domain,
        "number": doc.number,
        "status": doc.status,
        "status_label": status_label(doc.kind, doc.status),
        "is_terminal": doc.status in spec.terminal,
        "title": doc.title,
        "party": _party(db, doc),
        "external_reference": doc.external_reference,
        "issued_at": doc.issued_at,
        "due_at": doc.due_at,
        "follow_up_at": doc.follow_up_at,
        "completed_at": doc.completed_at,
        "total": _total(doc),
        "total_is_complete": _total(doc) is not None,
        "currency": doc.currency,
        "line_count": len(doc.lines),
    }


def serialize_detail(db: Session, doc: CommercialDocument) -> dict:
    contact = db.get(Contact, doc.contact_id) if doc.contact_id else None
    data = serialize_summary(db, doc) | {
        "internal_reference": doc.internal_reference,
        "payment_terms": doc.payment_terms,
        "notes": doc.notes,
        "source": doc.source,
        "editable": service.is_editable(doc),
        "contact": {"id": contact.id, "name": contact.name, "email": contact.email} if contact else None,
        "lines": [
            {
                "id": ln.id, "position": ln.position, "product_id": ln.product_id,
                "product_name": ln.product.name if ln.product else None, "product_sku": ln.product.sku if ln.product else None,
                "description": ln.description, "quantity": ln.quantity, "unit": ln.unit,
                "unit_price": ln.unit_price, "price_basis": ln.price_basis.value,
                "total": round(ln.quantity * ln.unit_price, 2) if ln.unit_price is not None else None,
                "lead_time_min_days": ln.lead_time_min_days, "lead_time_max_days": ln.lead_time_max_days,
                "lead_time_basis": ln.lead_time_basis.value, "moq": ln.moq, "spq": ln.spq,
                "planned_unit_cost": ln.planned_unit_cost,
                "planned_cost_basis": ln.planned_cost_basis.value if ln.planned_cost_basis else None,
                "planned_cost_source": ln.planned_cost_source,
            }
            for ln in doc.lines
        ],  # fmt: skip
        "cost_items": [
            {
                "id": c.id, "kind": c.kind.value, "label": c.label, "amount_min": c.amount_min, "amount_max": c.amount_max,
                "basis": c.basis.value, "confidence": c.confidence, "reference": c.reference, "line_id": c.line_id,
            }
            for c in doc.cost_items
        ],  # fmt: skip
        # The whole deal, in creation order: every document of the chain.
        "chain": [serialize_summary(db, d) for d in document_chain(db, doc.id)],
    }
    if doc.kind in {DocumentKind.CUSTOMER_REQUEST, DocumentKind.CUSTOMER_QUOTE, DocumentKind.CUSTOMER_ORDER, DocumentKind.CUSTOMER_INVOICE}:
        data["margin"] = compute_document_margin(db, doc).to_dict()
    if doc.kind == DocumentKind.PURCHASE_REQUEST:
        data["benchmarks"] = [
            benchmark_suppliers(db, ln.product_id, ln.quantity, purchase_request_id=doc.id).to_dict() for ln in doc.lines if ln.product_id
        ]
    return data


# --- Routes -----------------------------------------------------------------------------


@router.get("/meta")
def meta() -> dict:
    """Kinds, statuses and derivations -- the frontend reads the lifecycle
    from here instead of hard-coding it."""

    return {
        "kinds": [
            {
                "kind": kind.value, "label": spec.label, "prefix": spec.prefix, "domain": spec.domain, "party": spec.party,
                "initial_status": spec.initial_status, "statuses": spec.status_labels, "terminal": sorted(spec.terminal),
                "derivations": [t.value for t in DERIVATIONS.get(kind, ())],
            }
            for kind, spec in KINDS.items()
        ],  # fmt: skip
        "value_basis": [b.value for b in ValueBasis],
        "cost_kinds": [c.value for c in CostKind],
    }


@router.get("/margins")
def order_margins(limit: int = 50, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    if not user.can("view:finance"):
        raise HTTPException(status_code=403, detail="Votre profil n'a pas accès à la finance.")
    """Planned vs current margin of every non-cancelled customer order --
    Finance's per-order view, computed by the same engine as a document page."""

    orders = (
        db.query(CommercialDocument)
        .filter(CommercialDocument.company_id == company.id, CommercialDocument.kind == DocumentKind.CUSTOMER_ORDER, CommercialDocument.status != "cancelled")
        .order_by(CommercialDocument.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = []
    for order in orders:
        margin = compute_document_margin(db, order).to_dict()
        rows.append({"document": serialize_summary(db, order), "current": margin["current"], "planned": margin["planned"]})
    return rows


@router.get("")
def list_documents(
    kind: list[DocumentKind] | None = Query(default=None),
    domain: str | None = None,
    status: str | None = None,
    open_only: bool = False,
    customer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    company: Company = Depends(current_company),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    query = db.query(CommercialDocument).filter(CommercialDocument.company_id == company.id)
    visible = [k for k in DocumentKind if user.can(DOMAIN_VIEW_PERMISSION[KINDS[k].domain])]
    query = query.filter(CommercialDocument.kind.in_(visible))
    if kind:
        query = query.filter(CommercialDocument.kind.in_(kind))
    if domain == "sales":
        query = query.filter(CommercialDocument.kind.in_(SALES_KINDS))
    elif domain == "procurement":
        query = query.filter(CommercialDocument.kind.in_(PROCUREMENT_KINDS))
    if status:
        query = query.filter(CommercialDocument.status == status)
    if customer_id:
        query = query.filter(CommercialDocument.customer_id == customer_id)
    if supplier_id:
        query = query.filter(CommercialDocument.supplier_id == supplier_id)
    if q:
        like = f"%{q}%"
        query = query.filter(CommercialDocument.number.ilike(like) | CommercialDocument.title.ilike(like) | CommercialDocument.external_reference.ilike(like))
    docs = query.order_by(CommercialDocument.created_at.desc()).limit(limit).all()
    if open_only:
        docs = [d for d in docs if d.status not in KINDS[d.kind].terminal]
    return [serialize_summary(db, d) for d in docs]


@router.post("")
def create_document(
    payload: DocumentCreateIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    _require_kind(user, payload.kind)
    owner = user.profile.id if user.profile else None
    try:
        if payload.derived_from_id is not None:
            source = _get(db, company, payload.derived_from_id)
            doc = service.derive_document(db, event_bus, source, payload.kind, supplier_id=payload.supplier_id, owner_user_id=owner)
        else:
            data = service.DocumentInput(
                kind=payload.kind,
                customer_id=payload.customer_id,
                new_customer=service.NewCustomer(**payload.new_customer.model_dump()) if payload.new_customer else None,
                supplier_id=payload.supplier_id,
                contact_id=payload.contact_id,
                title=payload.title,
                external_reference=payload.external_reference,
                internal_reference=payload.internal_reference,
                due_at=payload.due_at,
                follow_up_at=payload.follow_up_at,
                payment_terms=payload.payment_terms,
                notes=payload.notes,
                lines=[ln.to_input() for ln in payload.lines],
            )
            doc = service.create_document(db, event_bus, company.id, data, owner_user_id=owner)
    except service.DocumentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_detail(db, doc)


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_view(user, doc.kind)
    return serialize_detail(db, doc)


@router.get("/{doc_id}/margin")
def get_margin(doc_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    doc = _get(db, company, doc_id)
    try:
        return compute_document_margin(db, doc).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _mutate(fn, db: Session):
    try:
        return fn()
    except service.DocumentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{doc_id}")
def update_document(doc_id: uuid.UUID, payload: DocumentUpdateIn, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.update_document(db, doc, payload.model_dump(exclude_unset=True)), db)
    return serialize_detail(db, doc)


@router.post("/{doc_id}/status")
def change_status(
    doc_id: uuid.UUID, payload: StatusIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user),
) -> dict:  # fmt: skip
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.change_status(db, event_bus, doc, payload.status, occurred_at=payload.occurred_at), db)
    return serialize_detail(db, doc)


@router.post("/{doc_id}/derive")
def derive(
    doc_id: uuid.UUID, payload: DeriveIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user),
) -> dict:  # fmt: skip
    source = _get(db, company, doc_id)
    _require_kind(user, payload.kind)
    owner = user.profile.id if user.profile else None
    doc = _mutate(lambda: service.derive_document(db, event_bus, source, payload.kind, supplier_id=payload.supplier_id, owner_user_id=owner), db)
    return serialize_detail(db, doc)


@router.post("/{doc_id}/lines")
def add_line(doc_id: uuid.UUID, payload: LineIn, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.add_line(db, doc, payload.to_input()), db)
    return serialize_detail(db, doc)


@router.patch("/{doc_id}/lines/{line_id}")
def update_line(doc_id: uuid.UUID, line_id: uuid.UUID, payload: LineUpdateIn, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.update_line(db, doc, line_id, payload.model_dump(exclude_unset=True)), db)
    return serialize_detail(db, doc)


@router.delete("/{doc_id}/lines/{line_id}")
def remove_line(doc_id: uuid.UUID, line_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.remove_line(db, doc, line_id), db)
    return serialize_detail(db, doc)


@router.post("/{doc_id}/costs")
def add_cost(doc_id: uuid.UUID, payload: CostIn, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    doc = _get(db, company, doc_id)
    _require_kind(user, doc.kind)
    _mutate(lambda: service.add_cost_item(db, doc, **payload.model_dump()), db)
    return serialize_detail(db, doc)


__all__ = ["router", "serialize_summary", "summarize"]
