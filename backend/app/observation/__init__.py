"""Observable Registry + Observation Engine: discovers business phenomena
from the Data Core generically -- one Observable per measurable signal,
reusing app.core.baseline's existing functions -- rather than one hardcoded
rule per event type. See brain/observation_engine.md.

Step 22 (brain/external_data_intelligence.md) adds two Observables reading
Communication rows the External Connectivity Layer (app.connectors)
ingests -- still generic, measurable signals (age in days of an unanswered
message), never a per-business-scenario rule.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.analytics import compute_unanswered_message_age
from app.core.baseline import (
    customer_quote_pending_baseline,
    customer_unanswered_message_baseline,
    customer_value_baseline,
    margin_baseline,
    supplier_delivery_baseline,
    supplier_unanswered_message_baseline,
)
from app.core.entities import RelatedEntityType
from app.observation.registry import Observable, ObservableRegistry


def _supplier_unanswered_extra(session: Session, supplier_id: uuid.UUID) -> dict:
    result = compute_unanswered_message_age(session, RelatedEntityType.SUPPLIER, supplier_id)
    if result.communication_id is None:
        return {}
    return {
        "communication_id": str(result.communication_id),
        "message_subject": result.subject,
        "message_excerpt": (result.body or "")[:280],
        "message_occurred_at": result.occurred_at.isoformat() if result.occurred_at else None,
    }


def _customer_unanswered_extra(session: Session, customer_id: uuid.UUID) -> dict:
    result = compute_unanswered_message_age(session, RelatedEntityType.CUSTOMER, customer_id)
    if result.communication_id is None:
        return {}
    return {
        "communication_id": str(result.communication_id),
        "message_subject": result.subject,
        "message_excerpt": (result.body or "")[:280],
        "message_occurred_at": result.occurred_at.isoformat() if result.occurred_at else None,
    }


def _customer_quote_extra(session: Session, customer_id: uuid.UUID) -> dict:
    from app.core.analytics import compute_pending_quote_age

    result = compute_pending_quote_age(session, customer_id)
    if result.document_id is None:
        return {}
    return {"document_id": str(result.document_id), "document_number": result.number, "pending_quotes": result.sample_size}


def build_observable_registry() -> ObservableRegistry:
    """Exposed as a function (rather than only the singleton below) so tests
    can build an isolated registry instead of depending on shared global
    state -- the same reasoning as app.ai.capabilities.build_capability_registry."""

    registry = ObservableRegistry()
    registry.register(
        Observable(
            name="margin_pct",
            domain="finance",
            entity_type=RelatedEntityType.PRODUCT,
            description="Gross margin trend for a product, from purchase and sales Transactions.",
            compute=margin_baseline,
            impact_thresholds=(0.05, 0.10),
        )
    )
    registry.register(
        Observable(
            name="delivery_delay_days",
            domain="procurement",
            entity_type=RelatedEntityType.SUPPLIER,
            description="Supplier delivery performance trend (promise vs. actual delivery dates).",
            compute=supplier_delivery_baseline,
            impact_thresholds=(1.5, 3.0),
        )
    )
    registry.register(
        Observable(
            name="customer_revenue_variation_pct",
            domain="sales",
            entity_type=RelatedEntityType.CUSTOMER,
            description="Customer revenue trend from sales Transactions.",
            compute=customer_value_baseline,
            impact_thresholds=(0.15, 0.35),
        )
    )
    # Step 22: External Data Intelligence -- reads Communication rows the
    # Connector Layer (app.connectors) ingests, via the exact same
    # Observable/Baseline/Significance machinery as the three metrics above.
    registry.register(
        Observable(
            name="supplier_unanswered_message_age_days",
            domain="procurement",
            entity_type=RelatedEntityType.SUPPLIER,
            description="Age in days of the oldest still-unanswered inbound Communication linked to this supplier.",
            compute=supplier_unanswered_message_baseline,
            impact_thresholds=(2.0, 5.0),
            extra_context=_supplier_unanswered_extra,
        )
    )
    registry.register(
        Observable(
            name="customer_unanswered_message_age_days",
            domain="sales",
            entity_type=RelatedEntityType.CUSTOMER,
            description="Age in days of the oldest still-unanswered inbound Communication linked to this customer.",
            compute=customer_unanswered_message_baseline,
            impact_thresholds=(2.0, 5.0),
            extra_context=_customer_unanswered_extra,
        )
    )
    # V2: the first Observable fed by business objects (a sent quote still
    # awaiting the customer) -- same Baseline/Significance machinery, no new engine.
    registry.register(
        Observable(
            name="customer_quote_pending_age_days",
            domain="sales",
            entity_type=RelatedEntityType.CUSTOMER,
            description="Age in days of the oldest quote sent to this customer and still awaiting an answer.",
            compute=customer_quote_pending_baseline,
            impact_thresholds=(3.0, 10.0),
            extra_context=_customer_quote_extra,
        )
    )
    return registry


observable_registry = build_observable_registry()

__all__ = ["Observable", "ObservableRegistry", "build_observable_registry", "observable_registry"]
