"""Deal / order / line margin (V2, brain/transactional_model.md).

Walks the document chain of a sales document (request, quote or order) and
prices every line's cost from the best source available, never upgrading
a source's nature:

  stage       source                                  basis
  actual      approved/paid supplier invoice line     OBSERVED
  committed   purchase order line                     DECLARED
  quoted      supplier quote line (selected first)    DECLARED
  catalog     supplier terms (ProductSupplier)        DECLARED
  reference   Product.unit_cost                       ESTIMATED
  unknown     nothing                                 UNKNOWN

Two views, so "less profitable than planned" has a concrete answer:
- planned: what could be known before committing (quoted > catalog > reference)
- current: the best source now (actual > committed > quoted > catalog > reference)

Non-product costs (transport, customs, ...) come from the chain's
CostItems, as ranges with their basis; OBSERVED amounts replace estimates
of the same kind in the current view. The margin is only ever called
"actual" when every cost component is OBSERVED.
"""

import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from app.core.entities import (
    CommercialDocument,
    CostItem,
    DocumentKind,
    Product,
    ProductSupplier,
    ValueBasis,
)
from app.objects.graph import document_chain

K = DocumentKind

STAGE_LABELS = {
    "actual": "Coût réel (facture fournisseur validée)",
    "committed": "Coût engagé (commande fournisseur)",
    "quoted": "Coût devisé (devis fournisseur)",
    "catalog": "Prix catalogue fournisseur",
    "reference": "Coût de référence estimé",
    "unknown": "Coût inconnu",
}
_CURRENT_ORDER = ("actual", "committed", "quoted", "catalog", "reference")
_PLANNED_ORDER = ("quoted", "catalog", "reference")
_COST_DOC_PRIORITY = (K.SUPPLIER_INVOICE, K.PURCHASE_ORDER, K.SUPPLIER_QUOTE, K.CUSTOMER_ORDER, K.CUSTOMER_QUOTE)


@dataclass
class CostSource:
    stage: str
    unit_cost: float | None
    basis: str
    confidence: str
    source_label: str
    document_id: uuid.UUID | None = None
    document_number: str | None = None


@dataclass
class LineMargin:
    line_id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str | None
    quantity: float
    unit_price: float | None
    revenue: float | None
    current: CostSource
    planned: CostSource
    current_cost: float | None
    planned_cost: float | None
    margin: float | None


@dataclass
class CostRange:
    min: float
    max: float
    basis: str


@dataclass
class CostItemMargin:
    kind: str
    current: CostRange | None
    planned: CostRange | None
    labels: list[str] = field(default_factory=list)


@dataclass
class MarginView:
    revenue: float
    cost_min: float
    cost_max: float
    margin_min: float
    margin_max: float
    margin_pct_min: float | None
    margin_pct_max: float | None
    # "actual" (every cost OBSERVED) | "partial" | "estimated" | "incomplete" (a cost is unknown)
    cost_basis: str


@dataclass
class Variance:
    component: str
    planned: float | None
    current: float | None
    delta: float
    explanation: str


@dataclass
class DocumentMargin:
    document_id: uuid.UUID
    number: str
    kind: str
    currency: str
    revenue_basis: str
    lines: list[LineMargin]
    cost_items: list[CostItemMargin]
    current: MarginView
    planned: MarginView
    variances: list[Variance]
    missing: list[str]
    allocation_note: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _terms_source(session: Session, product: Product) -> CostSource | None:
    terms = (
        session.query(ProductSupplier)
        .filter_by(product_id=product.id)
        .filter(ProductSupplier.unit_price.isnot(None))
        .order_by(ProductSupplier.is_preferred.desc())
        .first()
    )
    if terms is None:
        return None
    confidence = "medium" if terms.last_confirmed_at is not None else "low"
    return CostSource("catalog", terms.unit_price, terms.price_basis.value, confidence, STAGE_LABELS["catalog"])


def _collect_line_sources(session: Session, chain: list[CommercialDocument], product: Product) -> dict[str, CostSource]:
    sources: dict[str, CostSource] = {}

    def doc_source(stage: str, docs: list[CommercialDocument], basis_override: str | None = None, confidence: str = "high") -> None:
        for doc in docs:
            for line in doc.lines:
                if line.product_id == product.id and line.unit_price is not None:
                    basis = basis_override or line.price_basis.value
                    sources[stage] = CostSource(stage, line.unit_price, basis, confidence, STAGE_LABELS[stage], doc.id, doc.number)
                    return

    invoices = [d for d in chain if d.kind == K.SUPPLIER_INVOICE and d.status in {"approved", "partially_paid", "paid"}]
    doc_source("actual", invoices)
    # An invoice not yet approved is at best a declared figure, never "actual".
    if "actual" in sources and sources["actual"].basis != ValueBasis.OBSERVED.value:
        sources.pop("actual")
    doc_source("committed", [d for d in chain if d.kind == K.PURCHASE_ORDER and d.status != "cancelled"])
    quotes = [d for d in chain if d.kind == K.SUPPLIER_QUOTE and d.status != "declined"]
    quotes.sort(key=lambda d: (d.status != "selected", d.created_at))
    doc_source("quoted", quotes, confidence="medium")
    catalog = _terms_source(session, product)
    if catalog is not None:
        sources["catalog"] = catalog
    if product.unit_cost is not None:
        sources["reference"] = CostSource("reference", product.unit_cost, ValueBasis.ESTIMATED.value, "low", STAGE_LABELS["reference"])
    return sources


def _pick(sources: dict[str, CostSource], order: tuple[str, ...]) -> CostSource:
    for stage in order:
        if stage in sources:
            return sources[stage]
    return CostSource("unknown", None, ValueBasis.UNKNOWN.value, "none", STAGE_LABELS["unknown"])


def estimate_planned_unit_cost(session: Session, doc: CommercialDocument, product: Product) -> CostSource:
    """The cost a sales line can expect right now, before any commitment --
    frozen onto the line at creation (CommercialDocumentLine.planned_unit_cost)."""

    chain = document_chain(session, doc.id) if doc.id is not None else []
    return _pick(_collect_line_sources(session, chain, product), _PLANNED_ORDER)


def _snapshot_source(line) -> CostSource | None:
    if line.planned_unit_cost is None:
        return None
    basis = (line.planned_cost_basis or ValueBasis.ESTIMATED).value
    label = f"Estimation au chiffrage ({line.planned_cost_source or 'source non précisée'})"
    return CostSource("planned", line.planned_unit_cost, basis, "medium", label)


def _cost_items(chain: list[CommercialDocument], share: float) -> list[CostItemMargin]:
    by_kind: dict[str, list[tuple[CommercialDocument, CostItem]]] = {}
    for doc in chain:
        for item in doc.cost_items:
            by_kind.setdefault(item.kind.value, []).append((doc, item))

    result: list[CostItemMargin] = []
    for kind, pairs in by_kind.items():
        observed = [item for _, item in pairs if item.basis == ValueBasis.OBSERVED]
        not_observed = [(doc, item) for doc, item in pairs if item.basis != ValueBasis.OBSERVED]

        planned: CostRange | None = None
        for priority_kind in _COST_DOC_PRIORITY:
            items = [item for doc, item in not_observed if doc.kind == priority_kind]
            if items:
                weakest = min(items, key=lambda i: _BASIS_RANK[i.basis.value]).basis.value
                planned = CostRange(sum(i.amount_min for i in items) * share, sum(i.amount_max for i in items) * share, weakest)
                break
        current = (
            CostRange(sum(i.amount_min for i in observed) * share, sum(i.amount_max for i in observed) * share, ValueBasis.OBSERVED.value)
            if observed
            else planned
        )
        labels = [f"{item.label or kind} ({doc.number})" for doc, item in pairs]
        result.append(CostItemMargin(kind, current, planned, labels))
    return result


# Lower = weaker evidence; a sum is only as strong as its weakest part.
_BASIS_RANK = {"unknown": 0, "simulated": 1, "benchmark": 1, "estimated": 2, "declared": 3, "observed": 4}


def _view(revenue: float, line_costs: list[float | None], line_bases: list[str], items: list[CostRange | None]) -> MarginView:
    known = [c for c in line_costs if c is not None]
    cost_min = sum(known) + sum(r.min for r in items if r)
    cost_max = sum(known) + sum(r.max for r in items if r)
    bases = line_bases + [r.basis for r in items if r]
    if any(c is None for c in line_costs):
        cost_basis = "incomplete"
    elif bases and all(b == ValueBasis.OBSERVED.value for b in bases):
        cost_basis = "actual"
    elif any(b == ValueBasis.OBSERVED.value for b in bases):
        cost_basis = "partial"
    else:
        cost_basis = "estimated"
    margin_min, margin_max = revenue - cost_max, revenue - cost_min
    pct = (lambda m: round(m / revenue, 4)) if revenue else (lambda m: None)
    return MarginView(round(revenue, 2), round(cost_min, 2), round(cost_max, 2), round(margin_min, 2), round(margin_max, 2), pct(margin_min), pct(margin_max), cost_basis)


def _fmt_range(r: CostRange) -> str:
    """A range stays a range in every sentence -- never its midpoint."""

    return f"{r.min:.2f}" if abs(r.max - r.min) < 0.005 else f"{r.min:.2f}–{r.max:.2f}"


def _mid(r: CostRange | None) -> float | None:
    return None if r is None else (r.min + r.max) / 2


def compute_document_margin(session: Session, doc: CommercialDocument) -> DocumentMargin:
    if doc.kind not in {K.CUSTOMER_REQUEST, K.CUSTOMER_QUOTE, K.CUSTOMER_ORDER, K.CUSTOMER_INVOICE}:
        raise ValueError("La marge se calcule sur une demande, un devis, une commande ou une facture client")

    chain = document_chain(session, doc.id)
    missing: list[str] = []

    lines: list[LineMargin] = []
    revenue = 0.0
    for line in doc.lines:
        product = session.get(Product, line.product_id) if line.product_id else None
        line_revenue = line.quantity * line.unit_price if line.unit_price is not None else None
        if line_revenue is None:
            missing.append(f"Prix de vente inconnu : {line.description or 'ligne sans produit'}")
        revenue += line_revenue or 0.0
        sources = _collect_line_sources(session, chain, product) if product else {}
        current = _pick(sources, _CURRENT_ORDER)
        planned = _snapshot_source(line) or _pick(sources, _PLANNED_ORDER)
        if current.unit_cost is None:
            missing.append(f"Coût inconnu : {line.description or (product.name if product else 'ligne')}")
        current_cost = current.unit_cost * line.quantity if current.unit_cost is not None else None
        planned_cost = planned.unit_cost * line.quantity if planned.unit_cost is not None else None
        lines.append(
            LineMargin(
                line.id, line.product_id, product.name if product else line.description, line.quantity, line.unit_price,
                round(line_revenue, 2) if line_revenue is not None else None, current, planned,
                round(current_cost, 2) if current_cost is not None else None,
                round(planned_cost, 2) if planned_cost is not None else None,
                round(line_revenue - current_cost, 2) if (line_revenue is not None and current_cost is not None) else None,
            )
        )  # fmt: skip

    # Chain-level costs belong to the whole deal; with several customer
    # orders in one deal they are split by revenue share.
    orders = [d for d in chain if d.kind == K.CUSTOMER_ORDER and d.status != "cancelled"]
    share, allocation_note = 1.0, None
    if doc.kind == K.CUSTOMER_ORDER and len(orders) > 1:
        totals = {o.id: sum(ln.quantity * (ln.unit_price or 0) for ln in o.lines) for o in orders}
        grand = sum(totals.values())
        share = totals.get(doc.id, 0) / grand if grand else 1 / len(orders)
        allocation_note = f"Coûts annexes de l'affaire répartis au prorata du chiffre d'affaires ({share:.0%} sur cette commande)."
    cost_items = _cost_items(chain, share)

    current_view = _view(revenue, [ln.current_cost for ln in lines], [ln.current.basis for ln in lines], [c.current for c in cost_items])
    planned_view = _view(revenue, [ln.planned_cost for ln in lines], [ln.planned.basis for ln in lines], [c.planned for c in cost_items])

    variances: list[Variance] = []
    for ln in lines:
        if ln.current_cost is not None and ln.planned_cost is not None and abs(ln.current_cost - ln.planned_cost) > 0.005:
            delta = ln.current_cost - ln.planned_cost
            variances.append(
                Variance(
                    f"Coût produit · {ln.product_name}", ln.planned_cost, ln.current_cost, round(delta, 2),
                    f"{ln.planned.source_label} {ln.planned.unit_cost:.2f} → {ln.current.source_label.lower()} "
                    f"{ln.current.unit_cost:.2f} par unité ({ln.current.document_number or 'catalogue'}).",
                )
            )  # fmt: skip
    for item in cost_items:
        planned_mid, current_mid = _mid(item.planned), _mid(item.current)
        if current_mid is not None and (planned_mid is None or abs(current_mid - planned_mid) > 0.005):
            delta = current_mid - (planned_mid or 0.0)
            explanation = (
                f"{item.kind} : prévu {_fmt_range(item.planned)} ({item.planned.basis}), constaté {_fmt_range(item.current)} ({item.current.basis})."
                if item.planned is not None
                else f"{item.kind} : coût non prévu, {_fmt_range(item.current)} ({item.current.basis})."
            )
            variances.append(Variance(f"Coût annexe · {item.kind}", planned_mid, current_mid, round(delta, 2), explanation))
    variances.sort(key=lambda v: -abs(v.delta))

    revenue_basis = "observed" if any(d.kind == K.CUSTOMER_INVOICE and d.status in {"issued", "partially_paid", "paid"} for d in chain) else "declared"
    return DocumentMargin(
        doc.id, doc.number, doc.kind.value, doc.currency, revenue_basis, lines, cost_items,
        current_view, planned_view, variances, missing, allocation_note,
    )  # fmt: skip
