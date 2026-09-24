"""V2 transactional model: numbering, the document chain, lifecycle rules,
traceability and ledger posting into V1's Transaction facts."""

from datetime import timedelta

import pytest

from app.core.analytics import compute_supplier_delivery_performance
from app.core.entities import (
    CommercialDocument,
    Customer,
    DocumentKind,
    ObjectLink,
    Product,
    ProductSupplier,
    Transaction,
    TransactionStatus,
    TransactionType,
    ValueBasis,
)
from app.event_bus import build_event_bus
from app.objects.graph import document_ancestry, document_chain
from app.transactions import service
from app.transactions.service import DocumentError, DocumentInput, LineInput, NewCustomer, NewProduct
from tests.v2_support import NOW, build_world

K = DocumentKind


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def _request(db_session, bus, world, qty=20):
    return service.create_document(
        db_session, bus, world.company.id,
        DocumentInput(kind=K.CUSTOMER_REQUEST, customer_id=world.customer.id, title="Séminaire Atlas", lines=[LineInput(product_id=world.product.id, quantity=qty)]),
    )  # fmt: skip


def test_numbers_are_sequential_per_kind_and_unique(db_session, bus, world):
    first = _request(db_session, bus, world)
    second = _request(db_session, bus, world)
    quote = service.derive_document(db_session, bus, first, K.CUSTOMER_QUOTE)

    year = NOW.year
    assert first.number == f"DEM-{year}-0001"
    assert second.number == f"DEM-{year}-0002"
    assert quote.number == f"DEV-{year}-0001"


def test_sales_document_requires_a_customer_and_procurement_ones_a_supplier(db_session, bus, world):
    with pytest.raises(DocumentError):
        service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_QUOTE))
    with pytest.raises(DocumentError):
        service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_ORDER))
    # A purchase request has no supplier yet: that is what it is for.
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST))
    assert pr.status == "draft"


def test_quote_can_create_a_prospect_and_a_product_without_duplicates(db_session, bus, world):
    quote = service.create_document(
        db_session, bus, world.company.id,
        DocumentInput(
            kind=K.CUSTOMER_QUOTE,
            new_customer=NewCustomer(name="Nouvelle Société"),
            lines=[
                LineInput(new_product=NewProduct(name="Transfert aéroport", sku="TRF-01", sale_price=45.0), quantity=20),
                # Same reference as an existing product -> reused, not duplicated.
                LineInput(new_product=NewProduct(name="Un autre nom", sku="SEM-3N"), quantity=20),
            ],
        ),
    )  # fmt: skip
    prospect = db_session.get(Customer, quote.customer_id)
    assert prospect.status == "prospect"
    assert db_session.query(Product).filter_by(sku="SEM-3N").count() == 1
    assert quote.lines[1].product_id == world.product.id
    assert quote.lines[0].unit_price == 45.0 and quote.lines[0].price_basis == ValueBasis.DECLARED

    # Creating the same customer name again reuses it.
    again = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_REQUEST, new_customer=NewCustomer(name="nouvelle société")))
    assert again.customer_id == prospect.id


def test_derivation_builds_a_traceable_chain_and_advances_statuses(db_session, bus, world):
    request = _request(db_session, bus, world)
    quote = service.derive_document(db_session, bus, request, K.CUSTOMER_QUOTE)
    assert db_session.get(CommercialDocument, request.id).status == "quoting"
    assert quote.lines[0].unit_price == 900.0  # the product's list price, declared
    assert quote.lines[0].planned_unit_cost == 600.0  # catalog terms frozen at pricing time

    service.change_status(db_session, bus, quote, "sent")
    order = service.derive_document(db_session, bus, quote, K.CUSTOMER_ORDER)
    assert db_session.get(CommercialDocument, quote.id).status == "accepted"
    assert db_session.get(CommercialDocument, request.id).status == "won"
    assert order.lines[0].unit_price == quote.lines[0].unit_price
    assert order.lines[0].planned_unit_cost == quote.lines[0].planned_unit_cost

    assert [d.id for d in document_ancestry(db_session, order.id)] == [request.id, quote.id, order.id]
    assert {d.id for d in document_chain(db_session, order.id)} == {request.id, quote.id, order.id}
    link = db_session.query(ObjectLink).filter_by(source_id=order.id, target_id=quote.id, relation="derived_from").one()
    assert link.origin == "system"


def test_invalid_transition_and_invalid_derivation_are_refused(db_session, bus, world):
    request = _request(db_session, bus, world)
    with pytest.raises(DocumentError):
        service.change_status(db_session, bus, request, "won")  # new -> won is not a transition
    with pytest.raises(DocumentError):
        service.derive_document(db_session, bus, request, K.RECEPTION)


def test_confirmed_order_posts_sales_facts_traced_to_its_lines(db_session, bus, world):
    request = _request(db_session, bus, world, qty=20)
    order = service.derive_document(db_session, bus, service.derive_document(db_session, bus, request, K.CUSTOMER_QUOTE), K.CUSTOMER_ORDER)
    assert db_session.query(Transaction).filter_by(source_document_id=order.id).count() == 0

    service.change_status(db_session, bus, order, "confirmed")
    facts = db_session.query(Transaction).filter_by(source_document_id=order.id).all()
    assert len(facts) == 1
    assert facts[0].type == TransactionType.SALES_ORDER
    assert facts[0].amount == 18000.0 and facts[0].quantity == 20
    assert facts[0].source_line_id == order.lines[0].id

    # Idempotent: a second posting pass never duplicates.
    from app.transactions.posting import post_customer_order

    assert post_customer_order(db_session, order) == 0


def test_reception_feeds_v1_delivery_performance_and_invoice_never_double_counts(db_session, bus, world):
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    po = service.derive_document(db_session, bus, pr, K.PURCHASE_ORDER, supplier_id=world.supplier_b.id)
    assert po.lines[0].unit_price == 640.0  # supplier B's catalog terms
    assert db_session.get(CommercialDocument, pr.id).status == "ordered"
    service.update_document(db_session, po, {"due_at": NOW - timedelta(days=6)})
    service.change_status(db_session, bus, po, "sent")
    service.change_status(db_session, bus, po, "confirmed")

    before = compute_supplier_delivery_performance(db_session, world.supplier_b.id).sample_size
    reception = service.derive_document(db_session, bus, po, K.RECEPTION)
    service.change_status(db_session, bus, reception, "received", occurred_at=NOW)
    fact = db_session.query(Transaction).filter_by(source_document_id=reception.id).one()
    assert fact.type == TransactionType.PURCHASE_ORDER and fact.amount == 6400.0
    assert (fact.occurred_at - fact.expected_at).days == 6  # the real delay, visible to V1 analytics
    assert compute_supplier_delivery_performance(db_session, world.supplier_b.id).sample_size == before + 1

    invoice = service.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    assert invoice.lines[0].price_basis == ValueBasis.DECLARED  # copied from the PO: not yet a fact
    service.update_line(db_session, invoice, invoice.lines[0].id, {"unit_price": 655.0})
    service.change_status(db_session, bus, invoice, "approved")
    assert db_session.get(CommercialDocument, invoice.id).lines[0].price_basis == ValueBasis.OBSERVED

    db_session.refresh(fact)
    assert fact.amount == 6550.0  # re-valued at the invoiced price...
    invoice_facts = db_session.query(Transaction).filter(Transaction.type == TransactionType.INVOICE, Transaction.source_document_id == invoice.id).count()
    assert invoice_facts == 0  # ...and never posted a second time as an INVOICE fact
    terms = db_session.query(ProductSupplier).filter_by(product_id=world.product.id, supplier_id=world.supplier_b.id).one()
    assert terms.unit_price == 655.0 and terms.price_basis == ValueBasis.OBSERVED


def test_invoice_above_reference_cost_goes_through_v1_risk_path(db_session, bus, world):
    from app.core.entities import Risk

    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    po = service.derive_document(db_session, bus, pr, K.PURCHASE_ORDER, supplier_id=world.supplier_a.id)
    invoice = service.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    service.update_line(db_session, invoice, invoice.lines[0].id, {"unit_price": 720.0})  # +20% vs reference 600
    service.change_status(db_session, bus, invoice, "approved")

    assert db_session.get(Product, world.product.id).unit_cost == 720.0
    assert db_session.query(Risk).count() >= 1  # V1's SupplierCostIncreased -> Risk reaction


def test_cancelled_order_cancels_its_postings(db_session, bus, world):
    order = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_ORDER, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=5)]))
    service.change_status(db_session, bus, order, "confirmed")
    service.change_status(db_session, bus, order, "cancelled")
    assert {t.status for t in db_session.query(Transaction).filter_by(source_document_id=order.id)} == {TransactionStatus.CANCELLED}


def test_locked_documents_cannot_be_edited(db_session, bus, world):
    order = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_ORDER, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=5)]))
    service.change_status(db_session, bus, order, "confirmed")
    with pytest.raises(DocumentError):
        service.update_line(db_session, order, order.lines[0].id, {"quantity": 99})


def test_new_supplier_on_a_supplier_quote_creates_the_product_supplier_relation(db_session, bus, world):
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    assert db_session.query(ProductSupplier).filter_by(product_id=world.product.id, supplier_id=world.supplier_c.id).count() == 0
    service.derive_document(db_session, bus, pr, K.SUPPLIER_QUOTE, supplier_id=world.supplier_c.id)
    assert db_session.query(ProductSupplier).filter_by(product_id=world.product.id, supplier_id=world.supplier_c.id).count() == 1
    assert db_session.get(CommercialDocument, pr.id).status == "consulting"
