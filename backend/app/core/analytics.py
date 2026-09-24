"""Shared, deterministic trend computations over the Data Core.

Both the Intelligence layer (proactive monitoring rules) and the AI layer
(on-demand analysis capabilities) need the exact same numbers -- e.g. "has
this supplier's delivery performance degraded?" must mean the same thing
whether a human asks or the system detects it on its own. Putting the math
here once, as plain functions with no side effects, is what keeps those two
callers from silently drifting apart or duplicating business logic.

Every function here does real arithmetic on real rows. No LLM, no estimates.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.entities import (
    Communication,
    CommunicationDirection,
    RelatedEntityType,
    Transaction,
    TransactionType,
)


def _split_in_half(rows: list) -> tuple[list, list]:
    """Splits a chronologically-ordered list into an earlier and a later half,
    the simplest possible baseline-vs-recent comparison. With too few rows to
    compare meaningfully, the "earlier" half is returned empty rather than
    guessed at."""

    if len(rows) < 4:
        return [], rows
    midpoint = len(rows) // 2
    return rows[:midpoint], rows[midpoint:]


@dataclass(frozen=True)
class SupplierDeliveryPerformance:
    supplier_id: object
    sample_size: int
    baseline_avg_delay_days: float | None
    recent_avg_delay_days: float | None
    baseline_on_time_rate: float | None
    recent_on_time_rate: float | None
    trend: str  # "deteriorating" | "stable" | "improving" | "insufficient_data"


def compute_supplier_delivery_performance(session: Session, supplier_id) -> SupplierDeliveryPerformance:
    rows = (
        session.query(Transaction)
        .filter(
            Transaction.supplier_id == supplier_id,
            Transaction.type == TransactionType.PURCHASE_ORDER,
            Transaction.expected_at.isnot(None),
        )
        .order_by(Transaction.occurred_at.asc())
        .all()
    )

    baseline, recent = _split_in_half(rows)
    if not recent:
        return SupplierDeliveryPerformance(supplier_id, len(rows), None, None, None, None, "insufficient_data")

    def _metrics(batch: list) -> tuple[float, float] | tuple[None, None]:
        if not batch:
            return None, None
        delays = [max((t.occurred_at - t.expected_at).total_seconds() / 86400, 0.0) for t in batch]
        on_time = sum(1 for d in delays if d <= 1.0) / len(delays)
        return sum(delays) / len(delays), on_time

    baseline_delay, baseline_on_time = _metrics(baseline)
    recent_delay, recent_on_time = _metrics(recent)

    if baseline_delay is None:
        trend = "insufficient_data"
    elif recent_delay - baseline_delay >= 1.5:
        trend = "deteriorating"
    elif baseline_delay - recent_delay >= 1.5:
        trend = "improving"
    else:
        trend = "stable"

    return SupplierDeliveryPerformance(
        supplier_id=supplier_id,
        sample_size=len(rows),
        baseline_avg_delay_days=baseline_delay,
        recent_avg_delay_days=recent_delay,
        baseline_on_time_rate=baseline_on_time,
        recent_on_time_rate=recent_on_time,
        trend=trend,
    )


@dataclass(frozen=True)
class CustomerValueTrend:
    customer_id: object
    sample_size: int
    baseline_revenue: float | None
    recent_revenue: float | None
    variation_pct: float | None
    trend: str  # "growing" | "declining" | "stable" | "insufficient_data"


def compute_customer_value_trend(session: Session, customer_id) -> CustomerValueTrend:
    rows = (
        session.query(Transaction)
        .filter(Transaction.customer_id == customer_id, Transaction.type == TransactionType.SALES_ORDER)
        .order_by(Transaction.occurred_at.asc())
        .all()
    )

    baseline, recent = _split_in_half(rows)
    if not recent or not baseline:
        total = sum(t.amount for t in rows)
        return CustomerValueTrend(customer_id, len(rows), None, total or None, None, "insufficient_data")

    baseline_revenue = sum(t.amount for t in baseline)
    recent_revenue = sum(t.amount for t in recent)
    variation_pct = (recent_revenue - baseline_revenue) / baseline_revenue if baseline_revenue else None

    if variation_pct is None:
        trend = "insufficient_data"
    elif variation_pct >= 0.15:
        trend = "growing"
    elif variation_pct <= -0.15:
        trend = "declining"
    else:
        trend = "stable"

    return CustomerValueTrend(
        customer_id=customer_id,
        sample_size=len(rows),
        baseline_revenue=baseline_revenue,
        recent_revenue=recent_revenue,
        variation_pct=variation_pct,
        trend=trend,
    )


@dataclass(frozen=True)
class MarginTrend:
    product_id: object
    sample_size: int
    baseline_margin_pct: float | None
    recent_margin_pct: float | None
    point_change: float | None
    trend: str  # "deteriorating" | "stable" | "improving" | "insufficient_data"


def compute_margin_trend(session: Session, product_id) -> MarginTrend:
    cost_rows = (
        session.query(Transaction)
        .filter(
            Transaction.product_id == product_id,
            Transaction.type.in_([TransactionType.PURCHASE_ORDER, TransactionType.INVOICE]),
        )
        .order_by(Transaction.occurred_at.asc())
        .all()
    )
    revenue_rows = (
        session.query(Transaction)
        .filter(Transaction.product_id == product_id, Transaction.type == TransactionType.SALES_ORDER)
        .order_by(Transaction.occurred_at.asc())
        .all()
    )

    def _margin_pct(costs: list, revenues: list) -> float | None:
        cost = sum(t.amount for t in costs)
        revenue = sum(t.amount for t in revenues)
        if not revenue:
            return None
        return (revenue - cost) / revenue

    cost_before, cost_after = _split_in_half(cost_rows)
    revenue_before, revenue_after = _split_in_half(revenue_rows)

    baseline_margin = _margin_pct(cost_before, revenue_before)
    recent_margin = _margin_pct(cost_after, revenue_after)

    # The revenue side is the scarcer signal (a company has far fewer sales
    # orders than purchase orders per product in this model), so it gates
    # whether margin is knowable at all -- that's what sample_size reports.
    sample_size = len(revenue_rows)

    if baseline_margin is None or recent_margin is None:
        return MarginTrend(product_id, sample_size, baseline_margin, recent_margin, None, "insufficient_data")

    point_change = recent_margin - baseline_margin
    if point_change <= -0.05:
        trend = "deteriorating"
    elif point_change >= 0.05:
        trend = "improving"
    else:
        trend = "stable"

    return MarginTrend(product_id, sample_size, baseline_margin, recent_margin, point_change, trend)


@dataclass(frozen=True)
class CompanyFinancials:
    """Company-wide totals, distinct from compute_margin_trend's per-product
    baseline-vs-recent split -- this is the single simple aggregate the
    Finance and Procurement domain views both need (total spend, in
    Procurement's case, is exactly this total_costs number)."""

    total_revenue: float
    total_costs: float
    overall_margin_pct: float | None


def compute_company_financials(session: Session, company_id: uuid.UUID) -> CompanyFinancials:
    total_revenue = (
        session.query(Transaction)
        .filter(Transaction.company_id == company_id, Transaction.type == TransactionType.SALES_ORDER)
        .all()
    )
    total_costs = (
        session.query(Transaction)
        .filter(
            Transaction.company_id == company_id,
            Transaction.type.in_([TransactionType.PURCHASE_ORDER, TransactionType.INVOICE]),
        )
        .all()
    )
    revenue = sum(t.amount for t in total_revenue)
    costs = sum(t.amount for t in total_costs)
    margin_pct = (revenue - costs) / revenue if revenue else None
    return CompanyFinancials(total_revenue=revenue, total_costs=costs, overall_margin_pct=margin_pct)


@dataclass(frozen=True)
class MonthlyPoint:
    """One calendar month's real total for a set of Transaction types --
    zero-filled when the month has no matching Transaction, rather than
    omitted, so a chart can show an explicit gap instead of silently
    shrinking (Step 29 point 11: "afficher clairement ce qui est disponible
    et ce qui manque")."""

    month: str  # "YYYY-MM"
    total_amount: float
    transaction_count: int


def compute_monthly_series(
    session: Session,
    company_id: uuid.UUID,
    transaction_types: list[TransactionType],
    months: int = 12,
    now: datetime | None = None,
) -> list[MonthlyPoint]:
    """Real month-by-month totals over the last `months` calendar months
    (oldest first). No estimate, no interpolation: a month with zero
    matching Transactions reports `total_amount=0.0`, `transaction_count=0`."""

    now = now or datetime.now(timezone.utc)
    year, month = now.year, now.month
    keys: list[str] = []
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()

    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}

    rows = (
        session.query(Transaction)
        .filter(Transaction.company_id == company_id, Transaction.type.in_(transaction_types))
        .all()
    )
    for t in rows:
        occurred = _as_aware_utc(t.occurred_at)
        key = f"{occurred.year:04d}-{occurred.month:02d}"
        if key in totals:
            totals[key] += t.amount
            counts[key] += 1

    return [MonthlyPoint(month=k, total_amount=round(totals[k], 2), transaction_count=counts[k]) for k in keys]


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite round-trips a DateTime(timezone=True) column as timezone-naive
    (it has no real timezone storage) -- every occurred_at written in this
    codebase is UTC by convention (see app.core.entities.base.utcnow), so a
    naive value read back is treated as UTC rather than compared against an
    incompatible aware value."""

    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class UnansweredMessage:
    """Whether the OLDEST still-unanswered inbound Communication linked to an
    entity exists, and how old it is. "Unanswered" is a deliberately simple,
    generic proxy -- no thread-matching, no NLP -- an inbound Communication
    counts as answered as soon as any outbound Communication for the same
    entity ALREADY OCCURRED (not merely scheduled in the future, e.g. an
    upcoming calendar event) after it. Good enough for step 22's MVP (see
    brain/external_data_intelligence.md); a real deployment would want to
    match by thread/conversation id instead."""

    entity_id: uuid.UUID
    sample_size: int  # how many inbound Communications exist for this entity at all
    age_days: float | None  # None when there is no unanswered inbound Communication
    communication_id: uuid.UUID | None
    subject: str | None
    body: str | None
    occurred_at: datetime | None


def compute_unanswered_message_age(
    session: Session, entity_type: RelatedEntityType, entity_id: uuid.UUID, now: datetime | None = None
) -> UnansweredMessage:
    now = now or datetime.now(timezone.utc)

    inbound = (
        session.query(Communication)
        .filter(
            Communication.related_entity_type == entity_type,
            Communication.related_entity_id == entity_id,
            Communication.direction == CommunicationDirection.INBOUND,
        )
        .order_by(Communication.occurred_at.asc())
        .all()
    )
    if not inbound:
        return UnansweredMessage(entity_id, 0, None, None, None, None, None)

    outbound_times = [
        _as_aware_utc(c.occurred_at)
        for c in session.query(Communication).filter(
            Communication.related_entity_type == entity_type,
            Communication.related_entity_id == entity_id,
            Communication.direction == CommunicationDirection.OUTBOUND,
        )
        if _as_aware_utc(c.occurred_at) <= now  # a future-scheduled event (e.g. an upcoming
        # calendar meeting) hasn't happened yet, so it cannot have already answered anything
    ]

    unanswered = [msg for msg in inbound if not any(t > _as_aware_utc(msg.occurred_at) for t in outbound_times)]
    if not unanswered:
        return UnansweredMessage(entity_id, len(inbound), None, None, None, None, None)

    oldest = unanswered[0]  # `inbound` is already sorted ascending by occurred_at
    age_days = (now - _as_aware_utc(oldest.occurred_at)).total_seconds() / 86400
    return UnansweredMessage(entity_id, len(inbound), age_days, oldest.id, oldest.subject, oldest.body, oldest.occurred_at)


@dataclass(frozen=True)
class PendingQuote:
    customer_id: object
    sample_size: int  # sent quotes still awaiting the customer's decision
    age_days: float | None  # age of the oldest one
    document_id: object
    number: str | None
    issued_at: datetime | None


def compute_pending_quote_age(session: Session, customer_id) -> PendingQuote:
    """V2: how long the customer has left our oldest quote unanswered
    (status "sent": neither accepted, refused nor expired). Read from the
    CommercialDocument model -- the first V1 Observable input that comes
    from V2 business objects rather than from Transactions/Communications."""

    from app.core.entities import CommercialDocument, DocumentKind

    quotes = (
        session.query(CommercialDocument)
        .filter(
            CommercialDocument.customer_id == customer_id,
            CommercialDocument.kind == DocumentKind.CUSTOMER_QUOTE,
            CommercialDocument.status == "sent",
        )
        .all()
    )
    if not quotes:
        return PendingQuote(customer_id, 0, None, None, None, None)
    oldest = min(quotes, key=lambda q: _as_aware_utc(q.issued_at or q.created_at))
    issued = _as_aware_utc(oldest.issued_at or oldest.created_at)
    age = (datetime.now(timezone.utc) - issued).total_seconds() / 86400
    return PendingQuote(customer_id, len(quotes), age, oldest.id, oldest.number, issued)
