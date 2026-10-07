"""Business Event Interpretation Engine (app.interpretation.engine): proof
that a factual ObservationDetected Business Event is turned into a Risk,
Opportunity or Insight/Observation depending on the data alone -- never a
per-event-type hardcoded rule -- and that this layer never proposes or
executes a Task itself (that responsibility belongs to app.decision, see
tests/test_decision_engine.py)."""

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
    Supplier,
    Task,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.core.events.bus import InProcessEventBus
from app.core.events.log_handler import make_event_log_handler
from app.interpretation.engine import EVENT_INTERPRETED, classify, interpret_event, run_interpretation_sweep
from app.observation import build_observable_registry
from app.observation.engine import OBSERVATION_DETECTED, run_observation_sweep


def _bus(session_factory):
    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    return bus


def _observation_entry(db_session):
    return db_session.query(EventLogEntry).filter_by(event_type=OBSERVATION_DETECTED).one()


def _seed_margin_risk_scenario(db_session):
    """Steel-Frame-style supplier cost creep -> margin deterioration, with a
    company-declared 30% margin target -> high-confidence, unfavorable
    deviation -> the "un événement fournisseur/coût -> Risk" MVP case."""

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
    """A customer whose revenue roughly tripled, against a company-declared
    "+/-5%" normal variation -> high-confidence, favorable deviation -- the
    "un événement commercial positif -> Opportunity" MVP case."""

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
    """A brand-new supplier with only 3 shipments on record, all badly late --
    a real, high-magnitude signal, but on too thin a history (and no
    company-declared target) to confidently call it a Risk yet. The
    "un événement intéressant mais non clairement Risk/Opportunity -> Insight"
    MVP case."""

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


# --- Classification: the one deterministic, generic rule ---------------------


def test_classify_high_confidence_unfavorable_deviation_is_a_risk():
    payload = {"baseline_confidence": "high", "deviation": -0.15, "observable": "margin_pct"}
    assert classify(payload) == ("risk", "high")


def test_classify_medium_confidence_favorable_deviation_is_an_opportunity():
    payload = {"baseline_confidence": "medium", "deviation": 0.5, "observable": "customer_revenue_variation_pct"}
    assert classify(payload) == ("opportunity", "medium")


def test_classify_low_confidence_deviation_is_an_insight_regardless_of_direction():
    assert classify({"baseline_confidence": "low", "deviation": 4.5, "observable": "delivery_delay_days"}) == (
        "insight", "low",
    )
    assert classify({"baseline_confidence": "low", "deviation": -4.5, "observable": "delivery_delay_days"}) == (
        "insight", "low",
    )


def test_classify_insufficient_context_is_an_observation_not_a_forced_risk_or_opportunity():
    assert classify({"baseline_confidence": "insufficient", "deviation": 9.0, "observable": "margin_pct"}) == (
        "observation", "low",
    )
    # Even with high confidence, an unrecognized observable (no known
    # direction) or a missing deviation must never be forced into a
    # Risk/Opportunity guess.
    assert classify({"baseline_confidence": "high", "deviation": None, "observable": "margin_pct"}) == (
        "observation", "high",
    )
    assert classify({"baseline_confidence": "high", "deviation": 1.0, "observable": "unknown_metric"}) == (
        "observation", "high",
    )


# --- End-to-end interpretation of a real Business Event -----------------------


def test_interpret_event_produces_a_risk_for_a_supplier_cost_driven_margin_event(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    entry = _observation_entry(db_session)

    interpretation = interpret_event(
        db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry
    )

    assert interpretation.type == "risk"
    assert interpretation.confidence == "high"
    assert interpretation.entity_name == "Frame"
    assert interpretation.recommendation is not None
    assert interpretation.explanation  # non-empty: the LLM's narrative
    assert interpretation.capabilities_consulted  # deeper context was gathered
    assert interpretation.observations_used[0]["observable"] == "margin_pct"


def test_interpret_event_never_leaks_technical_noise_without_a_real_llm(db_session, session_factory):
    """Step 27: without a configured LLM (DeterministicLLMClient, the only
    option in this test suite), `title` and `explanation` must still be
    clean French business sentences -- never the raw observable identifier,
    never a JSON/prompt dump ("Context:", "{", "deterministic answer")."""

    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    entry = _observation_entry(db_session)

    interpretation = interpret_event(
        db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry
    )

    for text in (interpretation.title, interpretation.explanation, interpretation.recommendation):
        assert text is not None
        assert "margin_pct" not in text
        assert DETERMINISTIC_MARKER not in text
        assert "Context:" not in text
        assert "{" not in text
    assert "Frame" in interpretation.title
    assert "Frame" in interpretation.explanation


def test_interpret_event_produces_an_opportunity_for_a_growing_customer(db_session, session_factory):
    bus = _bus(session_factory)
    company, customer = _seed_customer_growth_opportunity_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    entry = _observation_entry(db_session)

    interpretation = interpret_event(
        db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry
    )

    assert interpretation.type == "opportunity"
    assert interpretation.confidence == "high"
    assert interpretation.entity_name == "Metroline"
    assert interpretation.recommendation is not None


def test_interpret_event_produces_an_insight_for_a_thin_history_anomaly(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier = _seed_new_supplier_delivery_insight_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)
    entry = _observation_entry(db_session)

    interpretation = interpret_event(
        db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id, entry
    )

    assert interpretation.type == "insight"
    assert interpretation.confidence == "low"
    assert interpretation.entity_name == "Coastal Metal Supply"
    # Not confident enough to be forced into a Risk -- no recommendation.
    assert interpretation.recommendation is None


# --- Sweep: publication and idempotence (no Task proposal at this layer) ----
#
# Since Step 17, turning an Interpretation into a Task proposal is
# app.decision's job (see app.decision.engine.run_decision_sweep and
# tests/test_decision_engine.py) -- app.interpretation never proposes or
# executes anything, only publishes EventInterpreted.


def test_run_interpretation_sweep_interprets_but_proposes_no_task(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)

    result = run_interpretation_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert result["observations_interpreted"] == 1
    assert result["by_type"]["risk"] == 1
    assert "actions_proposed" not in result

    entries = db_session.query(EventLogEntry).filter_by(event_type=EVENT_INTERPRETED).all()
    assert len(entries) == 1
    assert entries[0].payload["type"] == "risk"

    # No side effect at all at this layer -- no Task, proposed or otherwise.
    assert db_session.query(Task).count() == 0


def test_run_interpretation_sweep_run_twice_does_not_duplicate(db_session, session_factory):
    bus = _bus(session_factory)
    company, supplier, product, customer = _seed_margin_risk_scenario(db_session)
    run_observation_sweep(db_session, bus, build_observable_registry(), company.id)

    first = run_interpretation_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)
    second = run_interpretation_sweep(db_session, bus, build_capability_registry(), DeterministicLLMClient(), company.id)

    assert first["observations_interpreted"] == 1
    assert second["observations_interpreted"] == 0
