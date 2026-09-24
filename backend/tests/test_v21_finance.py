"""V2.1 director finance: deterministic treasury projection (low/high range,
document-derived flows), masked identifiers, cash risk through V1, cap table
and a labelled valuation range; director-only access by default."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.entities import (
    BankAccount,
    BusinessContext,
    CashMovement,
    DocumentKind,
    Risk,
    Role,
    Shareholder,
    Task,
    Transaction,
    TransactionStatus,
    TransactionType,
    UserProfile,
    ValueBasis,
)
from app.event_bus import build_event_bus
from app.transactions import service as docs
from app.transactions.service import DocumentInput, LineInput
from app.treasury import service
from tests.v2_support import api_client, build_world

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def world(db_session):
    w = build_world(db_session)
    db_session.add(BusinessContext(company_id=w.company.id, country="FR", monitored_domains=[], home_focus=[], declared_baselines={}, learned_notes=[], finance_settings={"min_cash": 10000}))
    db_session.add(BankAccount(company_id=w.company.id, name="Courant", kind="current", balance=20000, balance_basis=ValueBasis.DECLARED, balance_as_of=NOW))
    db_session.add(BankAccount(company_id=w.company.id, name="Prêt", kind="loan", balance=50000, balance_basis=ValueBasis.DECLARED, balance_as_of=NOW))
    db_session.commit()
    return w


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def test_projection_is_a_range_built_from_planned_declared_and_estimated_flows(db_session, world, bus):
    account = db_session.query(BankAccount).filter_by(name="Courant").one()
    db_session.add(CashMovement(company_id=world.company.id, account_id=account.id, direction="out", amount=3000, status="planned", occurred_at=NOW + timedelta(days=10), category="salary"))
    db_session.commit()
    # An issued customer invoice (declared receivable) and a confirmed, uninvoiced order (estimated).
    invoice = docs.create_document(db_session, bus, world.company.id, DocumentInput(kind=DocumentKind.CUSTOMER_INVOICE, customer_id=world.customer.id, due_at=NOW + timedelta(days=20), lines=[LineInput(product_id=world.product.id, quantity=5)]))
    docs.change_status(db_session, bus, invoice, "issued")
    order = docs.create_document(db_session, bus, world.company.id, DocumentInput(kind=DocumentKind.CUSTOMER_ORDER, customer_id=world.customer.id, due_at=NOW, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    docs.change_status(db_session, bus, order, "confirmed")

    overview = service.treasury_overview(db_session, world.company.id)
    assert overview["cash_now"] == 20000 and overview["debt_outstanding"] == 50000
    p30 = next(p for p in overview["projection"] if p["horizon_days"] == 30)
    p90 = next(p for p in overview["projection"] if p["horizon_days"] == 90)
    assert p30["low"] == 20000 - 3000 + 4500  # planned salary out + declared invoice in
    assert p90["high"] - p90["low"] == 9000  # the estimated order only widens the high bound
    sources = {f["label"] for f in overview["upcoming"]}
    assert any(invoice.number in s for s in sources) and any(order.number in s for s in sources)  # read from the documents, not copied


def test_cash_below_declared_threshold_creates_one_v1_risk_and_its_review_task(db_session, world, bus):
    account = db_session.query(BankAccount).filter_by(name="Courant").one()
    db_session.add(CashMovement(company_id=world.company.id, account_id=account.id, direction="out", amount=15000, status="planned", occurred_at=NOW + timedelta(days=5), category="tax"))
    db_session.commit()
    assert service.monitor_cash(db_session, bus, world.company.id)["risk_created"] is True
    assert service.monitor_cash(db_session, bus, world.company.id)["risk_created"] is False  # idempotent
    risk = db_session.query(Risk).filter_by(title="Trésorerie projetée sous le seuil minimum").one()
    assert db_session.query(Task).filter(Task.title.contains(risk.title)).count() == 1  # V1 RiskCreated -> Task reaction


def test_identifiers_are_masked_never_stored_in_full():
    assert service.mask_identifier("FR76 3000 6000 0112 3456 7890 189", "current") == "FR76 •••• 0189"
    assert service.mask_identifier("4970 1012 3456 4242", "card") == "•••• 4242"


def test_ownership_percentages_and_valuation_are_computed_and_labelled(db_session, world):
    for name, shares in (("A", 450), ("B", 450), ("CEO", 100)):
        db_session.add(Shareholder(company_id=world.company.id, name=name, shares=shares))
    # 12 months of sales (the world already has purchase history).
    for i in range(12):
        db_session.add(Transaction(company_id=world.company.id, customer_id=world.customer.id, product_id=world.product.id, type=TransactionType.SALES_ORDER, status=TransactionStatus.CONFIRMED, amount=10000, occurred_at=NOW - timedelta(days=15 + 28 * i)))
    db_session.commit()
    data = service.ownership(db_session, world.company.id)
    assert [h["pct"] for h in data["holders"]] == [0.45, 0.45, 0.1]
    valuation = data["valuation"]
    assert valuation["basis"] == "estimated" and valuation["declared"] is None
    assert valuation["estimated_min"] < valuation["estimated_max"]
    assert any(i["basis"] == "benchmark" for i in valuation["inputs"])  # no declared multiple: generic benchmark, said so
    ceo = data["holders"][-1]
    assert ceo["value_estimated_min"] == round(0.1 * valuation["estimated_min"], -2)


def test_director_finance_is_director_only_by_default(session_factory, db_session, world):
    sales = UserProfile(company_id=world.company.id, name="S", role=Role.SALES, access_grants=[], access_revokes=[])
    db_session.add(sales)
    db_session.commit()
    as_sales = {"X-User-Id": str(sales.id)}
    with api_client(session_factory) as client:
        assert client.get("/treasury/overview", headers=as_sales).status_code == 403
        assert client.get("/ownership", headers=as_sales).status_code == 403
        assert client.get("/treasury/overview").status_code == 200  # director / legacy operator
        created = client.post("/treasury/accounts", json={"name": "Carte", "kind": "card", "identifier": "4970101234564242", "balance": -120}).json()
        assert created["masked_identifier"] == "•••• 4242"
        assert "4970101234564242" not in str(client.get("/treasury/overview").json())
