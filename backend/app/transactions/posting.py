"""Ledger posting: how V2 documents feed V1's intelligence (V2,
brain/transactional_model.md).

V1's analytics, Baselines, Significance, Observation Engine and Risk rules
all read `Transaction` rows. Rather than rewriting them over documents, a
document *posts* ledger facts when -- and only when -- the business event
really happened:

  customer order confirmed   -> SALES_ORDER fact per product line
  reception received         -> PURCHASE_ORDER fact per product line
                                (occurred_at = actual reception date,
                                 expected_at = the PO's promised date: V1's
                                 supplier delivery performance, now fed by
                                 real receptions)
  supplier invoice approved  -> the reception facts of that PO are
                                re-valued at the invoiced (OBSERVED) price,
                                and an increase over the product's reference
                                cost goes through V1's own
                                `record_supplier_cost_increase` -> Risk path.
  customer invoice paid      -> the order's SALES_ORDER facts become PAID.

A supplier invoice is deliberately NOT posted as a separate INVOICE fact:
V1 sums PURCHASE_ORDER + INVOICE as costs, so posting both for one
purchase would count it twice (found by the V2 audit, brain/decisions.md #31).
Every posted fact points back to its document (source_document_id/line_id).
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.analytics import _as_aware_utc
from app.core.entities import (
    CommercialDocument,
    DocumentKind,
    Product,
    ProductSupplier,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.core.events.bus import EventBus
from app.objects.graph import document_chain, document_parents

# An approved invoice price at least this much above the product's reference
# cost is reported to V1's cost-increase path (same order of magnitude as
# V1's own procurement rules; a product setting, documented).
COST_INCREASE_REPORT_THRESHOLD = 0.02


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_or_none(value: datetime | None) -> datetime | None:
    return _as_aware_utc(value) if value is not None else None


def _already_posted(session: Session, line_id) -> bool:
    return session.query(Transaction.id).filter_by(source_line_id=line_id).first() is not None


def _parent_of_kind(session: Session, doc: CommercialDocument, kind: DocumentKind) -> CommercialDocument | None:
    for parent_id in document_parents(session, doc.id):
        parent = session.get(CommercialDocument, parent_id)
        if parent is not None and parent.kind == kind:
            return parent
    return None


def post_customer_order(session: Session, doc: CommercialDocument) -> int:
    posted = 0
    for line in doc.lines:
        if line.product_id is None or line.unit_price is None or _already_posted(session, line.id):
            continue
        session.add(
            Transaction(
                company_id=doc.company_id,
                customer_id=doc.customer_id,
                product_id=line.product_id,
                type=TransactionType.SALES_ORDER,
                status=TransactionStatus.CONFIRMED,
                amount=round(line.quantity * line.unit_price, 2),
                quantity=line.quantity,
                currency=doc.currency,
                occurred_at=_as_aware_utc(doc.issued_at or _now()),
                source_document_id=doc.id,
                source_line_id=line.id,
            )
        )
        posted += 1
    session.commit()
    return posted


def post_reception(session: Session, doc: CommercialDocument) -> int:
    purchase_order = _parent_of_kind(session, doc, DocumentKind.PURCHASE_ORDER)
    po_prices = {ln.product_id: ln.unit_price for ln in purchase_order.lines} if purchase_order else {}
    posted = 0
    for line in doc.lines:
        unit_price = po_prices.get(line.product_id, line.unit_price)
        if line.product_id is None or unit_price is None or _already_posted(session, line.id):
            continue
        session.add(
            Transaction(
                company_id=doc.company_id,
                supplier_id=doc.supplier_id,
                product_id=line.product_id,
                type=TransactionType.PURCHASE_ORDER,
                status=TransactionStatus.CONFIRMED,
                amount=round(line.quantity * unit_price, 2),
                quantity=line.quantity,
                currency=doc.currency,
                # Both normalized to aware UTC: SQLite hands back naive
                # datetimes, and V1's delay arithmetic subtracts the two.
                occurred_at=_as_aware_utc(doc.completed_at or _now()),
                expected_at=_aware_or_none((purchase_order.due_at if purchase_order else None) or doc.due_at),
                source_document_id=doc.id,
                source_line_id=line.id,
            )
        )
        posted += 1
    session.commit()
    return posted


def revalue_from_supplier_invoice(session: Session, event_bus: EventBus, invoice: CommercialDocument) -> int:
    """Re-values the reception facts of the invoiced PO at the invoiced
    price, records the OBSERVED price on the supplier's terms, and reports a
    material increase through V1's cost-increase path."""

    purchase_order = _parent_of_kind(session, invoice, DocumentKind.PURCHASE_ORDER)
    if purchase_order is None:
        return 0
    reception_ids = [
        d.id for d in document_chain(session, purchase_order.id)
        if d.kind == DocumentKind.RECEPTION and purchase_order.id in document_parents(session, d.id)
    ]  # fmt: skip
    revalued = 0
    for line in invoice.lines:
        if line.product_id is None or line.unit_price is None:
            continue
        facts = (
            session.query(Transaction)
            .filter(Transaction.source_document_id.in_(reception_ids), Transaction.product_id == line.product_id)
            .all()
            if reception_ids
            else []
        )
        for fact in facts:
            fact.amount = round((fact.quantity or line.quantity) * line.unit_price, 2)
            revalued += 1

        terms = session.query(ProductSupplier).filter_by(product_id=line.product_id, supplier_id=invoice.supplier_id).first()
        if terms is not None:
            terms.unit_price = line.unit_price
            terms.price_basis = line.price_basis
            terms.last_confirmed_at = _now()
    session.commit()

    for line in invoice.lines:
        _report_cost_increase(session, event_bus, invoice, line)
    return revalued


def _report_cost_increase(session: Session, event_bus: EventBus, invoice: CommercialDocument, line) -> None:
    from app.domains.procurement.service import ProcurementError, ProcurementService

    product = session.get(Product, line.product_id) if line.product_id else None
    if product is None or line.unit_price is None or product.unit_cost in (None, 0):
        return
    # V1's path only models the preferred supplier's reference cost.
    if product.supplier_id != invoice.supplier_id:
        return
    if (line.unit_price - product.unit_cost) / product.unit_cost < COST_INCREASE_REPORT_THRESHOLD:
        return
    try:
        ProcurementService(session, event_bus).record_supplier_cost_increase(invoice.supplier_id, product.id, line.unit_price)
    except ProcurementError:
        return


def mark_order_paid(session: Session, invoice: CommercialDocument) -> int:
    order = _parent_of_kind(session, invoice, DocumentKind.CUSTOMER_ORDER)
    if order is None:
        return 0
    facts = session.query(Transaction).filter_by(source_document_id=order.id).all()
    for fact in facts:
        fact.status = TransactionStatus.PAID
    session.commit()
    return len(facts)


def cancel_postings(session: Session, doc: CommercialDocument) -> int:
    facts = session.query(Transaction).filter_by(source_document_id=doc.id).all()
    for fact in facts:
        fact.status = TransactionStatus.CANCELLED
    session.commit()
    return len(facts)


def on_status_changed(session: Session, event_bus: EventBus, doc: CommercialDocument, old_status: str) -> None:
    K = DocumentKind
    if doc.kind == K.CUSTOMER_ORDER and doc.status == "confirmed":
        post_customer_order(session, doc)
    elif doc.kind == K.CUSTOMER_ORDER and doc.status == "cancelled":
        cancel_postings(session, doc)
    elif doc.kind == K.RECEPTION and doc.status == "received":
        post_reception(session, doc)
    elif doc.kind == K.SUPPLIER_INVOICE and doc.status == "approved":
        revalue_from_supplier_invoice(session, event_bus, doc)
    elif doc.kind == K.CUSTOMER_INVOICE and doc.status == "paid":
        mark_order_paid(session, doc)
