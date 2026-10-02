"""Billing API (V2.2, brain/billing.md): payments, instalments, accounts,
credit notes, non-conformities. Reads are derived views; every write is a
recorded fact, checked by the caller's permissions:

- recording / allocating a payment, setting a schedule, imputing a credit
  note, recording a refund -> write:finance
- reporting a non-conformity -> write:operations
- asking for a credit note's internal validation -> write:sales (the
  validation itself is a HITL approval, finance domain)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.access.deps import CurrentUser, get_current_user, require
from app.access.policy import VIEW_FINANCE, VIEW_PROCUREMENT, VIEW_SALES, WRITE_FINANCE, WRITE_OPERATIONS, WRITE_SALES
from app.billing import service
from app.core.entities import CashMovement, CommercialDocument, Company, Customer, Supplier
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus

router = APIRouter(prefix="/billing", tags=["billing"])


class PaymentIn(BaseModel):
    amount: float
    invoice_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    account_id: uuid.UUID | None = None
    label: str | None = None


class AllocateIn(BaseModel):
    invoice_id: uuid.UUID


class InstallmentIn(BaseModel):
    due_at: datetime
    amount: float
    label: str | None = None


class ScheduleIn(BaseModel):
    installments: list[InstallmentIn]


class RefundIn(BaseModel):
    occurred_at: datetime | None = None
    account_id: uuid.UUID | None = None


class NonConformityIn(BaseModel):
    line_id: uuid.UUID
    quantity: float
    note: str


def _doc(db: Session, company: Company, doc_id: uuid.UUID) -> CommercialDocument:
    doc = db.get(CommercialDocument, doc_id)
    if doc is None or doc.company_id != company.id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return doc


def _guard(fn, db: Session):
    try:
        return fn()
    except service.BillingError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_any(user: CurrentUser, *permissions: str) -> None:
    if not any(user.can(p) for p in permissions):
        raise HTTPException(status_code=403, detail="Votre profil n'a pas accès à ces informations.")


@router.get("/overview")
def overview(db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(VIEW_FINANCE))) -> dict:
    return service.billing_overview(db, company.id)


@router.get("/accounts/customer/{customer_id}")
def customer_account(customer_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    _require_any(user, VIEW_FINANCE, VIEW_SALES)
    customer = db.get(Customer, customer_id)
    if customer is None or customer.company_id != company.id:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return service.party_account(db, company.id, customer_id=customer_id)


@router.get("/accounts/supplier/{supplier_id}")
def supplier_account(supplier_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    _require_any(user, VIEW_FINANCE, VIEW_PROCUREMENT)
    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.company_id != company.id:
        raise HTTPException(status_code=404, detail="Fournisseur introuvable")
    return service.party_account(db, company.id, supplier_id=supplier_id)


@router.post("/payments")
def record_payment(
    payload: PaymentIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_FINANCE)),
) -> dict:
    invoice = _doc(db, company, payload.invoice_id) if payload.invoice_id else None
    movement = _guard(
        lambda: service.record_payment(
            db, event_bus, company.id, amount=payload.amount, invoice=invoice, customer_id=payload.customer_id, supplier_id=payload.supplier_id,
            occurred_at=payload.occurred_at, account_id=payload.account_id, label=payload.label,
        ),
        db,
    )  # fmt: skip
    return {"movement_id": movement.id, "settlement": service.settlement(db, invoice) if invoice else None}


@router.post("/payments/{movement_id}/allocate")
def allocate_payment(
    movement_id: uuid.UUID,
    payload: AllocateIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_FINANCE)),
) -> dict:
    movement = db.get(CashMovement, movement_id)
    if movement is None or movement.company_id != company.id:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    invoice = _doc(db, company, payload.invoice_id)
    _guard(lambda: service.allocate_payment(db, event_bus, movement, invoice), db)
    return service.settlement(db, invoice)


@router.get("/documents/{doc_id}")
def document_billing(doc_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    """Settlement (invoices), fulfilment + payment position (orders),
    credit-note position (credit notes), follow-up of the parent order
    (deliveries/receptions). Same data as in the document detail."""

    _require_any(user, VIEW_FINANCE, VIEW_SALES, VIEW_PROCUREMENT)
    return service_view(db, _doc(db, company, doc_id))


def service_view(db: Session, doc: CommercialDocument) -> dict:
    from app.core.entities import DocumentKind as K

    data: dict = {}
    if doc.kind in service.INVOICE_KINDS:
        data["settlement"] = service.settlement(db, doc)
    if doc.kind in {K.CUSTOMER_ORDER, K.PURCHASE_ORDER}:
        data["fulfilment"] = service.fulfilment(db, doc)
        data["payment"] = service.order_payment(db, doc)
    if doc.kind in service.CREDIT_KINDS:
        data["credit"] = service.credit_view(db, doc)
    if doc.kind in {K.CUSTOMER_DELIVERY, K.RECEPTION}:
        order = service.parent_order(db, doc)
        data["fulfilment"] = service.fulfilment(db, order) if order else None
    return data


@router.put("/documents/{doc_id}/installments")
def set_installments(
    doc_id: uuid.UUID,
    payload: ScheduleIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_FINANCE)),
) -> dict:
    invoice = _doc(db, company, doc_id)
    _guard(lambda: service.set_installments(db, event_bus, invoice, [i.model_dump() for i in payload.installments]), db)
    return service.settlement(db, invoice)


@router.post("/credit-notes/{doc_id}/request-validation")
def request_validation(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_SALES)),
) -> dict:
    doc = _doc(db, company, doc_id)
    task = _guard(lambda: service.request_credit_validation(db, event_bus, doc), db)
    return {"task_id": task.id, "credit": service.credit_view(db, doc)}


@router.post("/credit-notes/{doc_id}/apply")
def apply_credit_note(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_FINANCE)),
) -> dict:
    doc = _doc(db, company, doc_id)
    _guard(lambda: service.apply_credit_note(db, event_bus, doc), db)
    return service.credit_view(db, doc)


@router.post("/credit-notes/{doc_id}/refund")
def record_refund(
    doc_id: uuid.UUID,
    payload: RefundIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_FINANCE)),
) -> dict:
    doc = _doc(db, company, doc_id)
    _guard(lambda: service.record_refund(db, event_bus, doc, occurred_at=payload.occurred_at, account_id=payload.account_id), db)
    return service.credit_view(db, doc)


@router.post("/documents/{doc_id}/nonconformity")
def report_nonconformity(
    doc_id: uuid.UUID,
    payload: NonConformityIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_OPERATIONS)),
) -> dict:
    doc = _doc(db, company, doc_id)
    return _guard(lambda: service.report_nonconformity(db, event_bus, doc, payload.line_id, payload.quantity, payload.note), db)
