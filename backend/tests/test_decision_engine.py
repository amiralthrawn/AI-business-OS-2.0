"""Decision Intelligence Engine (app.decision.engine): proof that an
Interpretation is turned into a Decision -- concrete options with their
trade-offs and a reasoned, advisory recommendation -- and that only a
confident recommendation ever reaches the existing Human-in-the-Loop
mechanism as a Task proposal, never executed automatically."""

from datetime import datetime, timedelta, timezone

from app.ai.llm import DETERMINISTIC_MARKER
from app.ai.capabilities import build_capability_registry
from app.ai.llm import DeterministicLLMClient
from app.business_context.service import BusinessContextService
from app.core.entities import (
    Company,
    Customer,
    EventLogEntry,
    Product,
    Risk,
    RiskStatus,
    Supplier,
    Task,
    TaskStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.core.events.bus import InProcessEventBus
from app.core.events.log_handler import make_event_log_handler
from app.decision.engine import DECISION_PROPOSED, build_decision, run_decision_sweep
from app.interpretation.engine import EVENT_INTERPRETED, run_interpretation_sweep
from app.observation import build_observable_registry
from app.observation.engine import run_observation_sweep


def _bus(session_factory):
    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    return bus


def _interpretation_entry(db_session):
    return db_session.query(EventLogEntry).filter_by(event_type=EVENT_INTERPRETED).one()


def _seed_margin_risk_scenario(db_session):
    company = Company(name="Acme")
    db_session.add(company)
    db_session.flush()
    BusinessContextService(db_session).update(company.id, declared_baselines={"margin_pct": 0.30})

    supplier = Supplier(company_id=company.id, name="Northline")
    db_session.add(supplier)
    db_session.flush()
    customer = Customer(company_id=company.id, name="Buyer Co")
    db_session.add(customer)
    db_session.flush()
    product = Product(company_id=company.id, supplier_id=supplier.id, name="Frame", sku="F-1")
    db_session.add(product)
    db_session.flush()

    now = datetime.now(timezone.utc)
    for i, cost in enumerate([400.0, 400.0, 900.0, 900.0]):
        db_session.add(
            Transaction(
                company_id=company.id, supplier_id=supplier.id, product_id=product.id,
                type=TransactionType.PURCHASE_ORDER, status=TransactionStatus.CONFIRMED,
                amount=cost, currency="EUR", occurred_at=now - timedelta(days=(4 - i) * 30),
            )
        )
    for i in range(4):
        db_session.add(
            Transaction(
                company_id=company.id, customer_id=customer.id, product_id=product.id,
                type=TransactionType.SALES_ORDER, status=TransactionStatus.CONFIRMED,
                amount=1000.0, currency="EUR", occurred_at=now - timedelta(days=(4 - i) * 30),
            )
        )
    db_session.commit()
    return company, supplier, product, customer


def _seed_customer_growth_opportunity_scenario(db_session):
    company = Company(name="Acme")
    db_session.add(company)
    db_session.flush()
    BusinessContextService(db_session).update(company.id, declared_baselines={"customer_revenue_variation_pct": 0.05})

    customer = Customer(company_id=company.id, name="Metroline")
    db_session.add(customer)
    db_session.flush()

    now = datetime.now(timezone.utc)
    for i, amount in enumerate([500.0, 500.0, 1500.0, 1500.0]):
        db_session.add(
            Transaction(
                company_id=company.id, customer_id=customer.id,
                type=TransactionType.SALES_ORDER, status=TransactionStatus.CONFIRMED,
                amount=amount, currency="EUR", occurred_at=now - timedelta(days=(4 - i) * 30),
            )
        )
    db_session.commit()
    return company, customer


def _seed_new_supplier_delivery_insight_scenario(db_session):
    company = Company(name="Acme")
    db_session.add(company)
    db_session.flush()
    BusinessContextService(db_session).get_or_create(company.id)

    supplier = Supplier(company_id=company.id, name="Coastal Metal Supply")
    db_session.add(supplier)
    db_session.flush()

    now = datetime.now(timezone.utc)
    for i, delay_days in enumerate([6.0, 6.5, 7.0]):
        occurred_at = now - timedelta(days=(3 - i) * 20)
        db_session.add(
            Transaction(
                company_id=company.id, supplier_id=supplier.id,
                type=TransactionType.PURCHASE_ORDER, status=TransactionStatus.CONFIRMED,
                amount=100.0, currency="EUR", occurred_at=occurred_at,
                expected_at=occurred_at - timedelta(days=delay_days),
            )
        )
    db_session.commit()
    return company, supplier


def _interpret(db_session, bus, company_id):
    run_interpretation_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company_id)


# --- Construction of a Decision: options, trade-offs, recommendation, confidence


def test_build_decision_for_a_risk_has_several_options_with_trade_offs(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)
    entry = _interpretation_entry(db_session)

    decision = build_decision(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry)

    assert decision.type == "risk"
    assert decision.problem  # the Interpretation's own title, not re-derived
    assert len(decision.options) >= 2
    for option in decision.options:
        assert option.label
        assert option.expected_benefit
        assert option.trade_offs

    assert decision.recommendation.chosen_option is not None
    assert decision.recommendation.reasoning  # the LLM's narrative
    assert decision.confidence == "high"  # inherited from the Interpretation, not re-derived
    assert decision.capabilities_consulted  # deeper context was gathered
    assert decision.data_used  # the underlying Observation(s), reused not recomputed

    # Step 27: without a real LLM configured, none of the user-facing text
    # may be a raw JSON/prompt dump or an English option label.
    for text in (decision.problem, decision.recommendation.reasoning, decision.recommendation.chosen_option):
        assert "Context:" not in text
        assert "{" not in text
        assert DETERMINISTIC_MARKER not in text
    assert "Renegotiate" not in decision.recommendation.chosen_option


def test_build_decision_for_an_opportunity_has_options_tailored_to_growth(db_session, session_factory):
    bus = _bus(session_factory)
    company, customer = _seed_customer_growth_opportunity_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)
    entry = _interpretation_entry(db_session)

    decision = build_decision(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry)

    assert decision.type == "opportunity"
    assert len(decision.options) >= 2
    assert decision.recommendation.chosen_option is not None
    assert decision.confidence == "high"


def test_build_decision_for_insufficient_context_has_no_options_or_forced_recommendation(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier = _seed_new_supplier_delivery_insight_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)
    entry = _interpretation_entry(db_session)

    decision = build_decision(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry)

    assert decision.type == "insight"
    assert decision.options == []
    assert decision.recommendation.chosen_option is None
    # The AI still explains itself -- just doesn't force a recommendation.
    assert decision.recommendation.reasoning
    assert decision.confidence == "low"


# --- Sweep: publication, Human-in-the-Loop, no automatic execution -----------


def test_run_decision_sweep_proposes_a_pending_task_only_for_a_risk(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)

    result = run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert result["decisions_made"] == 1
    assert result["by_type"]["risk"] == 1
    assert result["actions_proposed"] == 1

    entries = db_session.query(EventLogEntry).filter_by(event_type=DECISION_PROPOSED).all()
    assert len(entries) == 1
    assert entries[0].payload["type"] == "risk"
    assert len(entries[0].payload["options"]) >= 2

    # Human-in-the-Loop: a Task was proposed, but nothing was auto-executed.
    task = db_session.query(Task).one()
    assert task.status == TaskStatus.PENDING_VALIDATION
    assert task.pending_action == "create_task"


def test_run_decision_sweep_proposes_no_task_for_insufficient_context(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier = _seed_new_supplier_delivery_insight_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)

    result = run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert result["by_type"]["insight"] == 1
    assert result["actions_proposed"] == 0
    assert db_session.query(Task).count() == 0


def test_run_decision_sweep_run_twice_does_not_duplicate(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)

    first = run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)
    second = run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert first["decisions_made"] == 1
    assert second["decisions_made"] == 0
    assert second["actions_proposed"] == 0
    assert db_session.query(Task).count() == 1


def test_no_duplicate_action_when_entity_already_has_an_open_risk(db_session, session_factory):
    """A Decision is still produced (additive, informational), but the
    side-effecting Action Proposal is skipped when the older per-metric flow
    already surfaced this exact entity as an open Risk -- "une Recommendation
    peut exister sans qu'une Action soit proposée"."""

    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)

    from app.intelligence.risks.service import RiskDetectionService

    RiskDetectionService(db_session, bus).evaluate_margin_trend(product.id)
    assert db_session.query(Risk).filter_by(status=RiskStatus.OPEN).count() == 1

    result = run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert result["by_type"]["risk"] == 1  # still decided
    assert result["actions_proposed"] == 0  # but no duplicate Task proposed
    assert db_session.query(Task).count() == 0


def test_proposed_task_can_be_approved_through_the_existing_action_executor(db_session, session_factory):
    """Compatibility with the existing Human-in-the-Loop mechanism: the Task
    a Decision proposes is handled by the SAME ActionExecutor/ActionsService
    as any other AI-proposed Task -- no new approval path, and nothing is
    executed until a human explicitly approves it."""

    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    _interpret(db_session, bus, company.id)
    run_decision_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    task = db_session.query(Task).one()
    assert task.status == TaskStatus.PENDING_VALIDATION  # never auto-executed

    from app.actions.executor import ActionExecutor
    from app.actions.service import ActionsService

    executor = ActionExecutor(ActionsService(db_session, bus))
    approved = executor.approve(task.id)

    assert approved.status == TaskStatus.EXECUTED
