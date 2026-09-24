"""Formalizes what "normal" means for a metric.

app.core.analytics answers "what happened" (the raw before/after numbers).
Baseline answers a different question: "how much should we trust that as
'normal', and does the company have its own declared target we should compare
against instead of, or alongside, what's merely been observed?"

Baseline observed from history is never the same thing as a target the
company declared for itself (see brain/business_state.md) -- conflating the
two would let a company's aspirational target quietly become "what's normal",
or let a rough early trend get treated as a confirmed target. Both are kept
as separate fields on every Baseline, and `reference_value` documents the
one precedence rule used to pick between them.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.analytics import (
    compute_customer_value_trend,
    compute_margin_trend,
    compute_supplier_delivery_performance,
    compute_unanswered_message_age,
)
from app.core.entities import BusinessContext, RelatedEntityType

BaselineSource = Literal["observed_history", "declared", "generic_fallback"]
BaselineConfidence = Literal["insufficient", "low", "medium", "high"]

# Generic, industry-agnostic rules of thumb used only when there is neither
# enough observed history nor a company-declared target. These are not a
# substitute for a real sector-benchmark dataset (deliberately deferred, see
# brain/business_state.md) -- they exist so the system can say *something*
# about a brand-new entity rather than nothing, while being explicit (via
# `source="generic_fallback"` and `confidence="low"`) that it is a guess.
GENERIC_BENCHMARKS: dict[str, float] = {
    "margin_pct": 0.25,
    "delivery_delay_days": 2.0,
    "customer_revenue_variation_pct": 0.0,
    "unanswered_message_age_days": 2.0,
    # V2: days a customer usually takes to answer a quote before a follow-up
    # is warranted -- a generic default, overridable via declared_baselines.
    "quote_response_days": 7.0,
}


def _confidence_for_sample_size(sample_size: int) -> BaselineConfidence:
    if sample_size <= 0:
        return "insufficient"
    if sample_size < 4:
        return "low"
    if sample_size < 8:
        return "medium"
    return "high"


@dataclass(frozen=True)
class Baseline:
    metric: str
    observed_value: float | None
    declared_value: float | None
    sample_size: int
    source: BaselineSource
    confidence: BaselineConfidence

    @property
    def reference_value(self) -> float | None:
        """What Significance should compare "current" against. A company's
        own declared target takes precedence over what has merely been
        observed, which in turn takes precedence over a generic rule of
        thumb -- the three are never averaged or treated as equally
        reliable."""

        if self.declared_value is not None:
            return self.declared_value
        if self.observed_value is not None:
            return self.observed_value
        return GENERIC_BENCHMARKS.get(self.metric)


def build_baseline(
    metric: str,
    *,
    observed_value: float | None,
    sample_size: int,
    declared_value: float | None = None,
) -> Baseline:
    """The one place that decides which source/confidence a Baseline gets, so
    that rule never has to be re-derived (or re-guessed) by each caller."""

    if declared_value is not None:
        # A human stated this explicitly; that is a different kind of
        # certainty than a statistical sample, but not a lesser one.
        source: BaselineSource = "declared"
        confidence: BaselineConfidence = "high"
    elif observed_value is not None and sample_size > 0:
        source = "observed_history"
        confidence = _confidence_for_sample_size(sample_size)
    else:
        source = "generic_fallback"
        confidence = "low" if metric in GENERIC_BENCHMARKS else "insufficient"

    return Baseline(
        metric=metric,
        observed_value=observed_value,
        declared_value=declared_value,
        sample_size=sample_size,
        source=source,
        confidence=confidence,
    )


def _declared(business_context: BusinessContext | None, metric: str) -> float | None:
    if business_context is None:
        return None
    return business_context.declared_baselines.get(metric)


def margin_baseline(
    session: Session, product_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    """Returns (baseline, current_value): the historical reference and the
    recent value to compare it against -- kept separate rather than folded
    into the Baseline itself, since "current" isn't part of what "normal"
    means."""

    trend = compute_margin_trend(session, product_id)
    baseline = build_baseline(
        "margin_pct",
        observed_value=trend.baseline_margin_pct,
        sample_size=trend.sample_size,
        declared_value=_declared(business_context, "margin_pct"),
    )
    return baseline, trend.recent_margin_pct


def supplier_delivery_baseline(
    session: Session, supplier_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    trend = compute_supplier_delivery_performance(session, supplier_id)
    baseline = build_baseline(
        "delivery_delay_days",
        observed_value=trend.baseline_avg_delay_days,
        sample_size=trend.sample_size,
        declared_value=_declared(business_context, "delivery_delay_days"),
    )
    return baseline, trend.recent_avg_delay_days


def customer_value_baseline(
    session: Session, customer_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    """The metric here (`customer_revenue_variation_pct`) is itself already a
    delta between two periods, not a level with a separate historical
    baseline to observe -- so there is no `observed_value` distinct from the
    current reading to extract from history. Absent a company-declared
    target, "normal" falls back to the generic benchmark (0% -- no change),
    which is an honest default, not a placeholder standing in for missing
    logic."""

    trend = compute_customer_value_trend(session, customer_id)
    baseline = build_baseline(
        "customer_revenue_variation_pct",
        observed_value=None,
        sample_size=trend.sample_size,
        declared_value=_declared(business_context, "customer_revenue_variation_pct"),
    )
    return baseline, trend.variation_pct


def supplier_unanswered_message_baseline(
    session: Session, supplier_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    """Like `customer_value_baseline`, this metric (the age in days of the
    oldest still-unanswered inbound Communication) is a point-in-time fact,
    not a level with its own separate observed history -- so `observed_value`
    is always `None`; "normal" comes from a company-declared expectation
    (e.g. "we respond within 3 days") or the generic benchmark otherwise."""

    result = compute_unanswered_message_age(session, RelatedEntityType.SUPPLIER, supplier_id)
    baseline = build_baseline(
        "unanswered_message_age_days",
        observed_value=None,
        sample_size=result.sample_size,
        declared_value=_declared(business_context, "unanswered_message_age_days"),
    )
    return baseline, result.age_days


def customer_unanswered_message_baseline(
    session: Session, customer_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    result = compute_unanswered_message_age(session, RelatedEntityType.CUSTOMER, customer_id)
    baseline = build_baseline(
        "unanswered_message_age_days",
        observed_value=None,
        sample_size=result.sample_size,
        declared_value=_declared(business_context, "unanswered_message_age_days"),
    )
    return baseline, result.age_days


def customer_quote_pending_baseline(
    session: Session, customer_id, business_context: BusinessContext | None = None
) -> tuple[Baseline, float | None]:
    """V2: age of the oldest quote still awaiting this customer's answer.
    A point-in-time fact like the unanswered-message metrics: "normal" is
    the company's declared `quote_response_days` or the generic default."""

    from app.core.analytics import compute_pending_quote_age

    result = compute_pending_quote_age(session, customer_id)
    baseline = build_baseline(
        "quote_response_days",
        observed_value=None,
        sample_size=result.sample_size,
        declared_value=_declared(business_context, "quote_response_days"),
    )
    return baseline, result.age_days
