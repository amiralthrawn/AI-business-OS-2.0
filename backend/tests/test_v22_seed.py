"""The V2.2 demo layer replays payments, instalments, deliveries, credit notes
and supplier claims on top of V1 + V2 + V2.1 -- idempotent, labelled as
simulated, and coherent: every balance matches its invoices, payments and
imputed credit notes, and no refused/pending credit note moves a balance."""

from app.billing import service as billing
from app.core.entities import CashMovement, CommercialDocument, CreditApplication, Customer, DocumentKind, Task, TaskStatus
from app.event_bus import build_event_bus
from data.seed import seed
from data.seed_v2 import seed_v2_demo
from data.seed_v21 import seed_v21_demo
from data.seed_v22 import seed_v22_demo

K = DocumentKind


def test_seed_v22_tells_varied_coherent_stories(db_session, session_factory):
    bus = build_event_bus(session_factory)
    seed(db_session, bus)
    seed_v2_demo(db_session, bus)
    seed_v21_demo(db_session, bus)
    result = seed_v22_demo(db_session, bus)
    assert result["skipped"] is False
    assert seed_v22_demo(db_session, bus)["skipped"] is True  # idempotent
    company_id = db_session.query(Customer).first().company_id

    accounts = {c.name: billing.party_account(db_session, company_id, customer_id=c.id) for c in db_session.query(Customer).all()}
    for name, a in accounts.items():
        expected = round(a["outstanding"] - a["unallocated"] - a["credit_on_account"] - a["refund_due"], 2)
        assert abs(a["balance"] - expected) < 0.01, name

    assert accounts["BrightWorks Ltd"]["open_invoices"][0]["installments_paid"] == 2
    assert accounts["BrightWorks Ltd"]["balance"] == 4000
    assert accounts["Vantix Group"]["overdue"] > 0 and accounts["Vantix Group"]["pending_credit_notes"]  # late + credit not deducted yet
    assert accounts["Atelier Rhône Industrie"]["refund_due"] == 300
    assert accounts["Helio Parc Énergie"]["is_up_to_date"]

    credit_notes = {d.number: d for d in db_session.query(CommercialDocument).filter(CommercialDocument.kind.in_([K.CUSTOMER_CREDIT_NOTE, K.SUPPLIER_CREDIT_NOTE])).all()}
    statuses = {d.status for d in credit_notes.values()}
    assert {"applied", "accepted", "rejected", "confirmed"} <= statuses
    rejected = [d for d in credit_notes.values() if d.status == "rejected"]
    assert rejected and all(db_session.query(CreditApplication).filter_by(credit_note_id=d.id).count() == 0 for d in rejected)
    # One validation still waiting for a human (HITL), visible in the Centre de contrôle.
    assert db_session.query(Task).filter_by(pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION, status=TaskStatus.PENDING_VALIDATION).count() == 1

    # Orders waiting for the customer; deliveries partial / late / in transit.
    overview = billing.billing_overview(db_session, company_id)
    assert {o["status"] for o in overview["orders_awaiting_confirmation"]} == {"sent", "acknowledged"}
    states = {d["state"] for d in overview["deliveries_to_watch"]}
    assert {"partial", "in_transit"} <= states and any(d["is_late"] for d in overview["deliveries_to_watch"])

    # Everything V2.2 created is identifiable as demonstration data.
    new_docs = db_session.query(CommercialDocument).filter(CommercialDocument.kind.in_([K.CUSTOMER_CREDIT_NOTE, K.CUSTOMER_INVOICE])).all()
    assert all(d.source == "simulated" for d in new_docs)
    payments = db_session.query(CashMovement).filter(CashMovement.document_id.isnot(None)).all()
    assert payments and all(m.source == "simulated" for m in payments)
