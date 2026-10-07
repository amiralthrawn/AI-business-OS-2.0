from app.actions.handlers import make_risk_created_handler
from app.actions.service import TASK_CREATED, ActionsService
from app.core.entities import (
    Company,
    EventLogEntry,
    Product,
    RelatedEntityType,
    Risk,
    RiskSeverity,
    RiskStatus,
    Supplier,
    Task,
    TaskStatus,
)
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


def _make_risk(db_session, supplier, product, source_event_id=None):
    import uuid

    risk = Risk(
        company_id=supplier.company_id,
        title="Supplier cost increase of 20% on product Widget",
        description="Unit cost rose from 100.0 to 120.0 (20.0%), detected from event fixture.",
        severity=RiskSeverity.MEDIUM,
        status=RiskStatus.OPEN,
        related_entity_type=RelatedEntityType.SUPPLIER,
        related_entity_id=supplier.id,
        source_event_id=source_event_id or uuid.uuid4(),
    )
    db_session.add(risk)
    db_session.commit()
    return risk


def _risk_created_event(risk, supplier, product) -> BusinessEvent:
    return BusinessEvent(
        event_type=RISK_CREATED,
        source="intelligence",
        payload={
            "risk_id": str(risk.id),
            "source_event_id": str(risk.source_event_id),
            "supplier_id": str(supplier.id),
            "product_id": str(product.id),
            "severity": risk.severity.value,
        },
    )


def test_risk_created_creates_a_pending_validation_task(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session)
    risk = _make_risk(db_session, supplier, product)
    event = _risk_created_event(risk, supplier, product)

    task = ActionsService(db_session, event_bus).create_task_from_risk_created(event)

    assert task is not None
    assert task.status == TaskStatus.PENDING_VALIDATION
    assert task.title == f"À examiner : {risk.title}"
    assert "20%" in task.title


def test_task_is_traceable_to_risk_and_carries_the_same_related_entity(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session)
    risk = _make_risk(db_session, supplier, product)
    event = _risk_created_event(risk, supplier, product)

    task = ActionsService(db_session, event_bus).create_task_from_risk_created(event)

    assert task.source_event_id == event.event_id
    assert task.related_entity_type == risk.related_entity_type == RelatedEntityType.SUPPLIER
    assert task.related_entity_id == risk.related_entity_id == supplier.id
    assert task.company_id == risk.company_id


def test_task_created_is_published_with_correlation_id(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session)
    risk = _make_risk(db_session, supplier, product)
    event = _risk_created_event(risk, supplier, product)

    received = []
    event_bus.subscribe(TASK_CREATED, received.append)

    task = ActionsService(db_session, event_bus).create_task_from_risk_created(event)

    assert len(received) == 1
    task_created = received[0]
    assert task_created.correlation_id == event.correlation_id
    assert task_created.payload["task_id"] == str(task.id)
    assert task_created.payload["risk_id"] == str(risk.id)
    assert task_created.payload["supplier_id"] == str(supplier.id)
    assert task_created.payload["product_id"] == str(product.id)
    assert task_created.payload["status"] == TaskStatus.PENDING_VALIDATION.value


def test_task_created_is_persisted_in_event_log(db_session, session_factory, event_bus):
    supplier, product = _make_supplier_and_product(db_session)
    risk = _make_risk(db_session, supplier, product)
    event_bus.subscribe("*", make_event_log_handler(session_factory))
    event = _risk_created_event(risk, supplier, product)

    ActionsService(db_session, event_bus).create_task_from_risk_created(event)

    entry = db_session.query(EventLogEntry).filter_by(event_type=TASK_CREATED).one()
    assert entry.source == "actions"
    assert entry.correlation_id == event.correlation_id


def test_same_risk_created_event_does_not_create_a_duplicate_task(db_session, event_bus):
    supplier, product = _make_supplier_and_product(db_session)
    risk = _make_risk(db_session, supplier, product)
    event = _risk_created_event(risk, supplier, product)
    service = ActionsService(db_session, event_bus)

    first = service.create_task_from_risk_created(event)
    second = service.create_task_from_risk_created(event)

    assert first is not None
    assert second is None
    assert db_session.query(Task).count() == 1


def test_full_pipeline_from_supplier_cost_increase_to_task_created(db_session, session_factory):
    """Procurement -> SupplierCostIncreased -> Intelligence -> Risk -> RiskCreated
    -> Actions -> Task -> TaskCreated, all through the Event Bus, all logged."""

    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)

    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    bus.subscribe(SUPPLIER_COST_INCREASED, make_supplier_cost_increased_handler(session_factory, bus))
    bus.subscribe(RISK_CREATED, make_risk_created_handler(session_factory, bus))

    cost_event = ProcurementService(db_session, bus).record_supplier_cost_increase(
        supplier.id, product.id, new_unit_cost=140.0
    )

    risk = db_session.query(Risk).filter_by(source_event_id=cost_event.event_id).one()
    task = db_session.query(Task).filter_by(related_entity_id=supplier.id).one()

    assert task.status == TaskStatus.PENDING_VALIDATION

    logged_types = {e.event_type for e in db_session.query(EventLogEntry).all()}
    assert {SUPPLIER_COST_INCREASED, RISK_CREATED, TASK_CREATED} <= logged_types

    task_created_entry = db_session.query(EventLogEntry).filter_by(event_type=TASK_CREATED).one()
    risk_created_entry = db_session.query(EventLogEntry).filter_by(event_type=RISK_CREATED).one()
    cost_increased_entry = db_session.query(EventLogEntry).filter_by(event_type=SUPPLIER_COST_INCREASED).one()

    # Every event in the chain shares the same correlation_id, end to end.
    assert task_created_entry.correlation_id == risk_created_entry.correlation_id == cost_increased_entry.correlation_id
    assert task_created_entry.payload["risk_id"] == str(risk.id)


def test_full_pipeline_below_threshold_creates_no_task(db_session, session_factory):
    supplier, product = _make_supplier_and_product(db_session, unit_cost=100.0)

    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    bus.subscribe(SUPPLIER_COST_INCREASED, make_supplier_cost_increased_handler(session_factory, bus))
    bus.subscribe(RISK_CREATED, make_risk_created_handler(session_factory, bus))

    ProcurementService(db_session, bus).record_supplier_cost_increase(supplier.id, product.id, new_unit_cost=104.0)

    assert db_session.query(Risk).count() == 0
    assert db_session.query(Task).count() == 0
