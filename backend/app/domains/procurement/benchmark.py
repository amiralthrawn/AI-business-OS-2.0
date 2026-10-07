"""Supplier benchmark (V2): which supplier for this product, this quantity?

Every criterion is a `Measure` -- a value or a range, its basis
(observed / declared / estimated / benchmark / unknown) and a confidence --
so "12-16 days, estimated, medium confidence" is never flattened into
"14 days". Candidates are every supplier linked to the product
(ProductSupplier) plus every supplier quote attached to the purchase
request; a quote (declared for this very request) outranks catalog terms.

Lead time is the declared one widened by the supplier's OBSERVED average
delay from V1's `compute_supplier_delivery_performance` -- the benchmark
reuses V1's real delivery history instead of trusting promises alone.

The recommendation is a deterministic, published weighting (never an LLM
choice, same rule as V1's classify(), brain/decisions.md #13): unknown
criteria score neutral and are listed, never silently treated as good.
"""

import math
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.analytics import compute_supplier_delivery_performance
from app.core.entities import (
    CommercialDocument,
    DocumentKind,
    Product,
    ProductSupplier,
    Risk,
    RiskStatus,
    StockKind,
    StockPosition,
    Supplier,
    ValueBasis,
)
from app.core.entities.base import RelatedEntityType
from app.objects.graph import document_children

WEIGHTS = {"total_cost": 0.40, "lead_time": 0.25, "performance": 0.20, "availability": 0.15}


@dataclass
class Measure:
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    text: str | None = None
    basis: str = ValueBasis.UNKNOWN.value
    confidence: str = "none"  # "high" | "medium" | "low" | "none"
    source: str | None = None

    @property
    def mid(self) -> float | None:
        if self.min is not None and self.max is not None:
            return (self.min + self.max) / 2
        return self.value


@dataclass
class SupplierCandidate:
    supplier_id: uuid.UUID
    supplier_name: str
    country: str | None
    quote_id: uuid.UUID | None
    quote_number: str | None
    quote_status: str | None
    unit_price: Measure
    order_quantity: Measure
    total_cost: Measure
    lead_time_days: Measure
    performance: Measure
    availability: Measure
    moq: Measure
    spq: Measure
    payment_terms: Measure
    origin_country: Measure
    certifications: list[str]
    open_risks: int
    score: float | None = None
    score_details: dict = field(default_factory=dict)
    unknown_criteria: list[str] = field(default_factory=list)
    recommended: bool = False


@dataclass
class Benchmark:
    product_id: uuid.UUID
    product_name: str
    quantity: float
    purchase_request_id: uuid.UUID | None
    weights: dict
    candidates: list[SupplierCandidate]
    recommended_supplier_id: uuid.UUID | None
    recommendation_confidence: str
    explanation: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        for candidate, raw in zip(self.candidates, data["candidates"]):
            for key in ("unit_price", "order_quantity", "total_cost", "lead_time_days", "performance", "availability", "moq", "spq", "payment_terms", "origin_country"):
                raw[key]["mid"] = getattr(candidate, key).mid
        return data


def _effective_quantity(quantity: float, moq: float | None, spq: float | None) -> tuple[float, str | None]:
    """What must actually be ordered: at least the MOQ, rounded up to the SPQ."""

    qty, notes = quantity, []
    if moq and qty < moq:
        qty, notes = moq, [f"MOQ {moq:g}"]
    if spq and spq > 0 and not math.isclose(qty % spq, 0.0, abs_tol=1e-9):
        qty = math.ceil(qty / spq) * spq
        notes.append(tx(f"multiple de {spq:g} (SPQ)", f"multiple of {spq:g} (SPQ)"))
    return qty, (" · ".join(notes) or None)


def _quotes_for(session: Session, purchase_request_id: uuid.UUID | None, product_id: uuid.UUID) -> dict[uuid.UUID, tuple[CommercialDocument, object]]:
    if purchase_request_id is None:
        return {}
    quotes: dict[uuid.UUID, tuple[CommercialDocument, object]] = {}
    for child_id in document_children(session, purchase_request_id):
        doc = session.get(CommercialDocument, child_id)
        if doc is None or doc.kind != DocumentKind.SUPPLIER_QUOTE or doc.supplier_id is None or doc.status == "declined":
            continue
        line = next((ln for ln in doc.lines if ln.product_id == product_id), None)
        if line is not None:
            quotes[doc.supplier_id] = (doc, line)
    return quotes


def _performance(session: Session, supplier_id: uuid.UUID) -> tuple[Measure, float]:
    perf = compute_supplier_delivery_performance(session, supplier_id)
    if perf.trend == "insufficient_data" or perf.recent_on_time_rate is None:
        return Measure(text=tx("Historique insuffisant", "Insufficient history"), basis=ValueBasis.UNKNOWN.value, confidence="none", source=tx("Aucune réception mesurée", "No measured goods receipt")), 0.0
    # 0-100: on-time rate, minus a penalty for a deteriorating trend.
    score = perf.recent_on_time_rate * 100 - (10 if perf.trend == "deteriorating" else 0)
    confidence = "high" if perf.sample_size >= 8 else "medium" if perf.sample_size >= 4 else "low"
    text = tx(f"{perf.recent_on_time_rate:.0%} à l'heure · retard moyen {perf.recent_avg_delay_days:.1f} j", f"{perf.recent_on_time_rate:.0%} on time · average delay {perf.recent_avg_delay_days:.1f} d")
    return (
        Measure(value=round(max(score, 0), 1), unit="/100", text=text, basis=ValueBasis.OBSERVED.value, confidence=confidence,
                source=tx(f"{perf.sample_size} commandes réceptionnées", f"{perf.sample_size} orders received")),
        perf.recent_avg_delay_days or 0.0,
    )  # fmt: skip


def _availability(session: Session, product_id: uuid.UUID, supplier_id: uuid.UUID, needed: float) -> Measure:
    position = session.query(StockPosition).filter_by(product_id=product_id, supplier_id=supplier_id, kind=StockKind.SUPPLIER).order_by(StockPosition.as_of.desc()).first()
    if position is None:
        return Measure(text=tx("Non communiquée", "Not provided"), basis=ValueBasis.UNKNOWN.value, confidence="none")
    enough = position.quantity >= needed
    return Measure(
        value=position.quantity, unit=tx("unités", "units"),
        text=tx(f"{position.quantity:g} en stock fournisseur" + ("" if enough else f" (besoin {needed:g})"), f"{position.quantity:g} in supplier stock" + ("" if enough else f" (need {needed:g})")),
        basis=position.quantity_basis.value, confidence="medium" if enough else "low",
        source=tx(f"{position.source} au {position.as_of.date().isoformat()}", f"{position.source} as of {position.as_of.date().isoformat()}"),
    )  # fmt: skip


def _candidate(session: Session, product: Product, supplier: Supplier, terms: ProductSupplier | None, quote, quantity: float) -> SupplierCandidate:
    quote_doc, quote_line = quote if quote else (None, None)

    # Price: this request's quote > catalog terms > nothing.
    if quote_line is not None and quote_line.unit_price is not None:
        unit_price = Measure(value=quote_line.unit_price, unit="EUR", basis=quote_line.price_basis.value, confidence="high", source=tx(f"Devis {quote_doc.number}", f"Quote {quote_doc.number}"))
    elif terms is not None and terms.unit_price is not None:
        unit_price = Measure(value=terms.unit_price, unit="EUR", basis=terms.price_basis.value, confidence="medium" if terms.last_confirmed_at else "low", source=tx("Conditions catalogue fournisseur", "Supplier catalogue terms"))
    else:
        unit_price = Measure(unit="EUR", text=tx("Prix non communiqué", "Price not provided"))

    moq_v = (quote_line.moq if quote_line and quote_line.moq is not None else None) or (terms.moq if terms else None)
    spq_v = (quote_line.spq if quote_line and quote_line.spq is not None else None) or (terms.spq if terms else None)
    order_qty, qty_note = _effective_quantity(quantity, moq_v, spq_v)
    order_quantity = Measure(value=order_qty, unit=tx("unités", "units"), text=qty_note, basis=ValueBasis.DECLARED.value if (moq_v or spq_v) else ValueBasis.ESTIMATED.value, confidence="high")

    transport_min = transport_max = 0.0
    transport_note = None
    if quote_doc is not None:
        items = [c for c in quote_doc.cost_items if c.kind.value == "transport"]
        transport_min, transport_max = sum(c.amount_min for c in items), sum(c.amount_max for c in items)
        if items:
            transport_note = f"transport {transport_min:.0f}–{transport_max:.0f} EUR" if transport_max != transport_min else f"transport {transport_min:.0f} EUR"
    if unit_price.value is not None:
        base = unit_price.value * order_qty
        total_cost = Measure(
            min=round(base + transport_min, 2), max=round(base + transport_max, 2), unit="EUR",
            text=" · ".join(filter(None, [qty_note and tx(f"quantité ajustée : {qty_note}", f"adjusted quantity: {qty_note}"), transport_note or tx("transport non chiffré", "transport not priced")])),
            basis=unit_price.basis if transport_min == transport_max else ValueBasis.ESTIMATED.value,
            confidence=unit_price.confidence, source=unit_price.source,
        )  # fmt: skip
    else:
        total_cost = Measure(unit="EUR", text=tx("Non calculable sans prix", "Cannot be computed without a price"))

    performance, observed_delay = _performance(session, supplier.id)

    # Lead time: declared range (quote > terms), widened by observed delay.
    lead_src = quote_line if (quote_line is not None and quote_line.lead_time_min_days is not None) else terms
    if lead_src is not None and lead_src.lead_time_min_days is not None:
        declared_min = lead_src.lead_time_min_days
        declared_max = lead_src.lead_time_max_days if lead_src.lead_time_max_days is not None else declared_min
        if performance.basis == ValueBasis.OBSERVED.value and observed_delay > 0.5:
            lead_time = Measure(
                min=declared_min, max=round(declared_max + observed_delay, 1), unit=tx("jours", "days"), basis=ValueBasis.ESTIMATED.value,
                confidence="medium", text=tx(f"annoncé {declared_min:g}–{declared_max:g} j, + {observed_delay:.1f} j de retard moyen observé", f"stated {declared_min:g}–{declared_max:g} d, + {observed_delay:.1f} d of observed average delay"),
                source=tx("Délai déclaré corrigé par l'historique réel", "Declared lead time corrected by actual history"),
            )  # fmt: skip
        else:
            lead_time = Measure(
                min=declared_min, max=declared_max, unit=tx("jours", "days"), basis=lead_src.lead_time_basis.value,
                confidence="medium" if quote_line is not None else "low", source=tx("Devis", "Quote") if lead_src is quote_line else tx("Conditions catalogue", "Catalogue terms"),
            )  # fmt: skip
    else:
        lead_time = Measure(unit=tx("jours", "days"), text=tx("Délai non communiqué", "Lead time not provided"))

    payment_terms_v = (terms.payment_terms if terms and terms.payment_terms else None) or supplier.payment_terms or (quote_doc.payment_terms if quote_doc else None)
    origin = (terms.country_of_origin if terms and terms.country_of_origin else None) or supplier.country
    certifications = list(dict.fromkeys((terms.certifications if terms else []) + (supplier.certifications or [])))
    open_risks = (
        session.query(Risk)
        .filter(Risk.related_entity_type == RelatedEntityType.SUPPLIER, Risk.related_entity_id == supplier.id, Risk.status == RiskStatus.OPEN)
        .count()
    )

    return SupplierCandidate(
        supplier_id=supplier.id, supplier_name=supplier.name, country=supplier.country,
        quote_id=quote_doc.id if quote_doc else None, quote_number=quote_doc.number if quote_doc else None,
        quote_status=quote_doc.status if quote_doc else None,
        unit_price=unit_price, order_quantity=order_quantity, total_cost=total_cost, lead_time_days=lead_time,
        performance=performance, availability=_availability(session, product.id, supplier.id, order_qty),
        moq=Measure(value=moq_v, unit=tx("unités", "units"), basis=ValueBasis.DECLARED.value if moq_v else ValueBasis.UNKNOWN.value, confidence="medium" if moq_v else "none"),
        spq=Measure(value=spq_v, unit=tx("unités", "units"), basis=ValueBasis.DECLARED.value if spq_v else ValueBasis.UNKNOWN.value, confidence="medium" if spq_v else "none"),
        payment_terms=Measure(text=payment_terms_v, basis=ValueBasis.DECLARED.value if payment_terms_v else ValueBasis.UNKNOWN.value, confidence="medium" if payment_terms_v else "none"),
        origin_country=Measure(text=origin, basis=ValueBasis.DECLARED.value if origin else ValueBasis.UNKNOWN.value, confidence="medium" if origin else "none"),
        certifications=certifications, open_risks=open_risks,
    )  # fmt: skip


def _normalize(values: dict[uuid.UUID, float | None], lower_is_better: bool) -> dict[uuid.UUID, float | None]:
    known = [v for v in values.values() if v is not None]
    if not known:
        return {k: None for k in values}
    lo, hi = min(known), max(known)
    out: dict[uuid.UUID, float | None] = {}
    for key, v in values.items():
        if v is None:
            out[key] = None
        elif hi == lo:
            out[key] = 1.0
        else:
            ratio = (v - lo) / (hi - lo)
            out[key] = 1 - ratio if lower_is_better else ratio
    return out


def benchmark_suppliers(session: Session, product_id: uuid.UUID, quantity: float, purchase_request_id: uuid.UUID | None = None) -> Benchmark:
    product = session.get(Product, product_id)
    if product is None:
        raise LookupError("Product not found")

    terms_by_supplier = {t.supplier_id: t for t in session.query(ProductSupplier).filter_by(product_id=product_id).all()}
    quotes = _quotes_for(session, purchase_request_id, product_id)
    supplier_ids = list(dict.fromkeys(list(terms_by_supplier) + list(quotes) + ([product.supplier_id] if product.supplier_id else [])))

    candidates = [
        _candidate(session, product, supplier, terms_by_supplier.get(supplier.id), quotes.get(supplier.id), quantity)
        for supplier in (session.get(Supplier, sid) for sid in supplier_ids)
        if supplier is not None
    ]

    criteria = {
        "total_cost": (_normalize({c.supplier_id: c.total_cost.mid for c in candidates}, lower_is_better=True)),
        "lead_time": (_normalize({c.supplier_id: c.lead_time_days.mid for c in candidates}, lower_is_better=True)),
        "performance": (_normalize({c.supplier_id: c.performance.value for c in candidates}, lower_is_better=False)),
        "availability": {
            c.supplier_id: (None if c.availability.value is None else (1.0 if c.availability.value >= c.order_quantity.value else 0.3))
            for c in candidates
        },
    }
    labels = {"total_cost": tx("coût total", "total cost"), "lead_time": tx("délai", "lead time"), "performance": "performance", "availability": tx("disponibilité", "availability")}
    for c in candidates:
        total = 0.0
        for name, weight in WEIGHTS.items():
            normalized = criteria[name][c.supplier_id]
            if normalized is None:
                c.unknown_criteria.append(labels[name])
                normalized = 0.5  # unknown = neutral, never "good"
            c.score_details[name] = round(normalized, 3)
            total += weight * normalized
        # An open Risk on the supplier is a known negative, visible in the score.
        total -= 0.05 * min(c.open_risks, 2)
        c.score = round(total * 100, 1)

    explanation: list[str] = []
    recommended = None
    priced = [c for c in candidates if c.total_cost.mid is not None]
    if priced:
        recommended = max(priced, key=lambda c: c.score or 0)
        recommended.recommended = True
        explanation.append(tx(f"{recommended.supplier_name} obtient le meilleur score pondéré ({recommended.score:.0f}/100).", f"{recommended.supplier_name} has the best weighted score ({recommended.score:.0f}/100)."))
        if recommended.unknown_criteria:
            explanation.append(tx(f"Critères inconnus pour {recommended.supplier_name} : {', '.join(recommended.unknown_criteria)} (comptés neutres).", f"Unknown criteria for {recommended.supplier_name}: {', '.join(recommended.unknown_criteria)} (counted as neutral)."))
        if recommended.open_risks:
            explanation.append(tx(f"Attention : {recommended.open_risks} risque(s) ouvert(s) sur ce fournisseur.", f"Warning: {recommended.open_risks} open risk(s) on this supplier."))
    else:
        explanation.append(tx("Aucun fournisseur n'a de prix connu : pas de recommandation possible. Demandez des devis.", "No supplier has a known price: no recommendation possible. Request quotes."))

    if recommended is None:
        confidence = "none"
    else:
        rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        weakest = min((recommended.total_cost.confidence, recommended.lead_time_days.confidence, recommended.performance.confidence), key=lambda x: rank.get(x, 0))
        confidence = {0: "low", 1: "low", 2: "medium", 3: "high"}[rank.get(weakest, 0)]
        if len(priced) < 2:
            confidence = "low"
            explanation.append(tx("Un seul fournisseur chiffré : la comparaison est limitée.", "Only one supplier is priced: the comparison is limited."))

    return Benchmark(
        product_id=product.id, product_name=product.name, quantity=quantity, purchase_request_id=purchase_request_id,
        weights=WEIGHTS, candidates=sorted(candidates, key=lambda c: -(c.score or 0)),
        recommended_supplier_id=recommended.supplier_id if recommended else None,
        recommendation_confidence=confidence, explanation=explanation,
    )  # fmt: skip
