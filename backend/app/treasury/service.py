"""Director finance (V2.1, brain/director_finance.md): treasury, accounts,
ownership and an estimated company value. NOT a bank, not accounting.

Everything is deterministic and explainable -- no LLM computes a number:

  cash now      = declared/observed account balances
  + / - flows   = ACTUAL movements (already in the balance after its date),
                  PLANNED movements (committed: loan, tax, salaries...),
                  receivables/payables read from commercial documents
                  (issued customer invoices, approved supplier invoices:
                  DECLARED amounts and due dates),
                  ESTIMATED flows (confirmed orders not invoiced yet)
  projection    = a LOW line (planned + declared, estimated inflows ignored)
                  and a HIGH line (+ estimated inflows) -- a range, never a point.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.analytics import _as_aware_utc, compute_company_financials
from app.core.entities import (
    BankAccount,
    BusinessContext,
    CashMovement,
    CommercialDocument,
    DocumentKind,
    RelatedEntityType,
    Risk,
    RiskSeverity,
    RiskStatus,
    Shareholder,
    Transaction,
    TransactionType,
)
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent

CASH_FORECAST_DETERIORATED = "CashForecastDeteriorated"
HORIZONS = (30, 60, 90)
# Revenue multiple benchmark for a small company's enterprise value when
# none is declared -- a wide, generic BENCHMARK, labelled as such.
GENERIC_REVENUE_MULTIPLE = (0.5, 1.5)
DEFAULT_PAYMENT_DELAY_DAYS = 30


class TreasuryError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(session: Session, company_id: uuid.UUID) -> dict:
    ctx = session.query(BusinessContext).filter_by(company_id=company_id).first()
    return dict(ctx.finance_settings or {}) if ctx else {}


def mask_identifier(raw: str | None, kind: str) -> str | None:
    """Keeps only the last 4 characters -- a full IBAN or card number is
    never stored or returned."""

    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isalnum())
    if len(digits) < 4:
        raise TreasuryError("Identifiant trop court")
    prefix = digits[:4].upper() + " " if kind != "card" and digits[:2].isalpha() else ""
    return f"{prefix}•••• {digits[-4:]}"


@dataclass
class Flow:
    date: datetime
    direction: str
    amount: float
    status: str  # "actual" | "planned" | "declared" | "estimated"
    category: str
    label: str
    account_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    source: str | None = None


def _document_flows(session: Session, company_id: uuid.UUID, now: datetime) -> list[Flow]:
    """Receivables / payables straight from the commercial documents -- the
    treasury reads the transactional model instead of copying it."""

    flows: list[Flow] = []
    docs = session.query(CommercialDocument).filter(
        CommercialDocument.company_id == company_id,
        CommercialDocument.kind.in_([DocumentKind.CUSTOMER_INVOICE, DocumentKind.SUPPLIER_INVOICE, DocumentKind.CUSTOMER_ORDER]),
    )
    for doc in docs.all():
        total = sum(ln.quantity * ln.unit_price for ln in doc.lines if ln.unit_price is not None)
        if not total:
            continue
        due = _as_aware_utc(doc.due_at) if doc.due_at else _as_aware_utc(doc.issued_at or doc.created_at) + timedelta(days=DEFAULT_PAYMENT_DELAY_DAYS)
        due = max(due, now)
        if doc.kind == DocumentKind.CUSTOMER_INVOICE and doc.status == "issued":
            flows.append(Flow(due, "in", total, "declared", "customer_payment", f"Facture client {doc.number}", document_id=doc.id, source="document"))
        elif doc.kind == DocumentKind.SUPPLIER_INVOICE and doc.status in {"received", "approved"}:
            flows.append(Flow(due, "out", total, "declared", "supplier_payment", f"Facture fournisseur {doc.number}", document_id=doc.id, source="document"))
        elif doc.kind == DocumentKind.CUSTOMER_ORDER and doc.status in {"confirmed", "delivered"}:
            # Not invoiced yet: the cash is expected, not committed.
            flows.append(Flow(due + timedelta(days=DEFAULT_PAYMENT_DELAY_DAYS), "in", total, "estimated", "customer_payment", f"Commande {doc.number} (non facturée)", document_id=doc.id, source="document"))
    return flows


def _movement_flows(session: Session, company_id: uuid.UUID, now: datetime) -> tuple[list[Flow], list[Flow]]:
    past, future = [], []
    for m in session.query(CashMovement).filter_by(company_id=company_id).all():
        flow = Flow(_as_aware_utc(m.occurred_at), m.direction, m.amount, m.status, m.category, m.label or m.category, m.account_id, m.document_id, m.source)
        (future if flow.date > now and m.status != "actual" else past).append(flow)
    return past, future


@dataclass
class ProjectionPoint:
    horizon_days: int
    low: float
    high: float


@dataclass
class AccountView:
    id: uuid.UUID
    name: str
    bank_name: str | None
    kind: str
    masked_identifier: str | None
    balance: float
    balance_basis: str
    balance_as_of: datetime
    source: str
    inflows_30d: float
    outflows_30d: float
    upcoming: list[dict]
    projection: list[ProjectionPoint]
    interest_rate: float | None = None
    maturity_at: datetime | None = None


def _project(start: float, flows: list[Flow], now: datetime) -> list[ProjectionPoint]:
    points = []
    for h in HORIZONS:
        window = [f for f in flows if f.date <= now + timedelta(days=h)]
        certain = sum((f.amount if f.direction == "in" else -f.amount) for f in window if f.status in {"planned", "declared"})
        estimated_out = sum(f.amount for f in window if f.status == "estimated" and f.direction == "out")
        estimated_in = sum(f.amount for f in window if f.status == "estimated" and f.direction == "in")
        points.append(ProjectionPoint(h, round(start + certain - estimated_out, 2), round(start + certain + estimated_in, 2)))
    return points


def treasury_overview(session: Session, company_id: uuid.UUID) -> dict:
    now = _now()
    accounts = session.query(BankAccount).filter_by(company_id=company_id).order_by(BankAccount.kind, BankAccount.name).all()
    past, future = _movement_flows(session, company_id, now)
    doc_flows = _document_flows(session, company_id, now)

    views: list[AccountView] = []
    for acc in accounts:
        acc_past = [f for f in past if f.account_id == acc.id and f.date >= now - timedelta(days=30)]
        acc_future = sorted((f for f in future if f.account_id == acc.id), key=lambda f: f.date)
        views.append(
            AccountView(
                acc.id, acc.name, acc.bank_name, acc.kind, acc.masked_identifier, acc.balance, acc.balance_basis.value,
                acc.balance_as_of, acc.source,
                round(sum(f.amount for f in acc_past if f.direction == "in"), 2), round(sum(f.amount for f in acc_past if f.direction == "out"), 2),
                [asdict(f) for f in acc_future[:15]],
                _project(acc.balance if acc.kind != "loan" else -acc.balance, acc_future, now) if acc.kind != "loan" else [],
                acc.interest_rate, acc.maturity_at,
            )
        )  # fmt: skip

    cash_accounts = [a for a in accounts if a.kind in {"current", "savings"}]
    cash_now = sum(a.balance for a in cash_accounts)
    debt = sum(a.balance for a in accounts if a.kind == "loan")
    company_flows = sorted([f for f in future if f.account_id is None or any(a.id == f.account_id for a in cash_accounts)] + doc_flows, key=lambda f: f.date)
    projection = _project(cash_now, company_flows, now)
    settings = _settings(session, company_id)
    min_cash = settings.get("min_cash")
    bases = {a.balance_basis.value for a in cash_accounts}
    return {
        "as_of": now,
        "cash_now": round(cash_now, 2),
        "cash_basis": "simulated" if "simulated" in bases else ("observed" if bases == {"observed"} else "declared" if bases else "unknown"),
        "debt_outstanding": round(debt, 2),
        "projection": [asdict(p) for p in projection],
        "min_cash": min_cash,
        "below_min_cash": bool(min_cash is not None and projection and min(p.low for p in projection) < min_cash),
        "upcoming": [asdict(f) for f in company_flows[:30]],
        "accounts": [asdict(v) for v in views],
        "method": "Solde des comptes + flux planifiés et factures (déclarés) ; la borne haute ajoute les encaissements estimés (commandes non facturées).",
    }


def monitor_cash(session: Session, event_bus: EventBus, company_id: uuid.UUID) -> dict:
    """Cash forecast deterioration -> Business Event -> a V1 Risk (company-
    level), whose RiskCreated reaction creates the review Task as for every
    other Risk. Idempotent: one open cash Risk at a time."""

    overview = treasury_overview(session, company_id)
    if not overview["below_min_cash"]:
        return {"risk_created": False, "reason": "Projection au-dessus du seuil déclaré" if overview["min_cash"] is not None else "Aucun seuil de trésorerie déclaré"}
    title = "Trésorerie projetée sous le seuil minimum"
    if session.query(Risk.id).filter_by(company_id=company_id, title=title, status=RiskStatus.OPEN).first() is not None:
        return {"risk_created": False, "reason": "Risque déjà ouvert"}
    low = min(p["low"] for p in overview["projection"])
    risk = Risk(
        company_id=company_id, title=title, severity=RiskSeverity.HIGH, status=RiskStatus.OPEN,
        description=f"Projection basse à {low:,.0f} € sur 90 jours, sous le seuil déclaré de {overview['min_cash']:,.0f} €.".replace(",", " "),
        related_entity_type=RelatedEntityType.COMPANY, related_entity_id=company_id,
    )  # fmt: skip
    session.add(risk)
    session.commit()
    event_bus.publish(BusinessEvent(event_type=CASH_FORECAST_DETERIORATED, source="treasury", payload={"projected_low": low, "min_cash": overview["min_cash"], "title": title}))
    from app.intelligence.risks.service import RISK_CREATED

    event_bus.publish(BusinessEvent(event_type=RISK_CREATED, source="treasury", payload={"risk_id": str(risk.id), "severity": risk.severity.value}))
    return {"risk_created": True, "risk_id": str(risk.id)}


# --- Ownership & valuation -------------------------------------------------------------


@dataclass
class Valuation:
    declared: dict | None
    estimated_min: float | None
    estimated_max: float | None
    basis: str
    confidence: str
    inputs: list[dict] = field(default_factory=list)
    method: str = ""


def _revenue(session: Session, company_id: uuid.UUID, start: datetime, end: datetime) -> float:
    rows = session.query(Transaction).filter(Transaction.company_id == company_id, Transaction.type == TransactionType.SALES_ORDER).all()
    return sum(t.amount for t in rows if start <= _as_aware_utc(t.occurred_at) < end and t.status.value != "cancelled")


def estimate_valuation(session: Session, company_id: uuid.UUID) -> Valuation:
    """A deliberately simple, explainable estimate:
    EV = revenue(12m) x multiple range (declared, else a generic benchmark),
    adjusted for margin and growth; equity = EV + cash - debt - taxes due.
    Always a range, always labelled -- never an official value."""

    now = _now()
    settings = _settings(session, company_id)
    declared = None
    if settings.get("declared_valuation"):
        declared = {"value": settings["declared_valuation"], "date": settings.get("declared_valuation_date"), "basis": "declared"}

    revenue = _revenue(session, company_id, now - timedelta(days=365), now)
    previous = _revenue(session, company_id, now - timedelta(days=730), now - timedelta(days=365))
    financials = compute_company_financials(session, company_id)
    treasury = treasury_overview(session, company_id)
    taxes_due = sum(f["amount"] for f in treasury["upcoming"] if f["category"] == "tax" and f["direction"] == "out")

    inputs = [
        {"label": "Chiffre d'affaires 12 mois", "value": round(revenue, 2), "basis": "observed", "source": "Écritures de vente"},
        {"label": "Marge globale", "value": financials.overall_margin_pct, "basis": "observed", "source": "Écritures"},
        {"label": "Croissance vs 12 mois précédents", "value": round((revenue - previous) / previous, 4) if previous else None, "basis": "observed" if previous else "unknown", "source": "Écritures"},
        {"label": "Trésorerie", "value": treasury["cash_now"], "basis": treasury["cash_basis"], "source": "Comptes"},
        {"label": "Dette", "value": treasury["debt_outstanding"], "basis": "declared", "source": "Prêts"},
        {"label": "Impôts à payer (planifiés)", "value": round(taxes_due, 2), "basis": "declared", "source": "Flux planifiés"},
    ]
    if revenue <= 0:
        return Valuation(declared, None, None, "unknown", "none", inputs, "Chiffre d'affaires inconnu : aucune estimation possible.")

    if settings.get("revenue_multiple_min") and settings.get("revenue_multiple_max"):
        lo, hi, multiple_basis = float(settings["revenue_multiple_min"]), float(settings["revenue_multiple_max"]), "declared"
    else:
        (lo, hi), multiple_basis = GENERIC_REVENUE_MULTIPLE, "benchmark"
    margin = financials.overall_margin_pct
    if margin is not None and margin < 0:
        lo, hi = lo * 0.5, hi * 0.6
    elif margin is not None and margin > 0.2:
        lo, hi = lo * 1.1, hi * 1.2
    growth = inputs[2]["value"]
    if growth is not None and growth > 0.2:
        hi *= 1.15
    net_cash = treasury["cash_now"] - treasury["debt_outstanding"] - taxes_due
    estimated_min, estimated_max = revenue * lo + net_cash, revenue * hi + net_cash
    inputs.append({"label": "Multiple de CA retenu", "value": f"{lo:.2f}–{hi:.2f}×", "basis": multiple_basis, "source": "Déclaré" if multiple_basis == "declared" else "Référence générique PME"})
    confidence = "medium" if multiple_basis == "declared" and growth is not None else "low"
    if treasury["cash_basis"] == "simulated":
        confidence = "low"
    return Valuation(
        declared, round(max(estimated_min, 0.0), -3), round(max(estimated_max, 0.0), -3), "estimated", confidence, inputs,
        "Valeur d'entreprise = CA 12 mois × multiple (ajusté marge/croissance) ; valeur des titres = + trésorerie − dette − impôts dus.",
    )  # fmt: skip


def ownership(session: Session, company_id: uuid.UUID) -> dict:
    holders = session.query(Shareholder).filter_by(company_id=company_id).order_by(Shareholder.shares.desc()).all()
    total = sum(h.shares for h in holders)
    valuation = estimate_valuation(session, company_id)
    reference = valuation.declared["value"] if valuation.declared else None
    rows = []
    for h in holders:
        pct = h.shares / total if total else 0.0
        economic = h.economic_rights_pct if h.economic_rights_pct is not None else pct
        rows.append(
            {
                "id": h.id, "name": h.name, "kind": h.kind, "shares": h.shares, "share_class": h.share_class, "pct": round(pct, 4),
                "economic_rights_pct": round(economic, 4), "economic_rights_declared": h.economic_rights_pct is not None,
                "employee_id": h.employee_id, "basis": h.basis.value, "acquired_at": h.acquired_at,
                "value_estimated_min": round(economic * valuation.estimated_min, -2) if valuation.estimated_min is not None else None,
                "value_estimated_max": round(economic * valuation.estimated_max, -2) if valuation.estimated_max is not None else None,
                "value_declared": round(economic * reference, -2) if reference else None,
            }
        )  # fmt: skip
    return {"total_shares": total, "holders": rows, "valuation": asdict(valuation)}


def company_overview(session: Session, company_id: uuid.UUID) -> dict:
    financials = compute_company_financials(session, company_id)
    treasury = treasury_overview(session, company_id)
    valuation = estimate_valuation(session, company_id)
    return {
        "revenue": financials.total_revenue,
        "costs": financials.total_costs,
        "margin_pct": financials.overall_margin_pct,
        "cash_now": treasury["cash_now"],
        "cash_basis": treasury["cash_basis"],
        "debt": treasury["debt_outstanding"],
        "projection_90": treasury["projection"][-1] if treasury["projection"] else None,
        "below_min_cash": treasury["below_min_cash"],
        "valuation": asdict(valuation),
    }
