"""Commercial documents: create, derive (the chain), edit, move through
their lifecycle (V2, brain/transactional_model.md).

Every write goes through here so that numbering, party rules, the
`derived_from` chain, ledger posting and Business Events can never be
skipped by a caller."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.entities import (
    PROCUREMENT_KINDS,
    SALES_KINDS,
    CommercialDocument,
    CommercialDocumentLine,
    CostItem,
    CostKind,
    Customer,
    DocumentKind,
    Product,
    ProductSupplier,
    Supplier,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.objects.graph import document_chain, document_parents
from app.objects.links import create_link
from app.transactions import posting
from app.transactions.lifecycle import DERIVATIONS, KINDS, SYSTEM_STATUSES, allowed_transitions, kind_label, status_label
from app.transactions.margin import estimate_planned_unit_cost

DOCUMENT_CREATED = "DocumentCreated"
DOCUMENT_STATUS_CHANGED = "DocumentStatusChanged"

# Default wait before a sent quote / RFQ is due for a follow-up when the
# user sets none. A product default, shown as such, not a learned value.
DEFAULT_FOLLOW_UP_DAYS = 7


class DocumentError(ValueError):
    pass


@dataclass
class NewCustomer:
    name: str
    country: str | None = None
    status: str = "prospect"


@dataclass
class NewProduct:
    name: str
    sku: str | None = None
    sale_price: float | None = None
    unit_cost: float | None = None
    brand: str | None = None
    unit: str | None = None


@dataclass
class LineInput:
    product_id: uuid.UUID | None = None
    new_product: NewProduct | None = None
    description: str | None = None
    quantity: float = 1.0
    unit_price: float | None = None
    price_basis: ValueBasis | None = None
    lead_time_min_days: float | None = None
    lead_time_max_days: float | None = None
    lead_time_basis: ValueBasis | None = None
    moq: float | None = None
    spq: float | None = None
    # Carried from the source line when deriving (quote -> order), so the
    # planned cost stays the one estimated when the deal was priced.
    planned_unit_cost: float | None = None
    planned_cost_basis: ValueBasis | None = None
    planned_cost_source: str | None = None


@dataclass
class DocumentInput:
    kind: DocumentKind
    customer_id: uuid.UUID | None = None
    new_customer: NewCustomer | None = None
    supplier_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    title: str | None = None
    external_reference: str | None = None
    internal_reference: str | None = None
    issued_at: datetime | None = None
    due_at: datetime | None = None
    follow_up_at: datetime | None = None
    payment_terms: str | None = None
    notes: str | None = None
    source: str = "manual"
    lines: list[LineInput] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def next_number(session: Session, company_id: uuid.UUID, kind: DocumentKind, at: datetime | None = None) -> str:
    """`PREFIX-YYYY-NNNN`, sequential per company, kind and year. Derived
    from the highest existing number rather than a counter table: correct
    under SQLite's single writer; a real sequence is the Postgres-era fix."""

    year = (at or _now()).year
    prefix = f"{KINDS[kind].prefix}-{year}-"
    numbers = [
        row.number
        for row in session.query(CommercialDocument.number)
        .filter(CommercialDocument.company_id == company_id, CommercialDocument.number.like(f"{prefix}%"))
        .all()
    ]
    highest = max((int(n.rsplit("-", 1)[1]) for n in numbers if n.rsplit("-", 1)[1].isdigit()), default=0)
    return f"{prefix}{highest + 1:04d}"


# --- Parties and products ----------------------------------------------------


def _resolve_customer(session: Session, company_id: uuid.UUID, data: DocumentInput) -> uuid.UUID | None:
    if data.customer_id is not None:
        customer = session.get(Customer, data.customer_id)
        if customer is None or customer.company_id != company_id:
            raise DocumentError(tx("Client introuvable", "Customer not found"))
        return customer.id
    if data.new_customer is not None and data.new_customer.name.strip():
        name = data.new_customer.name.strip()
        # Never a second representation of an existing customer.
        existing = session.query(Customer).filter(Customer.company_id == company_id, Customer.name.ilike(name)).first()
        if existing is not None:
            return existing.id
        customer = Customer(company_id=company_id, name=name, country=data.new_customer.country, status=data.new_customer.status)
        session.add(customer)
        session.flush()
        return customer.id
    return None


def resolve_or_create_product(session: Session, company_id: uuid.UUID, new_product: NewProduct) -> Product:
    """One product, one representation: a new product whose reference (sku)
    or exact name already exists IS that product -- it is reused, never
    duplicated (brain/decisions.md #32)."""

    name = new_product.name.strip()
    if not name:
        raise DocumentError(tx("Le nom du produit est obligatoire", "The product name is required"))
    query = session.query(Product).filter(Product.company_id == company_id)
    if new_product.sku:
        by_sku = query.filter(Product.sku == new_product.sku.strip()).first()
        if by_sku is not None:
            return by_sku
    by_name = query.filter(Product.name.ilike(name)).first()
    if by_name is not None:
        return by_name
    product = Product(
        company_id=company_id,
        name=name,
        sku=new_product.sku.strip() if new_product.sku else None,
        sale_price=new_product.sale_price,
        unit_cost=new_product.unit_cost,
        brand=new_product.brand,
        unit=new_product.unit,
    )
    session.add(product)
    session.flush()
    return product


def _default_price(session: Session, kind: DocumentKind, product: Product | None, supplier_id: uuid.UUID | None) -> tuple[float | None, ValueBasis]:
    if product is None:
        return None, ValueBasis.UNKNOWN
    if kind in SALES_KINDS:
        return (product.sale_price, product.sale_price_basis) if product.sale_price is not None else (None, ValueBasis.UNKNOWN)
    if supplier_id is not None:
        terms = session.query(ProductSupplier).filter_by(product_id=product.id, supplier_id=supplier_id).first()
        if terms is not None and terms.unit_price is not None:
            return terms.unit_price, terms.price_basis
    return None, ValueBasis.UNKNOWN


def _supplier_terms(session: Session, product_id: uuid.UUID | None, supplier_id: uuid.UUID | None) -> ProductSupplier | None:
    if product_id is None or supplier_id is None:
        return None
    return session.query(ProductSupplier).filter_by(product_id=product_id, supplier_id=supplier_id).first()


def _build_line(session: Session, company_id: uuid.UUID, doc: CommercialDocument, position: int, line: LineInput) -> CommercialDocumentLine:
    product: Product | None = None
    if line.product_id is not None:
        product = session.get(Product, line.product_id)
        if product is None or product.company_id != company_id:
            raise DocumentError(tx("Produit introuvable", "Product not found"))
    elif line.new_product is not None:
        product = resolve_or_create_product(session, company_id, line.new_product)

    if line.unit_price is not None:
        unit_price, basis = line.unit_price, line.price_basis or ValueBasis.DECLARED
    else:
        unit_price, basis = _default_price(session, doc.kind, product, doc.supplier_id)

    lead_min, lead_max, lead_basis = line.lead_time_min_days, line.lead_time_max_days, line.lead_time_basis
    moq, spq = line.moq, line.spq
    terms = _supplier_terms(session, product.id if product else None, doc.supplier_id) if doc.kind in PROCUREMENT_KINDS else None
    if terms is None and product is not None and doc.supplier_id is not None and doc.kind in PROCUREMENT_KINDS:
        # A supplier quoting/selling a product IS a product<->supplier
        # relation: record it once, so the catalog and the benchmark see it.
        session.add(
            ProductSupplier(
                company_id=company_id, product_id=product.id, supplier_id=doc.supplier_id,
                unit_price=line.unit_price, price_basis=line.price_basis or ValueBasis.DECLARED,
                lead_time_min_days=line.lead_time_min_days, lead_time_max_days=line.lead_time_max_days,
                lead_time_basis=line.lead_time_basis or (ValueBasis.DECLARED if line.lead_time_min_days is not None else ValueBasis.UNKNOWN),
                moq=line.moq, spq=line.spq, source=f"document:{doc.number}",
            )
        )  # fmt: skip
        session.flush()
    elif terms is not None:
        if lead_min is None and lead_max is None:
            lead_min, lead_max, lead_basis = terms.lead_time_min_days, terms.lead_time_max_days, terms.lead_time_basis
        moq = moq if moq is not None else terms.moq
        spq = spq if spq is not None else terms.spq

    planned_unit_cost, planned_basis, planned_source = line.planned_unit_cost, line.planned_cost_basis, line.planned_cost_source
    if doc.kind in SALES_KINDS and planned_unit_cost is None and product is not None:
        estimate = estimate_planned_unit_cost(session, doc, product)
        if estimate.unit_cost is not None:
            planned_unit_cost, planned_basis, planned_source = estimate.unit_cost, ValueBasis(estimate.basis), estimate.source_label

    return CommercialDocumentLine(
        position=position,
        planned_unit_cost=planned_unit_cost,
        planned_cost_basis=planned_basis,
        planned_cost_source=planned_source,
        product_id=product.id if product else None,
        description=line.description or (product.name if product else None),
        quantity=line.quantity,
        unit=product.unit if product else None,
        unit_price=unit_price,
        price_basis=basis,
        lead_time_min_days=lead_min,
        lead_time_max_days=lead_max,
        lead_time_basis=lead_basis or (ValueBasis.DECLARED if lead_min is not None else ValueBasis.UNKNOWN),
        moq=moq,
        spq=spq,
    )


def _check_parties(kind: DocumentKind, customer_id, supplier_id) -> None:
    spec = KINDS[kind]
    if spec.party == "customer" and customer_id is None:
        raise DocumentError(tx(f"Un(e) {spec.label.lower()} doit être rattaché(e) à un client", f"A {kind_label(kind).lower()} must be linked to a customer"))
    if kind in {DocumentKind.SUPPLIER_QUOTE, DocumentKind.PURCHASE_ORDER, DocumentKind.RECEPTION, DocumentKind.SUPPLIER_INVOICE} and supplier_id is None:
        raise DocumentError(tx(f"Un(e) {spec.label.lower()} doit être rattaché(e) à un fournisseur", f"A {kind_label(kind).lower()} must be linked to a supplier"))


# --- Create / derive -----------------------------------------------------------


def create_document(session: Session, event_bus: EventBus, company_id: uuid.UUID, data: DocumentInput, owner_user_id: uuid.UUID | None = None) -> CommercialDocument:
    customer_id = _resolve_customer(session, company_id, data)
    if data.supplier_id is not None:
        supplier = session.get(Supplier, data.supplier_id)
        if supplier is None or supplier.company_id != company_id:
            raise DocumentError(tx("Fournisseur introuvable", "Supplier not found"))
    _check_parties(data.kind, customer_id, data.supplier_id)

    doc = CommercialDocument(
        company_id=company_id,
        kind=data.kind,
        number=next_number(session, company_id, data.kind, data.issued_at),
        status=KINDS[data.kind].initial_status,
        title=data.title,
        customer_id=customer_id,
        supplier_id=data.supplier_id,
        contact_id=data.contact_id,
        external_reference=data.external_reference,
        internal_reference=data.internal_reference,
        issued_at=data.issued_at or _now(),
        due_at=data.due_at,
        follow_up_at=data.follow_up_at,
        payment_terms=data.payment_terms,
        notes=data.notes,
        owner_user_id=owner_user_id,
        source=data.source,
    )
    session.add(doc)
    session.flush()
    for i, line in enumerate(data.lines):
        doc.lines.append(_build_line(session, company_id, doc, i, line))
    session.commit()
    session.refresh(doc)
    _publish(event_bus, DOCUMENT_CREATED, doc, {"number": doc.number})
    return doc


def derive_document(
    session: Session,
    event_bus: EventBus,
    source: CommercialDocument,
    target_kind: DocumentKind,
    *,
    supplier_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> CommercialDocument:
    """Creates the next document of a chain from `source`, copying parties
    and lines, and links it `derived_from` the source -- the traceability
    that lets anyone walk an order back to the request that started it."""

    if target_kind not in DERIVATIONS.get(source.kind, ()):
        raise DocumentError(tx(f"Impossible de créer un(e) {KINDS[target_kind].label.lower()} depuis un(e) {KINDS[source.kind].label.lower()}", f"Cannot create a {kind_label(target_kind).lower()} from a {kind_label(source.kind).lower()}"))

    target_supplier = supplier_id or (source.supplier_id if target_kind in PROCUREMENT_KINDS else None)
    copy_prices_from_source = (
        # Same side of the flow: a quote's prices become the order's prices,
        # a supplier quote's prices become the PO's -- declared by the same party.
        (source.kind in SALES_KINDS and target_kind in SALES_KINDS)
        or (source.kind in {DocumentKind.SUPPLIER_QUOTE, DocumentKind.PURCHASE_ORDER} and target_kind in PROCUREMENT_KINDS)
        # A supplier claim is priced as the goods were bought/invoiced.
        or (target_kind == DocumentKind.SUPPLIER_CREDIT_NOTE)
    )

    # A credit note drawn from a delivery/reception with recorded
    # non-conformities credits only the non-conforming quantities.
    source_lines = list(source.lines)
    nonconforming_only = target_kind in {DocumentKind.CUSTOMER_CREDIT_NOTE, DocumentKind.SUPPLIER_CREDIT_NOTE} and any(
        (ln.quantity_nonconforming or 0) > 0 for ln in source_lines
    )
    if nonconforming_only:
        source_lines = [ln for ln in source_lines if (ln.quantity_nonconforming or 0) > 0]

    lines: list[LineInput] = []
    for line in source_lines:
        keep_price = copy_prices_from_source and line.unit_price is not None
        lines.append(
            LineInput(
                product_id=line.product_id,
                description=(f"Non-conformité : {line.nonconformity_note}" if nonconforming_only and line.nonconformity_note else line.description),
                quantity=line.quantity_nonconforming if nonconforming_only else line.quantity,
                unit_price=line.unit_price if keep_price else None,
                # A supplier invoice copied from its PO is only DECLARED until
                # a human approves it against the real invoice (then OBSERVED).
                price_basis=line.price_basis if keep_price else None,
                lead_time_min_days=line.lead_time_min_days if keep_price else None,
                lead_time_max_days=line.lead_time_max_days if keep_price else None,
                lead_time_basis=line.lead_time_basis if keep_price else None,
                moq=line.moq if keep_price else None,
                spq=line.spq if keep_price else None,
                planned_unit_cost=line.planned_unit_cost,
                planned_cost_basis=line.planned_cost_basis,
                planned_cost_source=line.planned_cost_source,
            )
        )

    data = DocumentInput(
        kind=target_kind,
        customer_id=source.customer_id,
        supplier_id=target_supplier,
        contact_id=source.contact_id if (KINDS[source.kind].party == KINDS[target_kind].party) else None,
        title=source.title,
        # A reception is due when the PO promised it.
        due_at=source.due_at if target_kind == DocumentKind.RECEPTION else None,
        payment_terms=source.payment_terms if target_kind in {DocumentKind.PURCHASE_ORDER, DocumentKind.SUPPLIER_INVOICE} else None,
        lines=lines,
    )
    doc = create_document(session, event_bus, source.company_id, data, owner_user_id)
    create_link(
        session,
        company_id=source.company_id,
        source_type="commercial_document",
        source_id=doc.id,
        target_type="commercial_document",
        target_id=source.id,
        relation="derived_from",
        origin="system",
    )
    if target_kind == DocumentKind.PURCHASE_ORDER and source.kind == DocumentKind.SUPPLIER_QUOTE:
        # Copy the supplier quote's non-product costs (e.g. quoted transport).
        for cost in source.cost_items:
            doc.cost_items.append(
                CostItem(
                    company_id=doc.company_id, document_id=doc.id, kind=cost.kind, label=cost.label,
                    amount_min=cost.amount_min, amount_max=cost.amount_max, basis=cost.basis,
                    confidence=cost.confidence, reference=cost.reference,
                )
            )  # fmt: skip
        session.commit()
    _advance_after_derivation(session, event_bus, source, target_kind)
    session.refresh(doc)
    return doc


# Ordering a purchase request walks its whole lifecycle, one valid step at
# a time from wherever it is (a draft ordered directly still passes through
# each state, so its history stays coherent).
_PR_PATH_TO_ORDERED = ("consulting", "comparing", "decided", "ordered")


def _advance_after_derivation(session: Session, event_bus: EventBus, source: CommercialDocument, target_kind: DocumentKind) -> None:
    """The obvious status consequences of moving the deal forward, applied
    only when they are valid transitions -- never forced."""

    K = DocumentKind
    moves: list[tuple[CommercialDocument, str]] = []
    if source.kind == K.CUSTOMER_REQUEST and target_kind == K.CUSTOMER_QUOTE:
        moves.append((source, "quoting"))
    if source.kind == K.PURCHASE_REQUEST and target_kind == K.SUPPLIER_QUOTE:
        moves.append((source, "consulting"))
    if source.kind == K.CUSTOMER_QUOTE and target_kind == K.CUSTOMER_ORDER:
        moves.append((source, "accepted"))
        for parent_id in document_parents(session, source.id):
            parent = session.get(CommercialDocument, parent_id)
            if parent is not None and parent.kind == K.CUSTOMER_REQUEST:
                moves.append((parent, "won"))
    if target_kind == K.PURCHASE_ORDER:
        if source.kind == K.SUPPLIER_QUOTE:
            moves.append((source, "selected"))
            for parent_id in document_parents(session, source.id):
                parent = session.get(CommercialDocument, parent_id)
                if parent is not None and parent.kind == K.PURCHASE_REQUEST:
                    moves += [(parent, s) for s in _PR_PATH_TO_ORDERED]
        elif source.kind == K.PURCHASE_REQUEST:
            moves += [(source, s) for s in _PR_PATH_TO_ORDERED]
    for doc, status in moves:
        if status in allowed_transitions(doc.kind, doc.status):
            change_status(session, event_bus, doc, status)


# --- Edit ----------------------------------------------------------------------


EDITABLE_FIELDS = {"title", "external_reference", "internal_reference", "due_at", "follow_up_at", "payment_terms", "notes", "contact_id", "carrier", "tracking_number"}


def update_document(session: Session, doc: CommercialDocument, changes: dict) -> CommercialDocument:
    for key, value in changes.items():
        if key not in EDITABLE_FIELDS:
            raise DocumentError(tx(f"Champ non modifiable : {key}", f"Field cannot be changed: {key}"))
        setattr(doc, key, value)
    session.commit()
    session.refresh(doc)
    return doc


def add_line(session: Session, doc: CommercialDocument, line: LineInput) -> CommercialDocumentLine:
    _ensure_editable(doc)
    new_line = _build_line(session, doc.company_id, doc, len(doc.lines), line)
    doc.lines.append(new_line)
    session.commit()
    session.refresh(new_line)
    return new_line


def update_line(session: Session, doc: CommercialDocument, line_id: uuid.UUID, changes: dict) -> CommercialDocumentLine:
    _ensure_editable(doc)
    line = next((ln for ln in doc.lines if ln.id == line_id), None)
    if line is None:
        raise DocumentError(tx("Ligne introuvable", "Line not found"))
    allowed = {"description", "quantity", "unit_price", "price_basis", "lead_time_min_days", "lead_time_max_days", "lead_time_basis", "moq", "spq"}
    for key, value in changes.items():
        if key not in allowed:
            raise DocumentError(tx(f"Champ de ligne non modifiable : {key}", f"Line field cannot be changed: {key}"))
        setattr(line, key, value)
    if "unit_price" in changes and "price_basis" not in changes and changes["unit_price"] is not None:
        # A human typing a price declares it; it is no longer "unknown".
        line.price_basis = ValueBasis.DECLARED if line.price_basis == ValueBasis.UNKNOWN else line.price_basis
    session.commit()
    session.refresh(line)
    return line


def remove_line(session: Session, doc: CommercialDocument, line_id: uuid.UUID) -> None:
    _ensure_editable(doc)
    line = next((ln for ln in doc.lines if ln.id == line_id), None)
    if line is None:
        raise DocumentError(tx("Ligne introuvable", "Line not found"))
    doc.lines.remove(line)
    session.commit()


def add_cost_item(
    session: Session,
    doc: CommercialDocument,
    *,
    kind: CostKind,
    amount_min: float,
    amount_max: float | None,
    basis: ValueBasis,
    label: str | None = None,
    confidence: str = "medium",
    reference: str | None = None,
    line_id: uuid.UUID | None = None,
) -> CostItem:
    amount_max = amount_min if amount_max is None else amount_max
    if amount_max < amount_min:
        raise DocumentError(tx("Le montant maximum doit être supérieur ou égal au minimum", "The maximum amount must be greater than or equal to the minimum"))
    if basis == ValueBasis.OBSERVED and amount_max != amount_min:
        raise DocumentError(tx("Un coût observé est un montant exact, pas une fourchette", "An observed cost is an exact amount, not a range"))
    item = CostItem(
        company_id=doc.company_id, document_id=doc.id, line_id=line_id, kind=kind, label=label,
        amount_min=amount_min, amount_max=amount_max, basis=basis, confidence=confidence, reference=reference,
    )  # fmt: skip
    # Through the relationship, so an already-loaded document sees its new
    # cost immediately (sessions don't expire on commit).
    doc.cost_items.append(item)
    session.commit()
    session.refresh(item)
    return item


# Statuses after which a document's lines are a commitment (sent to or
# confirmed by the other party, or already posted to the ledger).
_LOCKED_STATUSES: dict[DocumentKind, frozenset[str]] = {
    DocumentKind.CUSTOMER_QUOTE: frozenset({"sent"}),
    DocumentKind.CUSTOMER_ORDER: frozenset({"sent", "acknowledged", "confirmed", "delivered", "invoiced"}),
    DocumentKind.CUSTOMER_DELIVERY: frozenset({"shipped"}),
    DocumentKind.CUSTOMER_INVOICE: frozenset({"issued", "partially_paid"}),
    DocumentKind.PURCHASE_ORDER: frozenset({"sent", "confirmed", "received"}),
    DocumentKind.SUPPLIER_INVOICE: frozenset({"approved", "partially_paid"}),
    DocumentKind.CUSTOMER_CREDIT_NOTE: frozenset({"submitted", "accepted", "validated", "applied"}),
    DocumentKind.SUPPLIER_CREDIT_NOTE: frozenset({"confirmed"}),
}


def is_editable(doc: CommercialDocument) -> bool:
    return doc.status not in KINDS[doc.kind].terminal and doc.status not in _LOCKED_STATUSES.get(doc.kind, frozenset())


def _ensure_editable(doc: CommercialDocument) -> None:
    if not is_editable(doc):
        raise DocumentError(tx("Ce document n'est plus modifiable dans son état actuel", "This document can no longer be edited in its current state"))


# --- Lifecycle -----------------------------------------------------------------


def change_status(
    session: Session, event_bus: EventBus, doc: CommercialDocument, new_status: str, *, occurred_at: datetime | None = None, system: bool = False
) -> CommercialDocument:
    """`system=True` only from app.billing / the HITL executor: statuses in
    SYSTEM_STATUSES follow a recorded fact (payment, approval, imputation)
    and are never set by a plain status change."""

    if new_status not in allowed_transitions(doc.kind, doc.status):
        raise DocumentError(tx(f"Transition impossible : {doc.status} → {new_status}", f"Transition not allowed: {status_label(doc.kind, doc.status)} → {status_label(doc.kind, new_status)}"))
    if not system and new_status in SYSTEM_STATUSES.get(doc.kind, frozenset()):
        raise DocumentError(tx("Ce statut découle d'un fait enregistré (paiement, validation ou imputation) : utilisez l'action correspondante", "This status follows from a recorded fact (payment, validation or application): use the corresponding action"))
    old_status = doc.status
    doc.status = new_status
    now = occurred_at or _now()

    if new_status in {"sent"} and doc.kind in {DocumentKind.CUSTOMER_QUOTE, DocumentKind.SUPPLIER_QUOTE, DocumentKind.PURCHASE_ORDER}:
        # Sending IS the issue date of a quote/RFQ/PO (a draft's creation
        # date is not what the other party received).
        doc.issued_at = now
        if doc.kind == DocumentKind.CUSTOMER_QUOTE and doc.follow_up_at is None:
            doc.follow_up_at = now + timedelta(days=DEFAULT_FOLLOW_UP_DAYS)
    if new_status in {"received", "delivered", "paid"}:
        doc.completed_at = now
    if doc.kind == DocumentKind.SUPPLIER_INVOICE and new_status == "approved":
        # A human validated this invoice against the real one: its amounts
        # are now OBSERVED actual costs (the only path that makes them so).
        for line in doc.lines:
            if line.unit_price is not None:
                line.price_basis = ValueBasis.OBSERVED
    if new_status in {"accepted", "rejected", "expired", "selected", "declined", "cancelled"}:
        doc.follow_up_at = None

    session.commit()
    session.refresh(doc)
    posting.on_status_changed(session, event_bus, doc, old_status)
    _publish(event_bus, DOCUMENT_STATUS_CHANGED, doc, {"from": old_status, "to": new_status, "number": doc.number})
    from app.billing.service import on_document_status_changed

    on_document_status_changed(session, event_bus, doc, old_status)
    return doc


def _publish(event_bus: EventBus, event_type: str, doc: CommercialDocument, extra: dict) -> None:
    event_bus.publish(
        BusinessEvent(
            event_type=event_type,
            source="transactions",
            payload={
                "subject_type": "commercial_document",
                "subject_id": str(doc.id),
                "document_id": str(doc.id),
                "kind": doc.kind.value,
                "customer_id": str(doc.customer_id) if doc.customer_id else None,
                "supplier_id": str(doc.supplier_id) if doc.supplier_id else None,
                **extra,
            },
        )
    )


def chain_of(session: Session, doc: CommercialDocument) -> list[CommercialDocument]:
    return document_chain(session, doc.id)
