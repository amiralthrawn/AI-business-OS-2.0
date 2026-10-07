import uuid

from sqlalchemy.orm import Session

from app.core.entities import (
    Communication,
    Customer,
    EventLogEntry,
    Opportunity,
    OpportunityStatus,
    Product,
    RelatedEntityType,
    Risk,
    RiskSeverity,
    RiskStatus,
    Supplier,
    Task,
    TaskStatus,
    Transaction,
)
from app.core.i18n import text_of, tx
from app.core.observable_labels import observable_label

DEFAULT_RECENT_LIMIT = 5
DEFAULT_RECENT_EVENTS_LIMIT = 10
DEFAULT_PRIORITIES_LIMIT = 10
DEFAULT_DECISIONS_LIMIT = 10
DEFAULT_ACTIVITY_LIMIT = 30
DEFAULT_ACTIVITY_SCAN_WINDOW = 300  # how many raw EventLogEntry rows to scan for DEFAULT_ACTIVITY_LIMIT describable ones
DEFAULT_NARRATIVE_LIMIT = 10

# Business-language labels for the "Activité de l'OS" feed (Step 27) -- only
# the newer, generic Observation/Interpretation/Decision/Actions event types
# are narrated here (never the older per-metric monitoring sweep's
# RiskCreated/OpportunityCreated/etc., which describe the exact same
# phenomena a second time; see brain/decisions.md #19). Never shows a raw
# event_type or payload to a caller -- every entry is translated to a short
# sentence in the active language, honestly distinguishing "the OS analyzed/proposed
# something" from "a human actually approved/rejected it" (see brain's Step
# 27 notes) -- nothing here claims an external action (an email sent, a
# meeting confirmed) that was not actually executed.
_ACTIVITY_LABELS = {
    "ObservationDetected": ("Analyse effectuée", "Analysis performed"),
    "EventInterpreted": ("Analyse approfondie effectuée", "In-depth analysis performed"),
    "DecisionProposed": ("Recommandation générée", "Recommendation generated"),
    "TaskCreated": ("Tâche proposée", "Task proposed"),
    "ActionApproved": ("Action validée", "Action approved"),
    "ActionRejected": ("Action rejetée", "Action rejected"),
    "ActionExecuted": ("Action exécutée", "Action executed"),
}
_NARRATIVE_ENTITY_MODELS = {
    RelatedEntityType.SUPPLIER: Supplier,
    RelatedEntityType.CUSTOMER: Customer,
    RelatedEntityType.PRODUCT: Product,
}

_SEVERITY_RANK = {
    RiskSeverity.CRITICAL: 4,
    RiskSeverity.HIGH: 3,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 1,
}
_OPPORTUNITY_RANK = 2  # ranks alongside a medium-severity risk


class HomeService:
    """Builds the Command Center view by reading directly from the Data Core,
    Intelligence, Observation/Interpretation/Decision Event Log entries and
    Actions tables at request time. Owns no data of its own -- every number
    here is computed on the fly or re-hydrated from an existing source,
    nothing is cached, recomputed or duplicated (see brain/home_command_center.md).

    `get_priorities` is deliberately reused as-is by the AI `list_priorities`
    capability (see app.ai.capabilities.list_priorities): "what deserves
    attention" must mean the same thing whether a human opens Home or asks the
    AI, so the ranking logic lives here once. `get_ai_priorities` is a newer,
    separate method for the Command Center's own "AI Priorities" section --
    it re-exposes the Business State Snapshot's own `material_areas`
    (Baseline/Significance/Interpretation/Decision, already computed) rather
    than re-deriving a second ranking, so the two intentionally return
    different shapes for different consumers rather than one trying to serve
    both jobs.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_overview(self) -> dict:
        return {
            "supplier_count": self.session.query(Supplier).count(),
            "product_count": self.session.query(Product).count(),
            "customer_count": self.session.query(Customer).count(),
            "transaction_count": self.session.query(Transaction).count(),
        }

    def get_risks_summary(self, recent_limit: int = DEFAULT_RECENT_LIMIT) -> dict:
        return {
            "total_risks": self.session.query(Risk).filter_by(status=RiskStatus.OPEN).count(),
            "high_risks": (
                self.session.query(Risk)
                .filter(Risk.status == RiskStatus.OPEN, Risk.severity.in_([RiskSeverity.HIGH, RiskSeverity.CRITICAL]))
                .count()
            ),
            "recent_risks": (
                self.session.query(Risk).order_by(Risk.created_at.desc()).limit(recent_limit).all()
            ),
        }

    def get_opportunities_summary(self, recent_limit: int = DEFAULT_RECENT_LIMIT) -> dict:
        return {
            "total_opportunities": self.session.query(Opportunity).filter_by(status=OpportunityStatus.OPEN).count(),
            "recent_opportunities": (
                self.session.query(Opportunity).order_by(Opportunity.created_at.desc()).limit(recent_limit).all()
            ),
        }

    def get_tasks_summary(self, recent_limit: int = DEFAULT_RECENT_LIMIT) -> dict:
        return {
            "total_tasks": self.session.query(Task).count(),
            "pending_validation_tasks": (
                self.session.query(Task).filter_by(status=TaskStatus.PENDING_VALIDATION).count()
            ),
            "recent_tasks": (
                self.session.query(Task).order_by(Task.created_at.desc()).limit(recent_limit).all()
            ),
        }

    def get_recent_events(self, limit: int = DEFAULT_RECENT_EVENTS_LIMIT) -> list[EventLogEntry]:
        return list(
            self.session.query(EventLogEntry).order_by(EventLogEntry.occurred_at.desc()).limit(limit).all()
        )

    def get_priorities(self, limit: int = DEFAULT_PRIORITIES_LIMIT) -> list[dict]:
        """Open Risks and Opportunities merged into a single ranked feed --
        this is "AI Priorities": the answer to "what needs my attention now?"
        Ranked by severity/impact first, then recency. Pending Tasks are
        surfaced separately (see get_tasks_summary) since they represent a
        distinct kind of attention -- an approval decision, not a finding."""

        items: list[dict] = []

        for risk in self.session.query(Risk).filter_by(status=RiskStatus.OPEN).all():
            items.append(
                {
                    "kind": "risk",
                    "id": risk.id,
                    "title": text_of(risk, "title"),
                    "description": text_of(risk, "description"),
                    "severity": risk.severity.value,
                    "related_entity_type": risk.related_entity_type,
                    "related_entity_id": risk.related_entity_id,
                    "created_at": risk.created_at,
                    "_rank": _SEVERITY_RANK.get(risk.severity, 0),
                }
            )

        for opportunity in self.session.query(Opportunity).filter_by(status=OpportunityStatus.OPEN).all():
            items.append(
                {
                    "kind": "opportunity",
                    "id": opportunity.id,
                    "title": text_of(opportunity, "title"),
                    "description": text_of(opportunity, "description"),
                    "severity": None,
                    "related_entity_type": opportunity.related_entity_type,
                    "related_entity_id": opportunity.related_entity_id,
                    "created_at": opportunity.created_at,
                    "_rank": _OPPORTUNITY_RANK,
                }
            )

        items.sort(key=lambda item: (item["_rank"], item["created_at"]), reverse=True)
        for item in items:
            del item["_rank"]
        return items[:limit]

    def get_ai_priorities(self, company_id: uuid.UUID, limit: int = DEFAULT_PRIORITIES_LIMIT) -> list[dict]:
        """"AI Priorities": the Command Center's answer to "what deserves my
        attention now?", built by re-exposing the Business State Snapshot's
        own `material_areas` -- risk / opportunity / decision / observation
        areas, each already carrying real Significance (impact, urgency,
        confidence) and, for decision/observation kinds, the Interpretation/
        Decision Engines' own explanation, recommendation and options.

        Home never recomputes any of this: `build_snapshot` already did the
        work (see app.snapshot.service), so this method only re-hydrates its
        output into a Home-shaped dict and attaches a link back to an
        existing detail page for the risk/opportunity kinds that have one.
        """

        # Local import: app.snapshot.service itself imports HomeService (to
        # reuse get_risks_summary/get_opportunities_summary/get_tasks_summary
        # for its own open-Risk/Opportunity counts), so importing it back at
        # module load time here would be a circular import. Deferred to call
        # time, after both modules are already fully loaded, same fix used
        # for get_decisions below.
        from app.snapshot.service import build_snapshot

        snapshot = build_snapshot(self.session, company_id)

        # A risk/opportunity-kind area has no Risk/Opportunity row id of its
        # own (SnapshotArea only carries the *related* entity, e.g. a
        # Product or Supplier) -- these lookups let Home link back to the
        # existing detail page without adding a new field to SnapshotArea
        # itself, by matching on the same (entity_type, entity_id) pair the
        # detection rules already used to create that Risk/Opportunity.
        risk_ids_by_entity = {
            (r.related_entity_type, r.related_entity_id): r.id
            for r in self.session.query(Risk).filter_by(status=RiskStatus.OPEN).all()
            if r.related_entity_id is not None
        }
        opportunity_ids_by_entity = {
            (o.related_entity_type, o.related_entity_id): o.id
            for o in self.session.query(Opportunity).filter_by(status=OpportunityStatus.OPEN).all()
            if o.related_entity_id is not None
        }

        items: list[dict] = []
        for area in snapshot.material_areas[:limit]:
            detail_kind: str | None = None
            detail_id: uuid.UUID | None = None
            if area.kind == "risk":
                detail_id = risk_ids_by_entity.get((area.entity_type, area.entity_id))
                detail_kind = "risk" if detail_id else None
            elif area.kind == "opportunity":
                detail_id = opportunity_ids_by_entity.get((area.entity_type, area.entity_id))
                detail_kind = "opportunity" if detail_id else None

            items.append(
                {
                    "kind": area.kind,
                    "interpretation_type": area.interpretation_type,
                    "domain": area.domain,
                    "title": area.title,
                    "entity_type": area.entity_type,
                    "entity_id": area.entity_id,
                    "impact": area.significance.impact,
                    "urgency": area.significance.urgency,
                    "confidence": area.significance.confidence,
                    "explanation": area.explanation,
                    "recommendation": area.recommendation,
                    "decision_options": area.decision_options,
                    "detail_kind": detail_kind,
                    "detail_id": detail_id,
                }
            )
        return items

    def get_decisions(self, limit: int = DEFAULT_DECISIONS_LIMIT) -> list[dict]:
        """Decisions potentially requiring human attention -- re-hydrated
        directly from the Event Log's `DecisionProposed` entries
        (app.decision), most recent first. No recomputation: options,
        recommendation and confidence are exactly what the Decision
        Intelligence Engine already produced."""

        # Local import for the same circular-import reason as build_snapshot
        # above: app.decision.engine's own context assembly transitively
        # imports app.snapshot.service, which imports HomeService.
        from app.decision.engine import DECISION_PROPOSED, localize_decision

        entries = (
            self.session.query(EventLogEntry)
            .filter_by(event_type=DECISION_PROPOSED)
            .order_by(EventLogEntry.occurred_at.desc())
            .limit(limit)
            .all()
        )
        payloads = [(entry, localize_decision(entry.payload)) for entry in entries]
        return [
            {
                "type": payload.get("type"),
                "problem": payload.get("problem"),
                "domain": payload.get("domain"),
                "entity_type": payload.get("entity_type"),
                "entity_id": payload.get("entity_id"),
                "options": payload.get("options", []),
                "recommendation": payload.get("recommendation"),
                "confidence": payload.get("confidence"),
                "occurred_at": entry.occurred_at,
            }
            for entry, payload in payloads
        ]

    def _describe_activity_entry(self, entry: EventLogEntry) -> tuple[str | None, str] | None:
        """Returns (domain, detail) in business language for one Event Log
        entry, or `None` when it isn't one of the event types this feed
        narrates (see `_ACTIVITY_LABELS`) or its Task no longer resolves."""

        payload = entry.payload

        if entry.event_type == "ObservationDetected":
            label = observable_label(payload.get("observable"))
            entity_name = payload.get("entity_name") or ""
            return payload.get("domain"), f"{label} — {entity_name}".strip(" —")

        if entry.event_type == "EventInterpreted":
            from app.interpretation.engine import localize_interpretation

            return payload.get("domain"), localize_interpretation(payload).get("title") or ""

        if entry.event_type == "DecisionProposed":
            from app.decision.engine import localize_decision

            return payload.get("domain"), localize_decision(payload).get("problem") or ""

        if entry.event_type in ("TaskCreated", "ActionApproved", "ActionRejected", "ActionExecuted"):
            task_id = payload.get("task_id")
            task = self.session.get(Task, uuid.UUID(task_id)) if task_id else None
            if task is None:
                return None
            return None, text_of(task, "title")

        return None

    def get_os_activity(self, limit: int = DEFAULT_ACTIVITY_LIMIT, domain: str | None = None) -> list[dict]:
        """"What has the OS actually done recently?" -- re-hydrated from the
        real Event Log, most recent first, each entry translated into a
        short business sentence in the active language (never a raw event_type or payload).
        `domain` filters to entries that resolved one (finance/procurement/
        sales); entries with no resolvable domain (Task/Action events) are
        only included when no filter is active."""

        entries = (
            self.session.query(EventLogEntry)
            .order_by(EventLogEntry.occurred_at.desc())
            .limit(DEFAULT_ACTIVITY_SCAN_WINDOW)
            .all()
        )

        items: list[dict] = []
        for entry in entries:
            described = self._describe_activity_entry(entry)
            if described is None:
                continue
            entry_domain, detail = described
            if domain and entry_domain != domain:
                continue

            items.append(
                {
                    "event_type": entry.event_type,
                    "domain": entry_domain,
                    "label": tx(*_ACTIVITY_LABELS[entry.event_type]),
                    "detail": detail,
                    "occurred_at": entry.occurred_at,
                }
            )
            if len(items) >= limit:
                break
        return items

    def get_company_narrative(self, company_id: uuid.UUID, limit: int = DEFAULT_NARRATIVE_LIMIT) -> list[dict]:
        """The company's own real communications (emails, internal notes),
        most recent first -- the raw material for "what actually happened"
        and "what the company proposes", shown close to as-is rather than
        run through any Intelligence rule (there isn't one for Marketing/HR
        content). Each item is honestly what it is: a real Communication
        row, never something the AI "detected".

        Deliberately excludes `channel="calendar"` (a future-dated meeting
        is not "what happened", it's an upcoming appointment -- a distinct
        concept, see brain's Step 27 notes) and `channel="website"` (raw
        inbound inquiries, already surfaced through the Sales domain's own
        signals; too frequent and unfiltered to belong in a curated
        narrative feed). Only messages that really happened: a draft (or one
        awaiting validation, or rejected) was never sent, so its body -- often
        a template with placeholders -- is not part of the company's story.
        The subject and body are source data, returned untranslated; the
        interface frames them in its own language."""

        comms = (
            self.session.query(Communication)
            .filter_by(company_id=company_id)
            .filter(Communication.channel.in_(("email", "internal")))
            .filter(Communication.status.in_(("received", "sent")))
            .order_by(Communication.occurred_at.desc())
            .limit(limit)
            .all()
        )

        items: list[dict] = []
        for c in comms:
            entity_name = None
            if c.related_entity_type in _NARRATIVE_ENTITY_MODELS and c.related_entity_id is not None:
                entity = self.session.get(_NARRATIVE_ENTITY_MODELS[c.related_entity_type], c.related_entity_id)
                entity_name = entity.name if entity is not None else None

            items.append(
                {
                    "id": c.id,
                    "channel": c.channel,
                    "channel_detail": c.channel_detail,
                    "direction": c.direction.value,
                    "subject": c.subject,
                    "body": c.body,
                    "occurred_at": c.occurred_at,
                    "related_entity_type": c.related_entity_type,
                    "related_entity_name": entity_name,
                }
            )
        return items

    def get_command_center(self, company_id: uuid.UUID | None = None) -> dict:
        """The single Command Center read model Home's `GET /home` endpoint
        serves. `company_id` is `None` only on a brand-new, unseeded install
        (no Company yet) -- an explicit empty/"insufficient context" state
        for `priorities`, never a guess."""

        return {
            "overview": self.get_overview(),
            "priorities": self.get_ai_priorities(company_id) if company_id is not None else [],
            "risks": self.get_risks_summary(),
            "opportunities": self.get_opportunities_summary(),
            "decisions": self.get_decisions(),
            "tasks": self.get_tasks_summary(),
            "recent_events": self.get_recent_events(),
            "os_activity": self.get_os_activity(limit=6),
            "company_narrative": self.get_company_narrative(company_id, limit=6) if company_id is not None else [],
        }
