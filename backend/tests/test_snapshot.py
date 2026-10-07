from data.seed import seed
from app.event_bus import build_event_bus
from app.snapshot.service import build_snapshot


def test_snapshot_reflects_no_signal_on_an_empty_business(db_session, event_bus):
    from app.core.entities import Company

    company = Company(name="Empty Co")
    db_session.add(company)
    db_session.commit()

    snapshot = build_snapshot(db_session, company.id)

    assert snapshot.open_risks_count == 0
    assert snapshot.open_opportunities_count == 0
    assert snapshot.areas == []
    assert snapshot.material_areas == []


def test_snapshot_over_the_full_demo_dataset_identifies_material_areas(db_session, session_factory):
    seed(db_session, build_event_bus(session_factory))

    from app.core.entities import Company

    company = db_session.query(Company).one()
    snapshot = build_snapshot(db_session, company.id)

    assert snapshot.open_risks_count == 4
    assert snapshot.open_opportunities_count == 1
    # 4 risks + 1 opportunity + 2 Decision Intelligence areas for Coastal
    # Metal Supply (Chain 4: too little history for a confirmed delivery
    # Risk, see brain/decision_intelligence.md; plus, since step 22, a real
    # unanswered-message Risk from its own external Communication, see
    # brain/external_data_intelligence.md) -- neither covered by any Risk/
    # Opportunity, so both surface in their own right.
    assert len(snapshot.areas) == 7
    decision_areas = {a.metric: a for a in snapshot.areas if a.kind == "decision"}
    assert decision_areas["delivery_delay_days"].interpretation_type == "insight"
    assert decision_areas["delivery_delay_days"].decision_options == []  # not confident enough to offer options
    assert decision_areas["supplier_unanswered_message_age_days"].interpretation_type == "risk"
    assert decision_areas["supplier_unanswered_message_age_days"].domain == "procurement"
    assert decision_areas["supplier_unanswered_message_age_days"].recommendation

    material = snapshot.material_areas
    assert len(material) > 0
    assert all(area.significance.is_material for area in material)

    # Every risk/opportunity kind produced a real Significance with a
    # meaningful, non-degenerate classification -- not a placeholder.
    domains = {area.domain for area in snapshot.areas}
    assert domains == {"finance", "procurement", "sales"}

    margin_area = next(a for a in snapshot.areas if a.metric == "margin_pct")
    assert margin_area.baseline is not None
    # The seed declares margin_pct=0.30 in Business Context, so the deviation
    # is measured against that declared target, not the observed history --
    # exactly the "declared != observed" distinction this layer exists for.
    assert margin_area.baseline.source == "declared"
    assert margin_area.significance.deviation is not None
    assert margin_area.significance.confidence in {"low", "medium", "high"}

    from app.intelligence.risks.kinds import SUPPLIER_COST_INCREASE

    reactive_area = next(a for a in snapshot.areas if SUPPLIER_COST_INCREASE.matches(a.title))
    assert reactive_area.significance.impact == "high"
    assert reactive_area.baseline is None  # one-off event, no trend to baseline against


def test_snapshot_uses_declared_baseline_over_observed(db_session, session_factory):
    from app.business_context.service import BusinessContextService

    seed(db_session, build_event_bus(session_factory))

    from app.core.entities import Company

    company = db_session.query(Company).one()
    BusinessContextService(db_session).update(company.id, declared_baselines={"margin_pct": 0.30})

    snapshot = build_snapshot(db_session, company.id)
    margin_area = next(a for a in snapshot.areas if a.metric == "margin_pct")

    assert margin_area.baseline.source == "declared"
    assert margin_area.baseline.reference_value == 0.30
