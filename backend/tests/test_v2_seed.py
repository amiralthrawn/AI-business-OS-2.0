"""The V2 demo layer replays real workflows over the V1 seed, idempotently,
and produces the 'less profitable than planned' deal the product shows."""

from app.core.entities import CommercialDocument, DocumentKind, Transaction, UserProfile
from app.event_bus import build_event_bus
from app.transactions.margin import compute_document_margin
from data.seed import seed
from data.seed_v2 import seed_v2_demo


def test_seed_v2_builds_linked_deals_on_the_v1_seed(db_session, session_factory):
    bus = build_event_bus(session_factory)
    seed(db_session, bus)
    v1_transactions = db_session.query(Transaction).count()

    result = seed_v2_demo(db_session, bus)
    assert result["skipped"] is False and result["documents"] >= 15
    assert seed_v2_demo(db_session, bus)["skipped"] is True  # idempotent

    order = db_session.query(CommercialDocument).filter_by(kind=DocumentKind.CUSTOMER_ORDER).one()
    margin = compute_document_margin(db_session, order)
    assert margin.current.cost_basis == "actual"
    assert margin.current.margin_max < margin.planned.margin_min  # less profitable than planned
    # V2 documents posted real ledger facts for V1 analytics, traced back.
    assert db_session.query(Transaction).count() > v1_transactions
    assert db_session.query(Transaction).filter(Transaction.source_document_id.isnot(None)).count() >= 2
    assert db_session.query(UserProfile).count() == 3


def test_seed_v21_layers_people_finance_compliance_on_top(db_session, session_factory):
    from app.core.entities import AIRun, BankAccount, Candidate, Employee, Opportunity, Shareholder, SourcingLead, Task
    from app.people.service import employee_cost, estimate_contribution
    from data.seed_v21 import seed_v21_demo

    bus = build_event_bus(session_factory)
    seed(db_session, bus)
    seed_v2_demo(db_session, bus)
    assert seed_v21_demo(db_session, bus)["skipped"] is False
    assert seed_v21_demo(db_session, bus)["skipped"] is True  # idempotent

    hugo = db_session.query(Employee).filter_by(full_name="Hugo Martin").one()
    cost = employee_cost(db_session, hugo)
    assert cost.basis == "simulated" and cost.total_min < cost.total_max  # a range, labelled simulated
    contribution = estimate_contribution(db_session, hugo, cost)
    assert contribution.attributable_margin_min is not None  # owns the demo deal
    assert db_session.query(Candidate).count() == 1 and db_session.query(Opportunity).filter(Opportunity.title.like("Recruter%")).count() >= 1
    assert db_session.query(BankAccount).count() == 4 and db_session.query(Shareholder).count() == 3
    assert db_session.query(Task).filter_by(domain="compliance").count() == 3
    assert db_session.query(AIRun).filter_by(kind="website_audit", mode="simulated").count() == 1
    assert db_session.query(SourcingLead).count() >= 1
