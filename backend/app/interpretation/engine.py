"""Business Event Interpretation Engine: turns a factual ObservationDetected
Business Event into a structured Interpretation -- "what's happening and why
it matters". Pure computation plus one LLM call for the free-text narrative;
never mutates the Data Core, a Baseline, an Observation or a Significance,
and never proposes or executes an action itself.

Three concepts, kept explicitly distinct (see brain/interpretation_engine.md):

    Business Event   = fait détecté             (app.observation, unchanged)
    Interpretation    = compréhension produite par l'IA   (this module)
    Risk/Opportunity  = résultat métier dérivé   (app.intelligence's own Risk/
                         Opportunity rows from the older per-metric rules --
                         NOT created or replaced by this module)

Classification (risk / opportunity / insight / observation) is a small,
generic, auditable function of Significance fields the Observation Engine
already computed -- never a second detection pass, never a per-event-type
`if` branch, and never a call to the LLM: the LLM's role here is strictly the
free-text explanation (`app.interpretation.context` + `_explain` below),
never the classification itself, so that behavior stays deterministic and
testable without a live API key (see app.ai.llm.DeterministicLLMClient).

Turning an Interpretation into concrete options and a Task proposal is the
Decision Intelligence layer's job (app.decision), not this module's: as of
that step, this Engine no longer proposes a Task itself (an earlier version
of this file did) -- see brain/decision_intelligence.md and brain/decisions.md
decision #16 for why that responsibility moved one layer up.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.ai.capabilities.registry import CapabilityRegistry
from app.ai.llm import DeterministicLLMClient, LLMClient
from app.ai.orchestrator.service import _resolve_entity_by_ref
from app.core.entities import EventLogEntry, RelatedEntityType
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.core.i18n import both, current_locale, llm_language, tx, use_locale
from app.core.observable_labels import domain_label, impact_label, observable_label
from app.interpretation.context import assemble_context
from app.observation.engine import OBSERVATION_DETECTED

EVENT_INTERPRETED = "EventInterpreted"

InterpretationType = Literal["risk", "opportunity", "insight", "observation"]
ConfidenceLevel = Literal["high", "medium", "low"]

# Whether an increase in this Observable's value is desirable -- registered
# once per known metric, the same way app.observation.registry registers
# impact_thresholds once per Observable. This is metadata about a metric's
# polarity, not a new per-event-type detection rule: the deviation itself was
# already computed by Significance: this table only says which sign of an
# already-computed deviation is unfavorable for THIS metric.
_METRIC_DIRECTION: dict[str, Literal["higher_is_better", "lower_is_better"]] = {
    "margin_pct": "higher_is_better",
    "delivery_delay_days": "lower_is_better",
    "customer_revenue_variation_pct": "higher_is_better",
    # Step 22 (external data): a longer-unanswered message is a genuinely
    # universal "worse" fact, independent of the message's own content or
    # business scenario -- structurally identical to delivery_delay_days.
    "supplier_unanswered_message_age_days": "lower_is_better",
    "customer_unanswered_message_age_days": "lower_is_better",
    # V2: a quote waiting longer for an answer is always worse.
    "customer_quote_pending_age_days": "lower_is_better",
}


@dataclass(frozen=True)
class Interpretation:
    type: InterpretationType
    title: str
    explanation: str
    potential_impact: str
    recommendation: str | None
    confidence: ConfidenceLevel
    domain: str
    entity_type: RelatedEntityType
    entity_id: uuid.UUID
    entity_name: str
    observable: str
    observations_used: list[dict]
    capabilities_consulted: list[str]
    source_observation_event_id: uuid.UUID
    # {"fr": {title, explanation, recommendation}, "en": {...}} (brain/decisions.md #58)
    i18n: dict | None = None


def _confidence_level(baseline_confidence: str) -> ConfidenceLevel:
    if baseline_confidence == "high":
        return "high"
    if baseline_confidence == "medium":
        return "medium"
    return "low"  # "low" and "insufficient" both read as low confidence to a human


def classify(payload: dict) -> tuple[InterpretationType, ConfidenceLevel]:
    """The one classification rule, reused for every Observable -- see the
    module docstring for why this is deterministic rather than LLM-decided.

    - `insufficient` confidence: there isn't even a real baseline to compare
      against -- the honest answer is "observation" (a fact, no judgment).
    - `low` confidence (a generic-benchmark or thin-sample baseline): the
      magnitude may be real, but the reference it's measured against is a
      guess -- "insight" (worth watching, not confidently a Risk/Opportunity).
    - `medium`/`high` confidence with a known metric direction: a materially
      unfavorable deviation is a "risk", a favorable one an "opportunity".
    """

    baseline_confidence = payload.get("baseline_confidence", "insufficient")
    if baseline_confidence == "insufficient":
        return "observation", "low"

    deviation = payload.get("deviation")
    direction = _METRIC_DIRECTION.get(payload.get("observable"))
    if deviation is None or direction is None:
        return "observation", _confidence_level(baseline_confidence)

    if baseline_confidence == "low":
        return "insight", "low"

    is_bad = (direction == "higher_is_better" and deviation < 0) or (
        direction == "lower_is_better" and deviation > 0
    )
    return ("risk" if is_bad else "opportunity"), _confidence_level(baseline_confidence)


def _title(interpretation_type: InterpretationType, payload: dict) -> str:
    """A short, human-facing title in the active language, never the raw
    Observable identifier (Step 27: a machine field name like
    "delivery_delay_days" must never reach the UI; see
    app.core.observable_labels)."""

    entity_name = payload.get("entity_name")
    label = observable_label(payload.get("observable"))
    return {
        "risk": tx(f"{entity_name} — écart défavorable sur {label}", f"{entity_name} — unfavourable deviation in {label}"),
        "opportunity": tx(f"{entity_name} — amélioration sur {label}", f"{entity_name} — improvement in {label}"),
        "insight": tx(f"{entity_name} — anomalie sur {label} à surveiller", f"{entity_name} — anomaly in {label} to watch"),
        "observation": tx(f"{entity_name} — anomalie détectée sur {label}", f"{entity_name} — anomaly detected in {label}"),
    }[interpretation_type]


def _potential_impact(payload: dict) -> str:
    """Internal-only summary string (never returned to the frontend -- see
    HomeService.get_decisions, which does not forward `potential_impact`),
    so English/technical wording here is fine; kept for audit/debugging."""

    return (
        f"{payload.get('impact', 'low')} impact, {payload.get('urgency', 'low')} urgency "
        f"(deviation {payload.get('deviation')} from a {payload.get('baseline_source')} baseline)"
    )


def _recommendation(interpretation_type: InterpretationType, payload: dict) -> str | None:
    # Deliberately none for insight/observation -- the classifier itself
    # wasn't confident enough to call this a Risk or Opportunity, so it must
    # not manufacture a confident-sounding recommendation either.
    entity_name = payload.get("entity_name")
    domain = domain_label(payload.get("domain"))
    label = observable_label(payload.get("observable"))
    if interpretation_type == "risk":
        return tx(
            f"Examiner {entity_name} ({domain}) et envisager une tâche pour investiguer l'écart sur {label} avant qu'il ne s'aggrave.",
            f"Review {entity_name} ({domain}) and consider a task to investigate the deviation in {label} before it gets worse.",
        )
    if interpretation_type == "opportunity":
        return tx(
            f"Envisager de renforcer la relation avec {entity_name} pour capitaliser sur l'amélioration de {label}.",
            f"Consider strengthening the relationship with {entity_name} to build on the improvement in {label}.",
        )
    return None


def _deterministic_explanation(interpretation_type: InterpretationType, payload: dict) -> str:
    """A clean, honest sentence (active language) built directly from the same
    structured data an LLM would have received -- used only when no real
    LLM is configured (see app.ai.llm.DeterministicLLMClient), so the MVP
    never shows a raw JSON/prompt dump in place of an explanation (Step 27).
    A real LLM, once configured, replaces this with its own free-text
    explanation via `_explain` below -- this is not a second intelligence
    layer, just this one call's fallback when there is no LLM to call.

    Includes the real message subject when the triggering Observable
    attached one (`extra_context`, step 22's "the explanation should
    reference the actual message" feature) -- the fallback must not lose
    that real information just because there is no LLM to call."""

    entity_name = payload.get("entity_name") or tx("Cette entité", "This entity")
    label = observable_label(payload.get("observable"))
    impact = impact_label(payload.get("impact"))
    sentences = {
        "risk": tx(
            f"{entity_name} présente un écart défavorable sur {label}, avec un impact jugé {impact}.",
            f"{entity_name} shows an unfavourable deviation in {label}, with an impact assessed as {impact}.",
        ),
        "opportunity": tx(
            f"{entity_name} montre une amélioration sur {label}, une opportunité à impact {impact}.",
            f"{entity_name} shows an improvement in {label}, an opportunity with {impact} impact.",
        ),
        "insight": tx(
            f"Une anomalie a été repérée sur {label} pour {entity_name} — à surveiller, pas encore confirmée comme un risque ou une opportunité.",
            f"An anomaly was spotted in {label} for {entity_name} — to watch, not yet confirmed as a risk or an opportunity.",
        ),
        "observation": tx(
            f"Une variation a été observée sur {label} pour {entity_name}, sans référence historique assez fiable pour la qualifier davantage.",
            f"A variation was observed in {label} for {entity_name}, without a reliable enough history to qualify it further.",
        ),
    }
    sentence = sentences[interpretation_type]

    # The subject of a real message is source data: quoted, never translated.
    message_subject = (payload.get("extra_context") or {}).get("message_subject")
    if message_subject:
        sentence += tx(f" Message concerné : « {message_subject} ».", f' Related message: "{message_subject}".')
    return sentence


def _explain(llm: LLMClient, context: dict, interpretation_type: InterpretationType, payload: dict) -> str:
    if isinstance(llm, DeterministicLLMClient):
        return _deterministic_explanation(interpretation_type, payload)

    system_prompt = (
        "You are the Business Event Interpretation assistant inside an AI Business OS. "
        "Explain, in plain business language, what the structured data below means for this "
        "company -- strictly from that data, never inventing a number or fact not present in it. "
        f"This event has already been classified as '{interpretation_type}' by a deterministic "
        "rule; do not propose a different classification, only explain in one or two sentences "
        "why the data supports it and what it implies. "
        + llm_language()
    )
    user_prompt = f"Business Event interpretation context:\n{json.dumps(context, indent=2, default=str)}"
    return llm.complete(system_prompt=system_prompt, user_prompt=user_prompt)


def interpret_event(
    session: Session,
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    llm: LLMClient,
    company_id: uuid.UUID,
    entry: EventLogEntry,
) -> Interpretation:
    """Builds one Interpretation from one ObservationDetected Event Log
    entry. Pure computation plus one LLM call -- never mutates the Data Core,
    a Baseline, an Observation or a Significance."""

    payload = entry.payload
    interpretation_type, confidence = classify(payload)
    context, capabilities_consulted = assemble_context(
        session, event_bus, capability_registry, llm, company_id, entry
    )
    # Generated in both interface languages (brain/decisions.md #58): the
    # user may switch language after the analysis was produced, and the AI
    # text itself -- not a translation of it -- must then be in that language.
    texts = both(
        lambda: {
            "title": _title(interpretation_type, payload),
            "explanation": _explain(llm, context, interpretation_type, payload),
            "recommendation": _recommendation(interpretation_type, payload),
        }
    )

    observations_used = [
        {
            "observable": payload.get("observable"),
            "entity_name": payload.get("entity_name"),
            "current_value": payload.get("current_value"),
            "baseline_reference_value": payload.get("baseline_reference_value"),
            "deviation": payload.get("deviation"),
        },
        *payload.get("correlated_observations", []),
    ]

    return Interpretation(
        type=interpretation_type,
        title=texts["fr"]["title"],
        explanation=texts["fr"]["explanation"],
        potential_impact=_potential_impact(payload),
        recommendation=texts["fr"]["recommendation"],
        confidence=confidence,
        domain=payload.get("domain"),
        entity_type=RelatedEntityType(payload["entity_type"]),
        entity_id=uuid.UUID(payload["entity_id"]),
        entity_name=payload.get("entity_name"),
        observable=payload.get("observable"),
        observations_used=observations_used,
        capabilities_consulted=capabilities_consulted,
        source_observation_event_id=entry.event_id,
        i18n=texts,
    )


def _interpretation_payload(interpretation: Interpretation) -> dict:
    return {
        "type": interpretation.type,
        "title": interpretation.title,
        "explanation": interpretation.explanation,
        "potential_impact": interpretation.potential_impact,
        "recommendation": interpretation.recommendation,
        "confidence": interpretation.confidence,
        "domain": interpretation.domain,
        "entity_type": interpretation.entity_type.value,
        "entity_id": str(interpretation.entity_id),
        "entity_name": interpretation.entity_name,
        "observable": interpretation.observable,
        "observations_used": interpretation.observations_used,
        "capabilities_consulted": interpretation.capabilities_consulted,
        "source_observation_event_id": str(interpretation.source_observation_event_id),
        "i18n": interpretation.i18n,
    }


def _legacy_explanation(payload: dict) -> str | None:
    """For an analysis stored before both languages were kept: the
    deterministic sentence in the active language, but only when the stored
    French text is exactly that sentence -- an LLM-written explanation is
    never replaced by a template."""

    stored = payload.get("explanation")
    observed = (payload.get("observations_used") or [{}])[0]
    subject = None
    if stored and "« " in stored:
        subject = stored.rsplit("« ", 1)[1].rsplit(" »", 1)[0]
    for impact in ("high", "medium", "low"):
        source = {**observed, "entity_name": payload.get("entity_name"), "observable": payload.get("observable"), "impact": impact}
        if subject:
            source["extra_context"] = {"message_subject": subject}
        with use_locale("fr"):
            if _deterministic_explanation(payload["type"], source) != stored:
                continue
        return _deterministic_explanation(payload["type"], source)
    return None


def localize_interpretation(payload: dict) -> dict:
    """An EventInterpreted payload with its texts in the active language."""

    out = dict(payload)
    entry = (payload.get("i18n") or {}).get(current_locale())
    if entry:
        out.update(entry)
        return out
    kind = payload.get("type")
    if kind not in ("risk", "opportunity", "insight", "observation"):
        return out
    with use_locale("fr"):
        fr_title, fr_recommendation = _title(kind, payload), _recommendation(kind, payload)
    if payload.get("title") == fr_title:
        out["title"] = _title(kind, payload)
    if payload.get("recommendation") == fr_recommendation:
        out["recommendation"] = _recommendation(kind, payload)
    explanation = _legacy_explanation(payload)
    if explanation is not None:
        out["explanation"] = explanation
    return out


def _already_interpreted(session: Session, observation_event_id: uuid.UUID) -> bool:
    target = str(observation_event_id)
    return any(
        entry.payload.get("source_observation_event_id") == target
        for entry in session.query(EventLogEntry).filter_by(event_type=EVENT_INTERPRETED).all()
    )


def run_interpretation_sweep(
    session: Session,
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    llm: LLMClient,
    company_id: uuid.UUID,
) -> dict:
    """The one entry point a manual trigger (or, later, a scheduler) calls:
    interprets every ObservationDetected Business Event for this company that
    hasn't been interpreted yet. Safe to call repeatedly: an
    already-interpreted observation is skipped. Publishing EventInterpreted
    is the only side effect -- no Task is proposed here (see
    app.decision.engine.run_decision_sweep for that step)."""

    interpreted = 0
    by_type: dict[str, int] = {"risk": 0, "opportunity": 0, "insight": 0, "observation": 0}

    entries = session.query(EventLogEntry).filter_by(event_type=OBSERVATION_DETECTED).all()
    for entry in entries:
        if _already_interpreted(session, entry.event_id):
            continue

        supplier, product, customer = _resolve_entity_by_ref(
            session, entry.payload.get("entity_type"), entry.payload.get("entity_id")
        )
        entity = supplier or product or customer
        if entity is None or entity.company_id != company_id:
            continue

        interpretation = interpret_event(session, event_bus, capability_registry, llm, company_id, entry)
        event_bus.publish(
            BusinessEvent(
                event_type=EVENT_INTERPRETED,
                source="interpretation_engine",
                payload=_interpretation_payload(interpretation),
            )
        )
        interpreted += 1
        by_type[interpretation.type] += 1

    return {
        "observations_interpreted": interpreted,
        "by_type": by_type,
    }
