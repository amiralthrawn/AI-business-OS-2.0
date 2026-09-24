import uuid
from datetime import datetime, timezone

import pytest

from app.ai.capabilities import build_capability_registry
from app.ai.capabilities.analyze_margin import analyze_margin_capability
from app.ai.capabilities.base import CapabilityExecutionError, CapabilityNotFoundError
from app.ai.capabilities.read_product import read_product_capability
from app.ai.capabilities.read_supplier import read_supplier_capability
from app.ai.capabilities.read_transactions import read_transactions_capability
from app.core.entities import (
    Company,
    Product,
    Supplier,
    Transaction,
    TransactionStatus,
    TransactionType,
)


def _make_supplier_and_product(db_session, unit_cost=100.0):
    company = Company(name="Test Co")
    db_session.add(company)
    db_session.flush()

    supplier = Supplier(company_id=company.id, name="Test Supplier")
    db_session.add(supplier)
    db_session.flush()

    product = Product(company_id=company.id, supplier_id=supplier.id, name="Widget", sku="W-1", unit_cost=unit_cost)
    db_session.add(product)
    db_session.commit()

    return supplier, product


def test_registry_register_get_list():
    registry = build_capability_registry()

    assert registry.get("read_supplier") is read_supplier_capability
    names = {c.name for c in registry.list()}
    assert names == {
        "read_supplier",
        "read_product",
        "read_customer",
        "read_transactions",
        "analyze_margin",
        "analyze_supplier_performance",
        "analyze_customer_value",
        "list_priorities",
        "get_business_state_snapshot",
        "create_task",
        # V2 business objects (deals agent)
        "read_object_context",
        "analyze_document_margin",
        "benchmark_suppliers",
    }


def test_registry_raises_on_unknown_capability():
    registry = build_capability_registry()

    with pytest.raises(CapabilityNotFoundError):
        registry.get("send_email")


def test_registry_rejects_duplicate_registration():
    registry = build_capability_registry()

    with pytest.raises(ValueError):
        registry.register(read_supplier_capability)


def test_read_supplier_returns_real_data(db_session):
    supplier, product = _make_supplier_and_product(db_session)

    result = read_supplier_capability.run(db_session, supplier_id=supplier.id)

    assert result.id == supplier.id
    assert result.name == "Test Supplier"
    assert result.product_count == 1


def test_read_supplier_missing_raises_clean_error(db_session):
    with pytest.raises(CapabilityExecutionError):
        read_supplier_capability.run(db_session, supplier_id=uuid.uuid4())


def test_read_product_returns_real_data(db_session):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=42.0)

    result = read_product_capability.run(db_session, product_id=product.id)

    assert result.id == product.id
    assert result.unit_cost == 42.0
    assert result.supplier_id == supplier.id


def test_read_product_missing_raises_clean_error(db_session):
    with pytest.raises(CapabilityExecutionError):
        read_product_capability.run(db_session, product_id=uuid.uuid4())


def test_read_transactions_requires_supplier_or_product(db_session):
    with pytest.raises(Exception):  # pydantic ValidationError
        read_transactions_capability.run(db_session)


def test_read_transactions_filters_by_product(db_session):
    supplier, product = _make_supplier_and_product(db_session)
    db_session.add(
        Transaction(
            company_id=supplier.company_id,
            supplier_id=supplier.id,
            product_id=product.id,
            type=TransactionType.PURCHASE_ORDER,
            status=TransactionStatus.CONFIRMED,
            amount=500.0,
            currency="EUR",
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    result = read_transactions_capability.run(db_session, product_id=product.id)

    assert len(result.transactions) == 1
    assert result.transactions[0].amount == 500.0


def test_analyze_margin_reports_a_limitation_when_no_revenue_data(db_session):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    db_session.add(
        Transaction(
            company_id=supplier.company_id,
            supplier_id=supplier.id,
            product_id=product.id,
            type=TransactionType.PURCHASE_ORDER,
            status=TransactionStatus.CONFIRMED,
            amount=1000.0,
            currency="EUR",
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    result = analyze_margin_capability.run(db_session, product_id=product.id)

    assert result.cost == 1000.0
    assert result.revenue is None
    assert result.margin is None
    assert result.limitation is not None


def test_analyze_margin_computes_margin_when_revenue_data_exists(db_session):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    db_session.add_all(
        [
            Transaction(
                company_id=supplier.company_id,
                supplier_id=supplier.id,
                product_id=product.id,
                type=TransactionType.PURCHASE_ORDER,
                status=TransactionStatus.CONFIRMED,
                amount=1000.0,
                currency="EUR",
                occurred_at=datetime.now(timezone.utc),
            ),
            Transaction(
                company_id=supplier.company_id,
                product_id=product.id,
                type=TransactionType.SALES_ORDER,
                status=TransactionStatus.CONFIRMED,
                amount=1500.0,
                currency="EUR",
                occurred_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()

    result = analyze_margin_capability.run(db_session, product_id=product.id)

    assert result.cost == 1000.0
    assert result.revenue == 1500.0
    assert result.margin == 500.0
    assert result.margin_percentage == pytest.approx(1 / 3)
    assert result.limitation is None
