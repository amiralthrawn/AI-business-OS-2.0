import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.entities import BusinessContext, EventLogEntry

DEFAULT_MONITORED_DOMAINS = ["procurement", "finance", "sales"]
DEFAULT_HOME_FOCUS = ["priorities", "risks", "opportunities"]
DEFAULT_NOTIFICATION_LEVEL = "normal"

# How many approvals/rejections in a row are needed before suggesting a
# notification_level change. Deliberately low for the MVP's small demo
# dataset; a real deployment would want a much larger, time-boxed sample
# before trusting a pattern (see brain/business_state.md).
_SUGGESTION_STREAK_THRESHOLD = 2


@dataclass(frozen=True)
class ConfigurationSuggestion:
    """A proposed configuration change the OS noticed from human behavior. It
    is only ever a suggestion: nothing reads this and applies it
    automatically -- a human must call BusinessContextService.update() (via
    PATCH /business-context) themselves."""

    field: str
    current_value: object
    suggested_value: object
    reason: str
    evidence_count: int


class BusinessContextService:
    """Reads and writes the company's Business Context -- the configuration
    layer that lets the rest of the system reason about THIS business rather
    than a generic one. See brain/business_context.md for the concept and
    what is deliberately deferred (baselines learned from history live in
    app.core.baseline, not here; sector defaults; automatic changes)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self, company_id: uuid.UUID) -> BusinessContext:
        context = self.session.query(BusinessContext).filter_by(company_id=company_id).first()
        if context is not None:
            return context

        context = BusinessContext(
            company_id=company_id,
            monitored_domains=list(DEFAULT_MONITORED_DOMAINS),
            home_focus=list(DEFAULT_HOME_FOCUS),
            notification_level=DEFAULT_NOTIFICATION_LEVEL,
            declared_baselines={},
            learned_notes=[],
        )
        self.session.add(context)
        self.session.commit()
        return context

    def update(
        self,
        company_id: uuid.UUID,
        *,
        company_size: str | None = None,
        country: str | None = None,
        business_model: str | None = None,
        monitored_domains: list[str] | None = None,
        home_focus: list[str] | None = None,
        notification_level: str | None = None,
        stated_objectives: str | None = None,
        declared_baselines: dict[str, float] | None = None,
    ) -> BusinessContext:
        context = self.get_or_create(company_id)
        for field, value in {
            "company_size": company_size,
            "country": country,
            "business_model": business_model,
            "monitored_domains": monitored_domains,
            "home_focus": home_focus,
            "notification_level": notification_level,
            "stated_objectives": stated_objectives,
            "declared_baselines": declared_baselines,
        }.items():
            if value is not None:
                setattr(context, field, value)

        self.session.add(context)
        self.session.commit()
        return context

    def add_learned_note(self, company_id: uuid.UUID, note: str) -> BusinessContext:
        """Appends a short factual observation. This is a log entry the
        system writes for itself over time (e.g. from suggest_configuration_
        changes below), never a rewrite of an existing preference."""

        context = self.get_or_create(company_id)
        context.learned_notes = [*context.learned_notes, note]
        self.session.add(context)
        self.session.commit()
        return context

    def suggest_configuration_changes(self, company_id: uuid.UUID) -> list[ConfigurationSuggestion]:
        """Looks at real human decisions recorded in the Event Log
        (ActionApproved / ActionRejected) and proposes a configuration change
        when a clear pattern shows up -- it never applies anything itself.
        This is the MVP's whole "human feedback enriches Business Context"
        mechanism: a simple, explainable streak count, not a learning model.
        """

        context = self.get_or_create(company_id)
        approved = self.session.query(EventLogEntry).filter_by(event_type="ActionApproved").count()
        rejected = self.session.query(EventLogEntry).filter_by(event_type="ActionRejected").count()

        suggestions: list[ConfigurationSuggestion] = []

        if approved >= _SUGGESTION_STREAK_THRESHOLD and rejected == 0 and context.notification_level != "high":
            suggestions.append(
                ConfigurationSuggestion(
                    field="notification_level",
                    current_value=context.notification_level,
                    suggested_value="high",
                    reason=tx(f"Vous avez approuvé chacune des {approved} dernières actions proposées : "
                    "l'OS pourrait vous en proposer davantage de lui-même.", f"You approved each of the last {approved} proposed actions: "
                    "the OS could propose more of them on its own."),
                    evidence_count=approved,
                )
            )
        elif rejected >= _SUGGESTION_STREAK_THRESHOLD and approved == 0 and context.notification_level != "low":
            suggestions.append(
                ConfigurationSuggestion(
                    field="notification_level",
                    current_value=context.notification_level,
                    suggested_value="low",
                    reason=tx(f"Vous avez rejeté chacune des {rejected} dernières actions proposées : "
                    "l'OS pourrait proposer ce type d'action moins souvent.", f"You rejected each of the last {rejected} proposed actions: "
                    "the OS could propose this type of action less often."),
                    evidence_count=rejected,
                )
            )

        return suggestions
