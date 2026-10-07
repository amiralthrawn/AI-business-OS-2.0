"""Decision Intelligence Engine: turns an Interpretation into a Decision --
a problem/opportunity statement, a small set of concrete options with their
expected benefits and trade-offs, a reasoned recommendation, and, only when
that recommendation is confident enough to act on, a Task proposal through
the EXISTING Human-in-the-Loop mechanism.

    Interpretation = compréhension ("what's happening and why it matters")
    Decision       = délibération ("what could we do about it, and what do
                      we recommend, if anything") -- this module
    Action Proposal = the one, existing mechanism (ActionsService.propose_task)
                      that turns a Decision's recommendation into something a
                      human can approve or reject; this layer never executes
                      anything itself.

This is deliberately NOT a decision-making engine: `Decision.recommendation`
is advisory, `chosen_option` is `None` whenever the underlying Interpretation
wasn't confident enough (insight/observation) to make a reliable
recommendation ("Ne force jamais"), and even a confident recommendation only
ever reaches the business as a PENDING_VALIDATION Task, never an executed one.

The option catalog per (decision type, domain) is a small, generic lookup --
not a new agent, not a per-specific-event rule -- the same pattern
app.interpretation.engine already used for its own now-removed
recommendation() templates (see brain/decision_intelligence.md). This keeps
today's MVP qualitative and structured while leaving room for a later,
quantitative option-generation strategy (scenario modeling, Monte Carlo,
optimization) to be added here without touching Interpretation, Snapshot or
the Orchestrator.
"""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.actions.service import ActionsService
from app.ai.capabilities.registry import CapabilityRegistry
from app.ai.llm import DeterministicLLMClient, LLMClient
from app.ai.orchestrator.service import _resolve_entity_by_ref
from app.core.entities import EventLogEntry, Opportunity, OpportunityStatus, RelatedEntityType, Risk, RiskStatus
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.core.i18n import both, current_locale, llm_language, tx, use_locale
from app.interpretation.context import assemble_context
from app.interpretation.engine import EVENT_INTERPRETED
from app.observation.engine import OBSERVATION_DETECTED

DECISION_PROPOSED = "DecisionProposed"

# Small, generic option catalogs, one per (decision type, domain) -- not per
# specific metric or event. Each entry is [proactive, proactive, passive]:
# the deterministic recommendation below always combines the two proactive
# options and skips the passive one, mirroring the brief's own example
# ("Investigate renegotiation + alternative supplier", skipping "absorb the
# cost"). A domain this MVP doesn't cover falls back to the "finance" entry,
# the most generic of the three.
_RISK_OPTIONS: dict[str, list[dict[str, dict[str, str]]]] = {
    "procurement": [
        {
            "label": {"fr": "Renégocier les prix ou les conditions directement avec {entity_name}", "en": "Renegotiate prices or terms directly with {entity_name}"},
            "expected_benefit": {"fr": "Pourrait restaurer la marge sans perturber la relation fournisseur.", "en": "Could restore the margin without disrupting the supplier relationship."},
            "trade_offs": {"fr": "Dépend de la volonté de {entity_name} de renégocier ; peut prendre du temps.", "en": "Depends on {entity_name}'s willingness to renegotiate; may take time."},
        },
        {
            "label": {"fr": "Rechercher un fournisseur alternatif pour le ou les produits concernés", "en": "Look for an alternative supplier for the products concerned"},
            "expected_benefit": {"fr": "Réduit la dépendance à un fournisseur unique et l'exposition future au même risque.", "en": "Reduces dependence on a single supplier and future exposure to the same risk."},
            "trade_offs": {"fr": "Changer de fournisseur implique un coût, un risque et un délai d'intégration.", "en": "Switching suppliers means onboarding cost, risk and lead time."},
        },
        {
            "label": {"fr": "Absorber temporairement le coût et réévaluer à la prochaine revue", "en": "Absorb the cost for now and reassess at the next review"},
            "expected_benefit": {"fr": "Aucune perturbation immédiate ; laisse le temps de rassembler plus de données.", "en": "No immediate disruption; leaves time to gather more data."},
            "trade_offs": {"fr": "L'écart persiste entre-temps et peut se reproduire ou s'aggraver.", "en": "The deviation persists meanwhile and may recur or worsen."},
        },
    ],
    "sales": [
        {
            "label": {"fr": "Contacter {entity_name} pour comprendre la cause du problème", "en": "Contact {entity_name} to understand the cause of the problem"},
            "expected_benefit": {"fr": "Traite directement la cause et montre que la relation compte toujours.", "en": "Addresses the cause directly and shows the relationship still matters."},
            "trade_offs": {"fr": "Demande du temps commercial ; la cause peut être hors du contrôle de l'entreprise.", "en": "Takes sales time; the cause may be outside the company's control."},
        },
        {
            "label": {"fr": "Proposer une offre de fidélisation ou des conditions ajustées à {entity_name}", "en": "Offer {entity_name} a loyalty offer or adjusted terms"},
            "expected_benefit": {"fr": "Peut inverser ou ralentir le déclin avant qu'il ne devienne permanent.", "en": "Can reverse or slow the decline before it becomes permanent."},
            "trade_offs": {"fr": "Réduit la marge à court terme sur ce compte ; crée un précédent pour d'autres.", "en": "Reduces short-term margin on this account; sets a precedent for others."},
        },
        {
            "label": {"fr": "Réévaluer la priorité et le niveau de support accordés à ce compte", "en": "Reassess the priority and level of support given to this account"},
            "expected_benefit": {"fr": "Réalloue l'effort si le compte n'est plus stratégiquement prioritaire.", "en": "Reallocates effort if the account is no longer a strategic priority."},
            "trade_offs": {"fr": "Risque d'accélérer le déclin si le compte perçoit un désengagement.", "en": "May speed up the decline if the account senses disengagement."},
        },
    ],
    "finance": [
        {
            "label": {"fr": "Revoir la politique de prix ou la structure de coûts du produit concerné", "en": "Review the pricing policy or cost structure of the product concerned"},
            "expected_benefit": {"fr": "Cible directement la source de l'écart.", "en": "Targets the source of the deviation directly."},
            "trade_offs": {"fr": "Un changement de prix peut affecter la demande ou des contrats existants.", "en": "A price change can affect demand or existing contracts."},
        },
        {
            "label": {"fr": "Investiguer directement le facteur de coût ou de revenu en cause", "en": "Investigate the cost or revenue driver involved directly"},
            "expected_benefit": {"fr": "Construit une vision plus claire avant de s'engager sur une solution précise.", "en": "Builds a clearer picture before committing to a specific solution."},
            "trade_offs": {"fr": "Prend du temps ; l'écart se poursuit pendant l'investigation.", "en": "Takes time; the deviation continues during the investigation."},
        },
        {
            "label": {"fr": "Surveiller un cycle supplémentaire avant d'agir", "en": "Monitor one more cycle before acting"},
            "expected_benefit": {"fr": "Évite de réagir à un signal qui pourrait n'être que temporaire.", "en": "Avoids reacting to a signal that may only be temporary."},
            "trade_offs": {"fr": "Retarde la réponse si l'écart s'avère réel et s'aggrave.", "en": "Delays the response if the deviation proves real and worsens."},
        },
    ],
}

_OPPORTUNITY_OPTIONS: dict[str, list[dict[str, dict[str, str]]]] = {
    "sales": [
        {
            "label": {"fr": "Engager {entity_name} pour développer la relation (vente additionnelle ou croisée)", "en": "Engage {entity_name} to grow the relationship (upsell or cross-sell)"},
            "expected_benefit": {"fr": "Capture davantage de valeur sur un compte déjà en croissance.", "en": "Captures more value from an account that is already growing."},
            "trade_offs": {"fr": "Demande du temps commercial et une offre crédible ; la croissance peut plafonner.", "en": "Takes sales time and a credible offer; growth may plateau."},
        },
        {
            "label": {"fr": "Proposer un contrat plus long ou à plus fort volume pour sécuriser la croissance", "en": "Offer a longer or higher-volume contract to secure the growth"},
            "expected_benefit": {"fr": "Protège la tendance contre une volatilité future.", "en": "Protects the trend against future volatility."},
            "trade_offs": {"fr": "Peut nécessiter des concessions (prix, conditions) pour être conclu.", "en": "May require concessions (price, terms) to close."},
        },
        {
            "label": {"fr": "Allouer plus d'attention commerciale pour soutenir la tendance", "en": "Give the account more sales attention to support the trend"},
            "expected_benefit": {"fr": "Moyen à faible risque de renforcer une tendance déjà positive.", "en": "A low-to-medium-risk way to reinforce an already positive trend."},
            "trade_offs": {"fr": "Détourne de l'attention et des ressources d'autres comptes.", "en": "Diverts attention and resources from other accounts."},
        },
    ],
    "procurement": [
        {
            "label": {"fr": "Formaliser durablement les conditions améliorées avec {entity_name}", "en": "Lock in the improved terms with {entity_name} for the long term"},
            "expected_benefit": {"fr": "Sécurise l'amélioration avant qu'elle ne s'inverse.", "en": "Secures the improvement before it reverses."},
            "trade_offs": {"fr": "Peut nécessiter un engagement plus long que souhaité.", "en": "May require a longer commitment than desired."},
        },
        {
            "label": {"fr": "Explorer une augmentation de volume avec {entity_name} vu la performance actuelle", "en": "Explore higher volumes with {entity_name} given current performance"},
            "expected_benefit": {"fr": "Tire parti d'un fournisseur actuellement performant.", "en": "Makes the most of a supplier that is performing well."},
            "trade_offs": {"fr": "Augmente la dépendance à ce fournisseur unique.", "en": "Increases dependence on this single supplier."},
        },
        {
            "label": {"fr": "Continuer à surveiller pour confirmer que l'amélioration se maintient", "en": "Keep monitoring to confirm the improvement holds"},
            "expected_benefit": {"fr": "Évite de trop s'engager sur une tendance qui pourrait ne pas durer.", "en": "Avoids over-committing to a trend that may not last."},
            "trade_offs": {"fr": "Retarde la capture du bénéfice si l'amélioration est réelle et durable.", "en": "Delays capturing the benefit if the improvement is real and lasting."},
        },
    ],
    "finance": [
        {
            "label": {"fr": "Identifier ce qui explique l'amélioration pour le reproduire ailleurs", "en": "Identify what explains the improvement to replicate it elsewhere"},
            "expected_benefit": {"fr": "Transforme une amélioration ponctuelle en pratique reproductible.", "en": "Turns a one-off improvement into a repeatable practice."},
            "trade_offs": {"fr": "Demande du temps d'analyse avant tout déploiement plus large.", "en": "Takes analysis time before any wider rollout."},
        },
        {
            "label": {"fr": "Renforcer l'approche actuelle de prix ou de coûts", "en": "Reinforce the current pricing or cost approach"},
            "expected_benefit": {"fr": "Protège le gain avec un effort supplémentaire minimal.", "en": "Protects the gain with minimal extra effort."},
            "trade_offs": {"fr": "Passif ; ne capture pas activement de valeur supplémentaire.", "en": "Passive; does not actively capture extra value."},
        },
        {
            "label": {"fr": "Surveiller la durabilité avant de réallouer des ressources", "en": "Monitor durability before reallocating resources"},
            "expected_benefit": {"fr": "Évite de réallouer l'effort sur une tendance qui pourrait ne pas se confirmer.", "en": "Avoids reallocating effort to a trend that may not be confirmed."},
            "trade_offs": {"fr": "Retarde l'action sur l'opportunité si elle se confirme réelle.", "en": "Delays acting on the opportunity if it proves real."},
        },
    ],
}


@dataclass(frozen=True)
class DecisionOption:
    label: str
    expected_benefit: str
    trade_offs: str


@dataclass(frozen=True)
class DecisionRecommendation:
    chosen_option: str | None
    reasoning: str


@dataclass(frozen=True)
class Decision:
    problem: str
    type: str  # "risk" | "opportunity" | "insight" | "observation" -- inherited from the Interpretation, never re-derived
    options: list[DecisionOption]
    potential_impact: str
    confidence: str
    recommendation: DecisionRecommendation
    data_used: list[dict]
    capabilities_consulted: list[str]
    domain: str
    entity_type: RelatedEntityType
    entity_id: uuid.UUID
    entity_name: str
    source_interpretation_event_id: uuid.UUID
    # {"fr": {problem, options, recommendation}, "en": {...}} (brain/decisions.md #58)
    i18n: dict | None = None


def _texts(decision_type: str, problem: str, options: list[DecisionOption], recommendation: DecisionRecommendation) -> dict:
    return {
        "problem": problem,
        "options": [{"label": o.label, "expected_benefit": o.expected_benefit, "trade_offs": o.trade_offs} for o in options],
        "recommendation": {"chosen_option": recommendation.chosen_option, "reasoning": recommendation.reasoning},
    }


def _build_options(decision_type: str, domain: str, entity_name: str) -> list[DecisionOption]:
    if decision_type not in ("risk", "opportunity"):
        return []  # insight/observation: not confident enough to offer options at all

    catalog = _RISK_OPTIONS if decision_type == "risk" else _OPPORTUNITY_OPTIONS
    templates = catalog.get(domain, catalog["finance"])
    locale = current_locale()
    return [
        DecisionOption(
            label=t["label"][locale].format(entity_name=entity_name),
            expected_benefit=t["expected_benefit"][locale].format(entity_name=entity_name),
            trade_offs=t["trade_offs"][locale].format(entity_name=entity_name),
        )
        for t in templates
    ]


def _insufficient_reasoning(entity_name: str) -> str:
    return tx(
        f"Les données disponibles sur {entity_name} ne sont pas encore assez fiables pour "
        "recommander une action précise — la situation continue d'être surveillée.",
        f"The data available on {entity_name} is not yet reliable enough to recommend a "
        "specific action — the situation is still being monitored.",
    )


def _combined_reasoning(entity_name: str) -> str:
    return tx(
        f"Ces deux leviers combinent une action directe sur {entity_name} et une mesure de "
        "réduction du risque, sans attendre — l'option la plus prudente à ce stade.",
        f"These two levers combine direct action on {entity_name} with a risk-reducing "
        "measure, without waiting — the most prudent option at this stage.",
    )


def _build_recommendation(
    llm: LLMClient, context: dict, decision_type: str, options: list[DecisionOption], entity_name: str
) -> DecisionRecommendation:
    if decision_type not in ("risk", "opportunity") or not options:
        if isinstance(llm, DeterministicLLMClient):
            return DecisionRecommendation(chosen_option=None, reasoning=_insufficient_reasoning(entity_name))

        system_prompt = (
            "You are the Decision Intelligence assistant inside an AI Business OS. The data below "
            "was not confident enough to be classified as a Risk or an Opportunity. Explain briefly, "
            "strictly from the data, why there isn't enough reliable information yet to recommend a "
            "specific action -- never invent a fact, and never propose an action anyway. "
            + llm_language()
        )
        reasoning = llm.complete(
            system_prompt=system_prompt, user_prompt=f"Context:\n{json.dumps(context, indent=2, default=str)}"
        )
        return DecisionRecommendation(chosen_option=None, reasoning=reasoning)

    # Deterministic, auditable choice (see module docstring): combine the two
    # proactive options and skip the passive one -- never an LLM guess, for
    # the same reproducibility reason app.interpretation.engine.classify()
    # is deterministic rather than LLM-decided.
    chosen = f"{options[0].label} + {options[1].label}"

    if isinstance(llm, DeterministicLLMClient):
        return DecisionRecommendation(chosen_option=chosen, reasoning=_combined_reasoning(entity_name))

    system_prompt = (
        "You are the Decision Intelligence assistant inside an AI Business OS. Given the structured "
        "context and the numbered options below, explain in one or two sentences why the combined "
        f"option '{chosen}' is recommended -- strictly from the data, never inventing a fact. You are "
        "not deciding anything: a human will review this recommendation before any action is taken. "
        + llm_language()
    )
    options_text = "\n".join(
        f"{i + 1}. {o.label} (benefit: {o.expected_benefit}; trade-off: {o.trade_offs})"
        for i, o in enumerate(options)
    )
    user_prompt = f"Context:\n{json.dumps(context, indent=2, default=str)}\n\nOptions:\n{options_text}"
    reasoning = llm.complete(system_prompt=system_prompt, user_prompt=user_prompt)
    return DecisionRecommendation(chosen_option=chosen, reasoning=reasoning)


def build_decision(
    session: Session,
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    llm: LLMClient,
    company_id: uuid.UUID,
    interpretation_entry: EventLogEntry,
) -> Decision:
    """Builds one Decision from one EventInterpreted Event Log entry. Reuses
    the SAME context assembly the Interpretation itself used (Business Event
    + Significance + Business Context + Baseline + Snapshot + targeted
    capabilities), enriched with the Interpretation's own output, rather than
    reassembling a second, parallel context."""

    interp_payload = interpretation_entry.payload
    decision_type = interp_payload["type"]
    domain = interp_payload["domain"]
    entity_name = interp_payload["entity_name"]

    observation_entry = (
        session.query(EventLogEntry)
        .filter_by(event_type=OBSERVATION_DETECTED, event_id=uuid.UUID(interp_payload["source_observation_event_id"]))
        .one()
    )
    context, capabilities_consulted = assemble_context(
        session, event_bus, capability_registry, llm, company_id, observation_entry
    )
    context["interpretation"] = {
        "type": interp_payload["type"],
        "title": interp_payload["title"],
        "explanation": interp_payload["explanation"],
        "confidence": interp_payload["confidence"],
    }

    # Both interface languages, generated -- not translated -- in each one.
    interp_i18n = interp_payload.get("i18n") or {}

    def render() -> tuple[str, list[DecisionOption], DecisionRecommendation]:
        problem = (interp_i18n.get(current_locale()) or {}).get("title") or interp_payload["title"]
        options = _build_options(decision_type, domain, entity_name)
        return problem, options, _build_recommendation(llm, context, decision_type, options, entity_name)

    rendered = both(render)
    problem, options, recommendation = rendered["fr"]

    return Decision(
        problem=problem,
        type=decision_type,
        options=options,
        potential_impact=interp_payload["potential_impact"],
        confidence=interp_payload["confidence"],
        recommendation=recommendation,
        data_used=interp_payload["observations_used"],
        capabilities_consulted=capabilities_consulted,
        domain=domain,
        entity_type=RelatedEntityType(interp_payload["entity_type"]),
        entity_id=uuid.UUID(interp_payload["entity_id"]),
        entity_name=entity_name,
        source_interpretation_event_id=interpretation_entry.event_id,
        i18n={locale: _texts(decision_type, *parts) for locale, parts in rendered.items()},
    )


def _decision_payload(decision: Decision) -> dict:
    return {
        "problem": decision.problem,
        "type": decision.type,
        "options": [
            {"label": o.label, "expected_benefit": o.expected_benefit, "trade_offs": o.trade_offs}
            for o in decision.options
        ],
        "potential_impact": decision.potential_impact,
        "confidence": decision.confidence,
        "recommendation": {
            "chosen_option": decision.recommendation.chosen_option,
            "reasoning": decision.recommendation.reasoning,
        },
        "data_used": decision.data_used,
        "capabilities_consulted": decision.capabilities_consulted,
        "domain": decision.domain,
        "entity_type": decision.entity_type.value,
        "entity_id": str(decision.entity_id),
        "entity_name": decision.entity_name,
        "source_interpretation_event_id": str(decision.source_interpretation_event_id),
        "i18n": decision.i18n,
    }


def localize_decision(payload: dict) -> dict:
    """A DecisionProposed payload with its texts in the active language.
    One stored before both languages were kept is re-rendered from the
    option catalog only where its French text is exactly the catalog's (an
    LLM-written reasoning stays as it was written)."""

    from app.interpretation.engine import localize_interpretation

    out = dict(payload)
    entry = (payload.get("i18n") or {}).get(current_locale())
    if entry:
        out.update(entry)
        return out
    kind, domain, name = payload.get("type"), payload.get("domain"), payload.get("entity_name")
    observable = (payload.get("data_used") or [{}])[0].get("observable")
    title = localize_interpretation({"type": kind, "title": payload.get("problem"), "entity_name": name, "observable": observable, "domain": domain})
    out["problem"] = title["title"]
    with use_locale("fr"):
        fr_options = _build_options(kind, domain, name)
    if [o["label"] for o in payload.get("options", [])] == [o.label for o in fr_options]:
        options = _build_options(kind, domain, name)
        out["options"] = [{"label": o.label, "expected_benefit": o.expected_benefit, "trade_offs": o.trade_offs} for o in options]
        rec = dict(payload.get("recommendation") or {})
        if options and rec.get("chosen_option") == f"{fr_options[0].label} + {fr_options[1].label}":
            rec["chosen_option"] = f"{options[0].label} + {options[1].label}"
        with use_locale("fr"):
            fr_reasonings = {_combined_reasoning(name): _combined_reasoning, _insufficient_reasoning(name): _insufficient_reasoning}
        if rec.get("reasoning") in fr_reasonings:
            rec["reasoning"] = fr_reasonings[rec["reasoning"]](name)
        out["recommendation"] = rec
    return out


def _already_decided(session: Session, interpretation_event_id: uuid.UUID) -> bool:
    target = str(interpretation_event_id)
    return any(
        entry.payload.get("source_interpretation_event_id") == target
        for entry in session.query(EventLogEntry).filter_by(event_type=DECISION_PROPOSED).all()
    )


def _already_covered_by_existing_flow(session: Session, entity_id: uuid.UUID) -> bool:
    """True when an open Risk/Opportunity from the older per-metric rules
    already covers this entity. The Decision itself is still produced either
    way (it's additive, informational) -- only the side-effecting Action
    Proposal below is skipped, so this layer never proposes a second,
    duplicate Task for a phenomenon the existing flow already surfaced. Same
    guard, same reasoning app.interpretation.engine used for this before the
    responsibility moved here (see brain/decisions.md)."""

    has_risk = session.query(Risk).filter_by(related_entity_id=entity_id, status=RiskStatus.OPEN).first()
    has_opportunity = (
        session.query(Opportunity).filter_by(related_entity_id=entity_id, status=OpportunityStatus.OPEN).first()
    )
    return has_risk is not None or has_opportunity is not None


# Step 22 (external data): when the Interpretation this Decision is built
# from was itself triggered by an external-data Observable, approving the
# resulting Task should close the loop back through the SAME connector the
# signal came from, rather than the plain generic "create_task" -- a
# procurement-domain signal proposes a follow-up meeting (Mock Calendar), a
# sales-domain one proposes a follow-up reply (Mock Email). This is a
# domain-level policy, not a rule tied to any specific business scenario,
# and changes nothing for the three original, internal-metric Observables
# (margin_pct, delivery_delay_days, customer_revenue_variation_pct), which
# keep proposing a plain "create_task" exactly as before -- verified by
# every pre-existing Decision Intelligence test still passing unmodified.
_EXTERNAL_DATA_OBSERVABLES = {"supplier_unanswered_message_age_days", "customer_unanswered_message_age_days"}
_CONNECTOR_FOLLOWUP_BY_DOMAIN = {"procurement": "connector_followup_meeting", "sales": "connector_followup_email"}


def _pending_action_for(decision: Decision) -> str:
    primary_observable = decision.data_used[0].get("observable") if decision.data_used else None
    if primary_observable in _EXTERNAL_DATA_OBSERVABLES:
        return _CONNECTOR_FOLLOWUP_BY_DOMAIN.get(decision.domain, "create_task")
    return "create_task"


def _maybe_propose_action(
    session: Session, event_bus: EventBus, company_id: uuid.UUID, decision: Decision
) -> uuid.UUID | None:
    """Turns a Decision's recommendation into a real Task proposal through
    the EXISTING Human-in-the-Loop mechanism -- the same
    `ActionsService.propose_task` the `create_task` AI capability and the
    (now-removed) Interpretation-level proposal both used. The resulting
    Task is PENDING_VALIDATION only: nothing here executes anything; a human
    must still call the existing POST /actions/tasks/{id}/approve endpoint
    before ActionExecutor runs. A Decision with no chosen option (insight/
    observation, or genuinely insufficient context) never reaches here --
    "une Recommendation peut exister sans qu'une Action soit proposée"."""

    if decision.recommendation.chosen_option is None:
        return None
    if _already_covered_by_existing_flow(session, decision.entity_id):
        return None

    def task_text(locale: str) -> dict:
        texts = (decision.i18n or {}).get(locale) or _texts(decision.type, decision.problem, decision.options, decision.recommendation)
        rec = texts["recommendation"]
        label = "Recommandation" if locale == "fr" else "Recommended"
        sep = " :" if locale == "fr" else ":"
        return {"title": texts["problem"], "description": f"{label}{sep} {rec['chosen_option']}\n\n{rec['reasoning']}"}

    texts = {locale: task_text(locale) for locale in ("fr", "en")}
    task = ActionsService(session, event_bus).propose_task(
        company_id=company_id,
        title=texts["fr"]["title"],
        description=texts["fr"]["description"],
        i18n=texts,
        related_entity_type=decision.entity_type,
        related_entity_id=decision.entity_id,
        correlation_id=decision.source_interpretation_event_id,
        agent="decision_engine",
        pending_action=_pending_action_for(decision),
    )
    return task.id


def run_decision_sweep(
    session: Session,
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    llm: LLMClient,
    company_id: uuid.UUID,
) -> dict:
    """The one entry point a manual trigger (or, later, a scheduler) calls:
    builds a Decision for every EventInterpreted Business Event for this
    company that doesn't have one yet, and proposes a human-validated Task
    for the confidently-recommended ones not already covered by an existing
    Risk/Opportunity. Safe to call repeatedly: an already-decided
    Interpretation is skipped."""

    decided = 0
    proposed = 0
    by_type: dict[str, int] = {"risk": 0, "opportunity": 0, "insight": 0, "observation": 0}

    entries = session.query(EventLogEntry).filter_by(event_type=EVENT_INTERPRETED).all()
    for entry in entries:
        if _already_decided(session, entry.event_id):
            continue

        supplier, product, customer = _resolve_entity_by_ref(
            session, entry.payload.get("entity_type"), entry.payload.get("entity_id")
        )
        entity = supplier or product or customer
        if entity is None or entity.company_id != company_id:
            continue

        decision = build_decision(session, event_bus, capability_registry, llm, company_id, entry)
        event_bus.publish(
            BusinessEvent(
                event_type=DECISION_PROPOSED,
                source="decision_engine",
                payload=_decision_payload(decision),
            )
        )
        decided += 1
        by_type[decision.type] += 1

        if _maybe_propose_action(session, event_bus, company_id, decision) is not None:
            proposed += 1

    return {
        "decisions_made": decided,
        "actions_proposed": proposed,
        "by_type": by_type,
    }
