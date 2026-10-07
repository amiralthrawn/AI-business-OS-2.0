"""Business State Snapshot: a compact, deterministic, derived view of the
company's current state, built for the AI Orchestrator to consult on a broad
or proactive question instead of loading the whole Data Core into an LLM's
context.

This is explicitly NOT a second Data Core and NOT a new source of truth: it
is assembled fresh, on demand, from what Intelligence has already found (open
Risks and Opportunities) plus Baseline/Significance for each one. No LLM, no
RAG, no embeddings, no persistent cache -- see brain/business_state.md for
why each of those is deferred rather than built here.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.i18n import text_of, tx
from app.core.observable_labels import observable_label
from app.intelligence.risks.kinds import CUSTOMER_DECLINE, MARGIN_DETERIORATION, SUPPLIER_PERFORMANCE
from app.business_context.service import BusinessContextService
from app.core.baseline import Baseline, customer_value_baseline, margin_baseline, supplier_delivery_baseline
from app.core.entities import (
    BusinessContext,
    EventLogEntry,
    Opportunity,
    OpportunityStatus,
    Product,
    RelatedEntityType,
    Risk,
    RiskStatus,
)
from app.core.significance import Significance, assess_significance
from app.home.service import HomeService
from app.observation.engine import OBSERVATION_DETECTED

# Duplicated from app.interpretation.engine.EVENT_INTERPRETED and
# app.decision.engine.DECISION_PROPOSED rather than imported: both of those
# modules' own context assembly transitively imports build_snapshot (a
# Business State Snapshot is part of their own context), so importing either
# one back from here would be a circular import. Two one-line string
# constants are a small, safe price for keeping the dependency
# one-directional (Snapshot has no need to import anything else from
# app.interpretation or app.decision).
_EVENT_INTERPRETED = "EventInterpreted"
_DECISION_PROPOSED = "DecisionProposed"

# Mirrors the thresholds the corresponding Intelligence rule already uses
# (app.intelligence.risks.service / app.core.analytics). Duplicated here
# rather than imported because Significance classifies a *deviation from
# baseline*, while the existing rules classify an absolute recent value or
# point_change -- unifying the two is a deferred refactor (brain/business_state.md),
# not done here to avoid touching stable, tested detection code.
_MARGIN_IMPACT_THRESHOLDS = (0.05, 0.10)
_DELIVERY_IMPACT_THRESHOLDS = (1.5, 3.0)
_CUSTOMER_IMPACT_THRESHOLDS = (0.15, 0.35)


@dataclass
class SnapshotArea:
    domain: str
    kind: str  # "risk" | "opportunity" | "observation" | "interpretation"
    title: str
    entity_type: RelatedEntityType | None
    entity_id: uuid.UUID | None
    metric: str | None
    baseline: Baseline | None
    current_value: float | None
    significance: Significance
    # Only populated for kind="interpretation"/"decision" -- the AI's
    # classification and narrative from app.interpretation/app.decision,
    # never recomputed here. None for every other kind, kept backward
    # compatible with existing areas.
    interpretation_type: str | None = None
    explanation: str | None = None
    recommendation: str | None = None
    # Only populated for kind="decision" -- the concrete options
    # app.decision.engine generated, each as {label, expected_benefit, trade_offs}.
    decision_options: list[dict] | None = None


@dataclass
class BusinessStateSnapshot:
    generated_at: datetime
    monitored_domains: list[str]
    stated_objectives: str | None
    open_risks_count: int
    open_opportunities_count: int
    pending_validation_tasks: int
    areas: list[SnapshotArea] = field(default_factory=list)

    @property
    def material_areas(self) -> list[SnapshotArea]:
        """Material areas only, most urgent/impactful first -- this is what
        the Orchestrator drills into for a broad question, not the full list."""

        materials = [a for a in self.areas if a.significance.is_material]
        return sorted(
            materials,
            key=lambda a: (a.significance.urgency != "high", a.significance.impact != "high"),
        )


def _strategic_relevance(business_context: BusinessContext, domain: str, keyword: str) -> str:
    objectives = (business_context.stated_objectives or "").lower()
    if keyword in objectives:
        return "high"
    if domain in business_context.monitored_domains:
        return "medium"
    return "low"


def _recurrence_count(session: Session, event_type: str, related_entity_id: uuid.UUID | None) -> int:
    """How many times this kind of signal event has already fired for this
    entity. A real, queryable number from the Event Log -- not estimated.
    Payload matching is a Python-side scan, acceptable at this dataset's
    scale (documented limitation, see brain/business_state.md)."""

    if related_entity_id is None:
        return 0
    target = str(related_entity_id)
    count = 0
    for entry in session.query(EventLogEntry).filter_by(event_type=event_type).all():
        if target in (v for v in entry.payload.values() if isinstance(v, str)):
            count += 1
    # The occurrence that triggered the current Risk/Opportunity isn't itself
    # a "recurrence" of anything.
    return max(count - 1, 0)


def _build_area_for_risk(session: Session, risk: Risk, business_context: BusinessContext) -> SnapshotArea:
    title = text_of(risk, "title")

    if MARGIN_DETERIORATION.matches(title) and risk.related_entity_type == RelatedEntityType.PRODUCT:
        baseline, current_value = margin_baseline(session, risk.related_entity_id, business_context)
        correlation: list[str] = []
        product = session.get(Product, risk.related_entity_id)
        if product is not None and product.supplier_id is not None:
            correlated = (
                session.query(Risk)
                .filter(
                    Risk.related_entity_type == RelatedEntityType.SUPPLIER,
                    Risk.related_entity_id == product.supplier_id,
                    Risk.status == RiskStatus.OPEN,
                )
                .first()
            )
            if correlated is not None:
                correlation.append(text_of(correlated, "title"))
        significance = assess_significance(
            baseline,
            current_value,
            impact_thresholds=_MARGIN_IMPACT_THRESHOLDS,
            recurrence_count=_recurrence_count(session, "MarginDeteriorated", risk.related_entity_id),
            correlation=correlation,
            strategic_relevance=_strategic_relevance(business_context, "finance", "margin"),
        )
        return SnapshotArea(
            "finance", "risk", title, risk.related_entity_type, risk.related_entity_id,
            "margin_pct", baseline, current_value, significance,
        )

    if SUPPLIER_PERFORMANCE.matches(title) and risk.related_entity_type == RelatedEntityType.SUPPLIER:
        baseline, current_value = supplier_delivery_baseline(session, risk.related_entity_id, business_context)
        significance = assess_significance(
            baseline,
            current_value,
            impact_thresholds=_DELIVERY_IMPACT_THRESHOLDS,
            recurrence_count=_recurrence_count(session, "SupplierPerformanceDeteriorated", risk.related_entity_id),
            strategic_relevance=_strategic_relevance(business_context, "procurement", "supplier"),
        )
        return SnapshotArea(
            "procurement", "risk", title, risk.related_entity_type, risk.related_entity_id,
            "delivery_delay_days", baseline, current_value, significance,
        )

    if CUSTOMER_DECLINE.matches(title) and risk.related_entity_type == RelatedEntityType.CUSTOMER:
        baseline, current_value = customer_value_baseline(session, risk.related_entity_id, business_context)
        significance = assess_significance(
            baseline,
            current_value,
            impact_thresholds=_CUSTOMER_IMPACT_THRESHOLDS,
            recurrence_count=_recurrence_count(session, "CustomerDeclineDetected", risk.related_entity_id),
            strategic_relevance=_strategic_relevance(business_context, "sales", "customer"),
        )
        return SnapshotArea(
            "sales", "risk", title, risk.related_entity_type, risk.related_entity_id,
            "customer_revenue_variation_pct", baseline, current_value, significance,
        )

    # Reactive, already-realized events (e.g. "Supplier cost increase..."):
    # there is no ongoing trend to baseline against, so impact is taken
    # directly from the severity Intelligence already assigned rather than
    # recomputed from a deviation that doesn't apply to a one-off event.
    impact = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}[risk.severity.value]
    significance = Significance(
        deviation=None,
        impact=impact,
        urgency=impact,
        persistence="new",
        recurrence_count=0,
        correlation=[],
        strategic_relevance=_strategic_relevance(business_context, "procurement", "cost"),
        confidence="high",
    )
    return SnapshotArea(
        "procurement", "risk", title, risk.related_entity_type, risk.related_entity_id,
        None, None, None, significance,
    )


def _build_area_for_observation(entry: EventLogEntry) -> SnapshotArea:
    """Builds a SnapshotArea directly from an ObservationDetected payload --
    no recomputation: the Observation Engine (app.observation) already did
    the Baseline/Significance work when it published this event, so this
    just re-hydrates what's already there. This is how the Snapshot starts
    being fed by Business Events instead of depending only on Risks/
    Opportunities that already went through the older, per-metric detection
    rules (see brain/observation_engine.md)."""

    payload = entry.payload
    correlated = payload.get("correlated_observations") or []
    significance = Significance(
        deviation=payload.get("deviation"),
        impact=payload.get("impact", "low"),
        urgency=payload.get("urgency", "low"),
        persistence="recurring" if payload.get("recurrence_count", 0) > 1 else (
            "ongoing" if payload.get("recurrence_count", 0) == 1 else "new"
        ),
        recurrence_count=payload.get("recurrence_count", 0),
        correlation=[c.get("entity_name", "") for c in correlated],
        strategic_relevance=payload.get("strategic_relevance", "low"),
        confidence=payload.get("baseline_confidence", "insufficient"),
    )
    entity_type = payload.get("entity_type")
    entity_id = payload.get("entity_id")
    return SnapshotArea(
        domain=payload.get("domain", "unknown"),
        kind="observation",
        title=tx(
            f"{payload.get('entity_name')} — anomalie détectée sur {observable_label(payload.get('observable'))}",
            f"{payload.get('entity_name')} — anomaly detected in {observable_label(payload.get('observable'))}",
        ),
        entity_type=RelatedEntityType(entity_type) if entity_type else None,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        metric=payload.get("observable"),
        baseline=None,  # embedded directly in the payload fields above, not reconstructed as an object
        current_value=payload.get("current_value"),
        significance=significance,
    )


def _build_area_for_interpretation(observation_entry: EventLogEntry, interpretation_entry: EventLogEntry) -> SnapshotArea:
    """Builds a richer SnapshotArea from an EventInterpreted payload, paired
    with the ObservationDetected entry it interprets -- Baseline/Significance
    numbers come from the Observation (unchanged, not recomputed), while
    kind/title/explanation/recommendation come from the Interpretation
    Engine's own judgment (app.interpretation). Supersedes the plain
    "observation" area for the same entity: this is strictly richer, not a
    duplicate (see brain/interpretation_engine.md)."""

    obs_payload = observation_entry.payload
    from app.interpretation.engine import localize_interpretation  # circular at module load

    interp_payload = localize_interpretation(interpretation_entry.payload)
    correlated = obs_payload.get("correlated_observations") or []
    significance = Significance(
        deviation=obs_payload.get("deviation"),
        impact=obs_payload.get("impact", "low"),
        urgency=obs_payload.get("urgency", "low"),
        persistence="recurring" if obs_payload.get("recurrence_count", 0) > 1 else (
            "ongoing" if obs_payload.get("recurrence_count", 0) == 1 else "new"
        ),
        recurrence_count=obs_payload.get("recurrence_count", 0),
        correlation=[c.get("entity_name", "") for c in correlated],
        strategic_relevance=obs_payload.get("strategic_relevance", "low"),
        confidence=obs_payload.get("baseline_confidence", "insufficient"),
    )
    entity_type = interp_payload.get("entity_type")
    entity_id = interp_payload.get("entity_id")
    return SnapshotArea(
        domain=interp_payload.get("domain", "unknown"),
        kind="interpretation",
        title=interp_payload.get("title", ""),
        entity_type=RelatedEntityType(entity_type) if entity_type else None,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        metric=interp_payload.get("observable"),
        baseline=None,
        current_value=obs_payload.get("current_value"),
        significance=significance,
        interpretation_type=interp_payload.get("type"),
        explanation=interp_payload.get("explanation"),
        recommendation=interp_payload.get("recommendation"),
    )


def _build_area_for_decision(
    observation_entry: EventLogEntry, interpretation_entry: EventLogEntry, decision_entry: EventLogEntry
) -> SnapshotArea:
    """Builds the richest SnapshotArea, from a DecisionProposed payload paired
    with the ObservationDetected/EventInterpreted entries it builds on --
    Baseline/Significance numbers still come from the Observation (unchanged,
    not recomputed), while kind/title/explanation/recommendation/options come
    from the Decision Intelligence Engine's own output (app.decision).
    Supersedes the "interpretation" area for the same entity: strictly
    richer, not a duplicate (see brain/decision_intelligence.md)."""

    obs_payload = observation_entry.payload
    from app.decision.engine import localize_decision  # circular at module load

    decision_payload = localize_decision(decision_entry.payload)
    correlated = obs_payload.get("correlated_observations") or []
    significance = Significance(
        deviation=obs_payload.get("deviation"),
        impact=obs_payload.get("impact", "low"),
        urgency=obs_payload.get("urgency", "low"),
        persistence="recurring" if obs_payload.get("recurrence_count", 0) > 1 else (
            "ongoing" if obs_payload.get("recurrence_count", 0) == 1 else "new"
        ),
        recurrence_count=obs_payload.get("recurrence_count", 0),
        correlation=[c.get("entity_name", "") for c in correlated],
        strategic_relevance=obs_payload.get("strategic_relevance", "low"),
        confidence=obs_payload.get("baseline_confidence", "insufficient"),
    )
    entity_type = decision_payload.get("entity_type")
    entity_id = decision_payload.get("entity_id")
    recommendation = decision_payload.get("recommendation") or {}
    return SnapshotArea(
        domain=decision_payload.get("domain", "unknown"),
        kind="decision",
        title=decision_payload.get("problem", ""),
        entity_type=RelatedEntityType(entity_type) if entity_type else None,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        metric=interpretation_entry.payload.get("observable"),
        baseline=None,
        current_value=obs_payload.get("current_value"),
        significance=significance,
        interpretation_type=decision_payload.get("type"),
        explanation=recommendation.get("reasoning"),
        recommendation=recommendation.get("chosen_option"),
        decision_options=decision_payload.get("options") or [],
    )


def _build_area_for_opportunity(session: Session, opportunity: Opportunity, business_context: BusinessContext) -> SnapshotArea:
    baseline, current_value = customer_value_baseline(session, opportunity.related_entity_id, business_context)
    significance = assess_significance(
        baseline,
        current_value,
        impact_thresholds=_CUSTOMER_IMPACT_THRESHOLDS,
        recurrence_count=_recurrence_count(session, "CustomerGrowthDetected", opportunity.related_entity_id),
        strategic_relevance=_strategic_relevance(business_context, "sales", "customer"),
    )
    return SnapshotArea(
        "sales", "opportunity", text_of(opportunity, "title"), opportunity.related_entity_type,
        opportunity.related_entity_id, "customer_revenue_variation_pct", baseline, current_value, significance,
    )


def build_snapshot(session: Session, company_id: uuid.UUID) -> BusinessStateSnapshot:
    business_context = BusinessContextService(session).get_or_create(company_id)
    home = HomeService(session)
    risks_summary = home.get_risks_summary()
    opportunities_summary = home.get_opportunities_summary()
    tasks_summary = home.get_tasks_summary()

    open_risks = session.query(Risk).filter_by(status=RiskStatus.OPEN).all()
    open_opportunities = session.query(Opportunity).filter_by(status=OpportunityStatus.OPEN).all()

    areas: list[SnapshotArea] = [_build_area_for_risk(session, risk, business_context) for risk in open_risks]
    areas.extend(_build_area_for_opportunity(session, opportunity, business_context) for opportunity in open_opportunities)

    # Business Events from the Observation Engine (app.observation) feed the
    # Snapshot too, alongside Risks/Opportunities -- but only for an entity
    # not already represented above, so the same phenomenon never shows up
    # twice just because it was both observed and separately promoted to a
    # Risk/Opportunity by the older, per-metric detection rules.
    covered_entity_ids = {str(r.related_entity_id) for r in open_risks if r.related_entity_id} | {
        str(o.related_entity_id) for o in open_opportunities if o.related_entity_id
    }

    observation_entries_by_event_id = {
        str(e.event_id): e for e in session.query(EventLogEntry).filter_by(event_type=OBSERVATION_DETECTED).all()
    }
    interpretation_entries_by_event_id = {
        str(e.event_id): e for e in session.query(EventLogEntry).filter_by(event_type=_EVENT_INTERPRETED).all()
    }

    # DecisionProposed (app.decision) events supersede the "interpretation"
    # area for the same entity with the richest one yet -- options,
    # trade-offs and a recommendation, not a duplicate signal.
    decided_interpretation_ids: set[str] = set()
    for decision_entry in session.query(EventLogEntry).filter_by(event_type=_DECISION_PROPOSED).all():
        interp_id = decision_entry.payload.get("source_interpretation_event_id")
        decided_interpretation_ids.add(interp_id)
        if decision_entry.payload.get("entity_id") in covered_entity_ids:
            continue
        interpretation_entry = interpretation_entries_by_event_id.get(interp_id)
        if interpretation_entry is None:
            continue  # data inconsistency guard -- shouldn't happen, never fatal
        observation_entry = observation_entries_by_event_id.get(
            interpretation_entry.payload.get("source_observation_event_id")
        )
        if observation_entry is None:
            continue
        areas.append(_build_area_for_decision(observation_entry, interpretation_entry, decision_entry))

    # EventInterpreted (app.interpretation) events supersede the plain
    # "observation" area for the same entity with a richer "interpretation"
    # one -- the AI's classification and narrative, not a duplicate signal.
    # Skipped here when a Decision already exists for it (represented above).
    interpreted_observation_ids: set[str] = set()
    for interp_id, interp_entry in interpretation_entries_by_event_id.items():
        source_id = interp_entry.payload.get("source_observation_event_id")
        interpreted_observation_ids.add(source_id)
        if interp_id in decided_interpretation_ids:
            continue  # already represented above as a richer "decision" area
        if interp_entry.payload.get("entity_id") in covered_entity_ids:
            continue
        observation_entry = observation_entries_by_event_id.get(source_id)
        if observation_entry is None:
            continue  # data inconsistency guard -- shouldn't happen, never fatal
        areas.append(_build_area_for_interpretation(observation_entry, interp_entry))

    for event_id, observation_entry in observation_entries_by_event_id.items():
        if observation_entry.payload.get("entity_id") in covered_entity_ids:
            continue
        if event_id in interpreted_observation_ids:
            continue  # already represented above as a richer "interpretation"/"decision" area
        areas.append(_build_area_for_observation(observation_entry))

    return BusinessStateSnapshot(
        generated_at=datetime.now(timezone.utc),
        monitored_domains=business_context.monitored_domains,
        stated_objectives=business_context.stated_objectives,
        open_risks_count=risks_summary["total_risks"],
        open_opportunities_count=opportunities_summary["total_opportunities"],
        pending_validation_tasks=tasks_summary["pending_validation_tasks"],
        areas=areas,
    )
