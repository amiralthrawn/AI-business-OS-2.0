import pytest

from app.core.entities import Company, EventLogEntry, Product, RelatedEntityType, Risk, RiskSeverity, Supplier
from app.core.events.bus import InProcessEventBus
from app.core.events.business_event import BusinessEvent
from app.core.events.log_handler import make_event_log_handler
from app.domains.procurement.service import SUPPLIER_COST_INCREASED, ProcurementService
from app.intelligence.risks.handlers import make_supplier_cost_increased_handler
from app.intelligence.risks.service import RISK_CREATED, RiskDetectionService


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


def _cost_increase_event(supplier, product, old_unit_cost, new_unit_cost) -> BusinessEvent:
    return BusinessEvent(
        event_type=SUPPLIER_COST_INCREASED,
        source="procurement",
        payload={
            "supplier_id": str(supplier.id),
            "product_id": str(product.id),
            "old_unit_cost": old_unit_cost,
            "new_unit_cost": new_unit_cost,
            "variation_pct": (new_unit_cost - old_unit_cost) / old_unit_cost,
        },
    )


def test_small_cost_increase_creates_no_risk(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event = _cost_increase_event(supplier, product, 100.0, 105.0)  # 5%, below threshold

    risk = RiskDetectionService(db_session, event_bus).evaluate_supplier_cost_increase(event)

    assert risk is None
    assert db_session.query(Risk).count() == 0


def test_significant_cost_increase_creates_a_risk_linked_to_the_supplier(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event = _cost_increase_event(supplier, product, 100.0, 115.0)  # 15%, above threshold

    risk = RiskDetectionService(db_session, event_bus).evaluate_supplier_cost_increase(event)

    assert risk is not None
    assert risk.related_entity_type == RelatedEntityType.SUPPLIER
    assert risk.related_entity_id == supplier.id
    assert risk.company_id == supplier.company_id
    assert risk.severity == RiskSeverity.MEDIUM
    assert product.name in risk.title


def test_risk_is_traceable_to_its_source_event(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event = _cost_increase_event(supplier, product, 100.0, 130.0)  # 30%, high severity

    risk = RiskDetectionService(db_session, event_bus).evaluate_supplier_cost_increase(event)

    assert risk.source_event_id == event.event_id
    assert risk.severity == RiskSeverity.HIGH
    # French amounts (decision #56); the event itself is traced by source_event_id.
    assert "130,00" in risk.description
    assert "100,00" in risk.description


def test_risk_created_is_published_with_full_traceability(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event = _cost_increase_event(supplier, product, 100.0, 120.0)

    received = []
    event_bus.subscribe(RISK_CREATED, received.append)

    risk = RiskDetectionService(db_session, event_bus).evaluate_supplier_cost_increase(event)

    assert len(received) == 1
    risk_created = received[0]
    assert risk_created.correlation_id == event.correlation_id
    assert risk_created.payload["risk_id"] == str(risk.id)
    assert risk_created.payload["source_event_id"] == str(event.event_id)
    assert risk_created.payload["supplier_id"] == str(supplier.id)
    assert risk_created.payload["product_id"] == str(product.id)
    assert risk_created.payload["severity"] == risk.severity.value


def test_risk_created_is_persisted_in_event_log(db_session, session_factory, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event_bus.subscribe("*", make_event_log_handler(session_factory))
    event = _cost_increase_event(supplier, product, 100.0, 120.0)

    RiskDetectionService(db_session, event_bus).evaluate_supplier_cost_increase(event)

    entry = db_session.query(EventLogEntry).filter_by(event_type=RISK_CREATED).one()
    assert entry.source == "intelligence"
    assert entry.correlation_id == event.correlation_id
    assert entry.payload["source_event_id"] == str(event.event_id)


def test_same_source_event_does_not_create_a_duplicate_risk(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)
    event = _cost_increase_event(supplier, product, 100.0, 120.0)
    service = RiskDetectionService(db_session, event_bus)

    first = service.evaluate_supplier_cost_increase(event)
    second = service.evaluate_supplier_cost_increase(event)

    assert first is not None
    assert second is None
    assert db_session.query(Risk).count() == 1


def test_full_pipeline_from_supplier_cost_increase_to_risk_created(db_session, session_factory):
    """Procurement -> SupplierCostIncreased -> EventBus -> (EventLog, Intelligence)
    -> Risk -> RiskCreated -> EventBus -> EventLog, wired the same way as
    app.event_bus.build_event_bus but against the isolated test database."""

    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)

    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    bus.subscribe(SUPPLIER_COST_INCREASED, make_supplier_cost_increased_handler(session_factory, bus))

    cost_event = ProcurementService(db_session, bus).record_supplier_cost_increase(
        supplier.id, product.id, new_unit_cost=140.0
    )

    risk = db_session.query(Risk).filter_by(source_event_id=cost_event.event_id).one()
    assert risk.related_entity_id == supplier.id

    logged_types = {e.event_type for e in db_session.query(EventLogEntry).all()}
    assert {SUPPLIER_COST_INCREASED, RISK_CREATED} <= logged_types

    risk_created_entry = db_session.query(EventLogEntry).filter_by(event_type=RISK_CREATED).one()
    assert risk_created_entry.correlation_id == cost_event.correlation_id


def test_full_pipeline_below_threshold_creates_no_risk(db_session, session_factory):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)

    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    bus.subscribe(SUPPLIER_COST_INCREASED, make_supplier_cost_increased_handler(session_factory, bus))

    ProcurementService(db_session, bus).record_supplier_cost_increase(supplier.id, product.id, new_unit_cost=104.0)

    assert db_session.query(Risk).count() == 0
    logged_types = {e.event_type for e in db_session.query(EventLogEntry).all()}
    assert SUPPLIER_COST_INCREASED in logged_types
    assert RISK_CREATED not in logged_types
