"""V2 margin engine (planned vs current, never an estimate shown as actual)
and supplier benchmark (ranges, bases, MOQ/SPQ, observed delay)."""

import pytest

from app.core.entities import CostKind, DocumentKind, Product, StockKind, ValueBasis
from app.domains.procurement.benchmark import benchmark_suppliers
from app.event_bus import build_event_bus
from app.catalog.service import upsert_stock_position
from app.transactions import service
from app.transactions.margin import compute_document_margin
from app.transactions.service import DocumentInput, LineInput
from tests.v2_support import build_world

K = DocumentKind


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def _deal(db_session, bus, world, qty=20):
    """Request -> quote (sent) -> order (confirmed) -> purchase request ->
    PO at supplier A with an ESTIMATED transport cost range."""

    request = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_REQUEST, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=qty)]))
    quote = service.derive_document(db_session, bus, request, K.CUSTOMER_QUOTE)
    service.change_status(db_session, bus, quote, "sent")
    order = service.derive_document(db_session, bus, quote, K.CUSTOMER_ORDER)
    service.change_status(db_session, bus, order, "confirmed")
    pr = service.derive_document(db_session, bus, order, K.PURCHASE_REQUEST)
    po = service.derive_document(db_session, bus, pr, K.PURCHASE_ORDER, supplier_id=world.supplier_a.id)
    service.add_cost_item(db_session, po, kind=CostKind.TRANSPORT, amount_min=300, amount_max=450, basis=ValueBasis.ESTIMATED, label="Autocar")
    return order, po


def test_quote_margin_is_estimated_from_frozen_catalog_cost(db_session, bus, world):
    quote = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_QUOTE, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    margin = compute_document_margin(db_session, quote)
    assert margin.current.revenue == 9000.0
    assert margin.current.cost_min == 6000.0
    assert margin.current.cost_basis == "estimated"  # declared catalog price: not an actual cost
    assert margin.lines[0].planned.unit_cost == 600.0


def test_committed_cost_and_transport_range_are_kept_as_ranges(db_session, bus, world):
    order, _po = _deal(db_session, bus, world)
    margin = compute_document_margin(db_session, order)

    assert margin.lines[0].current.stage == "committed"
    assert margin.current.cost_min == 12000.0 + 300 and margin.current.cost_max == 12000.0 + 450
    assert margin.current.margin_min == 18000.0 - 12450 and margin.current.margin_max == 18000.0 - 12300
    assert margin.current.cost_basis == "estimated"
    transport = next(c for c in margin.cost_items if c.kind == "transport")
    assert transport.current.basis == "estimated"


def test_actual_margin_only_when_every_cost_is_observed_and_variance_explains_the_gap(db_session, bus, world):
    order, po = _deal(db_session, bus, world)
    invoice = service.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    service.update_line(db_session, invoice, invoice.lines[0].id, {"unit_price": 660.0})
    service.change_status(db_session, bus, invoice, "approved")

    partial = compute_document_margin(db_session, order)
    assert partial.lines[0].current.stage == "actual" and partial.lines[0].current.basis == "observed"
    assert partial.current.cost_basis == "partial"  # transport still an estimate

    service.add_cost_item(db_session, invoice, kind=CostKind.TRANSPORT, amount_min=520, amount_max=None, basis=ValueBasis.OBSERVED, reference="Facture autocar 88")
    actual = compute_document_margin(db_session, order)
    assert actual.current.cost_basis == "actual"
    assert actual.current.cost_min == actual.current.cost_max == 20 * 660.0 + 520
    # Planned stays what was expected at pricing time, not the new price.
    assert actual.planned.cost_min == 20 * 600.0 + 300
    components = {v.component for v in actual.variances}
    assert any("Coût produit" in c for c in components) and any("transport" in c for c in components)
    assert actual.variances[0].delta == pytest.approx(20 * 60.0)  # largest gap first


def test_an_observed_cost_must_be_exact(db_session, bus, world):
    _order, po = _deal(db_session, bus, world)
    with pytest.raises(service.DocumentError):
        service.add_cost_item(db_session, po, kind=CostKind.TRANSPORT, amount_min=100, amount_max=200, basis=ValueBasis.OBSERVED)


def test_unknown_cost_makes_the_margin_incomplete_not_optimistic(db_session, bus, world):
    mystery = Product(company_id=world.company.id, name="Excursion privée", sale_price=150.0)
    db_session.add(mystery)
    db_session.commit()
    quote = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_QUOTE, customer_id=world.customer.id, lines=[LineInput(product_id=mystery.id, quantity=4)]))
    margin = compute_document_margin(db_session, quote)
    assert margin.current.cost_basis == "incomplete"
    assert margin.lines[0].current.stage == "unknown"
    assert any("Coût inconnu" in m for m in margin.missing)


def test_benchmark_compares_every_supplier_with_ranges_and_bases(db_session, bus, world):
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=12)]))
    quote_c = service.derive_document(db_session, bus, pr, K.SUPPLIER_QUOTE, supplier_id=world.supplier_c.id)
    service.update_line(
        db_session, quote_c, quote_c.lines[0].id,
        {"unit_price": 590.0, "lead_time_min_days": 12, "lead_time_max_days": 16, "lead_time_basis": ValueBasis.DECLARED},
    )  # fmt: skip
    service.add_cost_item(db_session, quote_c, kind=CostKind.TRANSPORT, amount_min=200, amount_max=350, basis=ValueBasis.ESTIMATED)

    bench = benchmark_suppliers(db_session, world.product.id, 12, purchase_request_id=pr.id)
    by_name = {c.supplier_name: c for c in bench.candidates}
    assert set(by_name) == {"Hotel Riviera", "Alpine Lodges", "Costa Resorts"}

    a = by_name["Hotel Riviera"]
    # MOQ 10 satisfied, SPQ 5 -> 12 is rounded up to 15.
    assert a.order_quantity.value == 15 and "SPQ" in a.order_quantity.text
    assert a.total_cost.min == a.total_cost.max == 15 * 600.0
    # Declared 10-12 days widened by supplier A's OBSERVED recent delay -> an estimate.
    assert a.lead_time_days.basis == "estimated" and a.lead_time_days.min == 10 and a.lead_time_days.max > 12
    assert a.performance.basis == "observed"

    c = by_name["Costa Resorts"]
    assert c.unit_price.source.startswith("Devis") and c.unit_price.basis == "declared"
    assert (c.total_cost.min, c.total_cost.max) == (12 * 590.0 + 200, 12 * 590.0 + 350)
    assert c.lead_time_days.min == 12 and c.lead_time_days.max == 16  # a range, never "14"
    assert c.performance.basis == "unknown" and "performance" in c.unknown_criteria

    b = by_name["Alpine Lodges"]
    assert b.certifications == ["ISO 14001", "Green Key"]
    assert bench.recommended_supplier_id is not None
    assert sum(1 for cand in bench.candidates if cand.recommended) == 1


def test_benchmark_availability_uses_supplier_stock_and_says_unknown_otherwise(db_session, bus, world):
    upsert_stock_position(db_session, None, product=world.product, kind=StockKind.SUPPLIER, supplier_id=world.supplier_b.id, quantity=8, basis=ValueBasis.DECLARED)
    bench = benchmark_suppliers(db_session, world.product.id, 12)
    by_name = {c.supplier_name: c for c in bench.candidates}
    assert by_name["Alpine Lodges"].availability.value == 8 and by_name["Alpine Lodges"].availability.confidence == "low"
    assert by_name["Hotel Riviera"].availability.basis == "unknown"


def test_benchmark_without_any_price_makes_no_recommendation(db_session, bus, world):
    bare = Product(company_id=world.company.id, name="Prestation sans prix")
    db_session.add(bare)
    db_session.commit()
    bench = benchmark_suppliers(db_session, bare.id, 3)
    assert bench.recommended_supplier_id is None
    assert bench.recommendation_confidence == "none"
