import uuid

from sqlalchemy.orm import Session

from app.core.i18n import both, money, pct, tx
from app.intelligence.risks.kinds import GROWING_CUSTOMER
from app.core.analytics import compute_customer_value_trend
from app.core.entities import Customer, Opportunity, OpportunityStatus, RelatedEntityType
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent

OPPORTUNITY_CREATED = "OpportunityCreated"
CUSTOMER_GROWTH_DETECTED = "CustomerGrowthDetected"


class OpportunityDetectionService:
    """Applies deterministic Intelligence rules to detect Opportunities from
    real Data Core trends. Mirrors RiskDetectionService's shape deliberately:
    same idempotence approach, same event-then-record pattern."""

    def __init__(self, session: Session, event_bus: EventBus) -> None:
        self.session = session
        self.event_bus = event_bus

    def evaluate_customer_growth(self, customer_id: uuid.UUID) -> Opportunity | None:
        customer = self.session.get(Customer, customer_id)
        if customer is None:
            return None

        trend = compute_customer_value_trend(self.session, customer_id)
        if trend.trend != "growing":
            return None

        already_open = (
            self.session.query(Opportunity)
            .filter(
                Opportunity.related_entity_type == RelatedEntityType.CUSTOMER,
                Opportunity.related_entity_id == customer_id,
                Opportunity.status == OpportunityStatus.OPEN,
            )
            .first()
        )
        if already_open is not None:
            return None

        signal_event = BusinessEvent(
            event_type=CUSTOMER_GROWTH_DETECTED,
            source="intelligence",
            payload={
                "customer_id": str(customer_id),
                "baseline_revenue": trend.baseline_revenue,
                "recent_revenue": trend.recent_revenue,
                "variation_pct": trend.variation_pct,
            },
        )
        self.event_bus.publish(signal_event)

        texts = both(
            lambda: {
                "title": GROWING_CUSTOMER.title(customer.name),
                "description": tx(
                    f"Le chiffre d'affaires de {customer.name} a augmenté de {pct(trend.variation_pct)} "
                    f"(de {money(trend.baseline_revenue, 0)} à {money(trend.recent_revenue, 0)}). "
                    "Piste : développer cette relation.",
                    f"Revenue from {customer.name} grew by {pct(trend.variation_pct)} "
                    f"(from {money(trend.baseline_revenue, 0)} to {money(trend.recent_revenue, 0)}). "
                    "Lead: develop this relationship.",
                ),
            }
        )
        opportunity = Opportunity(
            company_id=customer.company_id,
            title=texts["fr"]["title"],
            description=texts["fr"]["description"],
            i18n=texts,
            status=OpportunityStatus.OPEN,
            related_entity_type=RelatedEntityType.CUSTOMER,
            related_entity_id=customer_id,
            source_event_id=signal_event.event_id,
        )
        self.session.add(opportunity)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=OPPORTUNITY_CREATED,
                source="intelligence",
                correlation_id=signal_event.correlation_id,
                payload={
                    "opportunity_id": str(opportunity.id),
                    "source_event_id": str(signal_event.event_id),
                    "customer_id": str(customer_id),
                },
            )
        )
        return opportunity
