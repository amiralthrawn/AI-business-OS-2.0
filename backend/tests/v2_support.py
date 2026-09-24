"""Shared V2 test world: a small, explicit business -- one customer, three
suppliers able to provide the same product on different terms, real
delivery history for one of them -- plus an isolated API client."""

import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.entities import (
    Company,
    Contact,
    Customer,
    Product,
    ProductSupplier,
    RelatedEntityType,
    Supplier,
    Transaction,
    TransactionStatus,
    TransactionType,
    ValueBasis,
)
from app.database import get_db
from app.dependencies import get_event_bus
from app.event_bus import build_event_bus
from app.main import app

NOW = datetime.now(timezone.utc)


@dataclass
class World:
    company: Company
    customer: Customer
    customer_contact: Contact
    supplier_a: Supplier
    supplier_b: Supplier
    supplier_c: Supplier
    supplier_a_contact: Contact
    product: Product


def build_world(session) -> World:
    company = Company(name="Voyages Horizon", industry="Travel Agency")
    session.add(company)
    session.flush()

    customer = Customer(company_id=company.id, name="Groupe Atlas", country="FR", status="active")
    supplier_a = Supplier(company_id=company.id, name="Hotel Riviera", country="IT", payment_terms="30 jours")
    supplier_b = Supplier(company_id=company.id, name="Alpine Lodges", country="CH", certifications=["Green Key"])
    supplier_c = Supplier(company_id=company.id, name="Costa Resorts", country="ES")
    session.add_all([customer, supplier_a, supplier_b, supplier_c])
    session.flush()

    product = Product(
        company_id=company.id, name="Séjour séminaire 3 nuits", sku="SEM-3N", unit="participant",
        sale_price=900.0, unit_cost=600.0, supplier_id=supplier_a.id,
    )  # fmt: skip
    session.add(product)
    session.flush()

    session.add_all(
        [
            ProductSupplier(
                company_id=company.id, product_id=product.id, supplier_id=supplier_a.id, unit_price=600.0,
                price_basis=ValueBasis.DECLARED, lead_time_min_days=10, lead_time_max_days=12,
                lead_time_basis=ValueBasis.DECLARED, moq=10, spq=5, is_preferred=True, certifications=[],
            ),
            ProductSupplier(
                company_id=company.id, product_id=product.id, supplier_id=supplier_b.id, unit_price=640.0,
                price_basis=ValueBasis.DECLARED, lead_time_min_days=5, lead_time_max_days=7,
                lead_time_basis=ValueBasis.DECLARED, certifications=["ISO 14001"],
            ),
        ]
    )  # fmt: skip

    customer_contact = Contact(
        company_id=company.id, name="Claire Martin", email="claire@atlas.example",
        related_entity_type=RelatedEntityType.CUSTOMER, related_entity_id=customer.id,
    )  # fmt: skip
    supplier_a_contact = Contact(
        company_id=company.id, name="Marco Rossi", email="marco@riviera.example",
        related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=supplier_a.id,
    )  # fmt: skip
    session.add_all([customer_contact, supplier_a_contact])

    # Supplier A's real delivery history: 8 receptions, the recent ones ~4 days late.
    for i, delay in enumerate([0, 0, 1, 0, 4, 5, 3, 4]):
        received = NOW - timedelta(days=200 - i * 20)
        session.add(
            Transaction(
                company_id=company.id, supplier_id=supplier_a.id, product_id=product.id,
                type=TransactionType.PURCHASE_ORDER, status=TransactionStatus.CONFIRMED, amount=6000.0,
                occurred_at=received, expected_at=received - timedelta(days=delay),
            )
        )  # fmt: skip
    session.commit()
    return World(company, customer, customer_contact, supplier_a, supplier_b, supplier_c, supplier_a_contact, product)


@contextlib.contextmanager
def api_client(session_factory):
    """TestClient bound to the test database AND to an event bus wired like
    production (Event Log handler on the same test database), so timelines
    and V1 reactions work exactly as in the app."""

    bus = build_event_bus(session_factory)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_bus] = lambda: bus
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
