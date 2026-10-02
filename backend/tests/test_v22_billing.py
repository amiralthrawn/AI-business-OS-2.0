"""V2.2 billing (app.billing, brain/billing.md): instalments, partial and late
payments, one balance per party, customer credit notes (accepted / refused,
validated through HITL, imputed exactly once, refunds), order acknowledgement,
partial deliveries, non-conformities, supplier claims and permissions."""

from datetime import timedelta

import pytest

from app.actions.executor import ActionExecutor
from app.actions.service import ActionsService
from app.billing import service as billing
from app.core.entities import (
    CashMovement,
    CommercialDocument,
    CreditApplication,
    DocumentKind,
    EventLogEntry,
    RelatedEntityType,
    Risk,
    Role,
    Task,
    TaskStatus,
    Transaction,
    TransactionStatus,
    UserProfile,
)
from app.event_bus import build_event_bus
from app.transactions import service as docs
from app.transactions.service import DocumentError, DocumentInput, LineInput
from app.treasury.service import treasury_overview
from tests.v2_support import NOW, api_client, build_world

K = DocumentKind


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def _order(db, bus, world, qty=10, price=1200.0, **kw):
    order = docs.create_document(db, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_ORDER, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=qty, unit_price=price)], **kw))
    return order


def _invoice_from(db, bus, order, *, due_days=30, issued_days_ago=0):
    invoice = docs.derive_document(db, bus, order, K.CUSTOMER_INVOICE)
    invoice.due_at = NOW + timedelta(days=due_days)
    db.commit()
    docs.change_status(db, bus, invoice, "issued", occurred_at=NOW - timedelta(days=issued_days_ago))
    return invoice


def _confirmed_invoice(db, bus, world, qty=10, price=1200.0, **kw):
    order = _order(db, bus, world, qty, price)
    docs.change_status(db, bus, order, "confirmed")
    return order, _invoice_from(db, bus, order, **kw)


def _balance_invariant(account):
    # balance = still owed on invoices - payments not yet reconciled - credit kept on account - refunds owed
    expected = round(account["outstanding"] - account["unallocated"] - account["credit_on_account"] - account["refund_due"], 2)
    assert account["balance"] == pytest.approx(expected, abs=0.01)


# --- Instalments and payments --------------------------------------------------------------


def test_three_instalments_two_paid(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)  # 12 000
    billing.set_installments(db_session, bus, invoice, [
        {"due_at": NOW - timedelta(days=40), "amount": 4000, "label": "Échéance 1/3"},
        {"due_at": NOW - timedelta(days=10), "amount": 4000, "label": "Échéance 2/3"},
        {"due_at": NOW + timedelta(days=20), "amount": 4000, "label": "Échéance 3/3"},
    ])  # fmt: skip
    billing.record_payment(db_session, bus, world.company.id, amount=4000, invoice=invoice, occurred_at=NOW - timedelta(days=40))
    billing.record_payment(db_session, bus, world.company.id, amount=4000, invoice=invoice, occurred_at=NOW - timedelta(days=9))
    view = billing.settlement(db_session, invoice)
    assert (view["installments_paid"], view["installments_count"]) == (2, 3)
    assert (view["paid"], view["remaining"]) == (8000, 4000)
    assert view["state"] == "partially_paid" and not view["is_late"]
    assert view["next_due"]["label"] == "Échéance 3/3"
    assert invoice.status == "partially_paid"
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["balance"] == 4000 and account["overdue"] == 0
    _balance_invariant(account)


def test_schedules_are_free_but_must_add_up(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world, qty=5, price=1000.0)  # 5 000
    # Deposit + balance: no fixed number of instalments.
    billing.set_installments(db_session, bus, invoice, [{"due_at": NOW, "amount": 1500, "label": "Acompte 30 %"}, {"due_at": NOW + timedelta(days=45), "amount": 3500, "label": "Solde"}])
    assert billing.settlement(db_session, invoice)["installments_count"] == 2
    with pytest.raises(billing.BillingError):
        billing.set_installments(db_session, bus, invoice, [{"due_at": NOW, "amount": 1000}, {"due_at": NOW + timedelta(days=30), "amount": 1000}])


def test_late_partial_payment(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world, qty=8, price=1200.0, due_days=-25)  # 9 600, due 25 days ago
    billing.record_payment(db_session, bus, world.company.id, amount=5000, invoice=invoice)
    view = billing.settlement(db_session, invoice)
    assert view["is_late"] and view["overdue_amount"] == 4600 and view["state"] == "partially_paid"
    assert view["installments"][0]["days_late"] >= 24


def test_full_payment_settles_invoice_and_marks_order_paid(db_session, bus, world):
    order, invoice = _confirmed_invoice(db_session, bus, world, qty=2, price=1000.0)
    billing.record_payment(db_session, bus, world.company.id, amount=2000, invoice=invoice)
    assert invoice.status == "paid"
    facts = db_session.query(Transaction).filter_by(source_document_id=order.id).all()
    assert facts and all(f.status == TransactionStatus.PAID for f in facts)
    assert billing.party_account(db_session, world.company.id, customer_id=world.customer.id)["is_up_to_date"]


def test_overpayment_refused_and_unallocated_payment_reconciled(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world, qty=2, price=1000.0)
    with pytest.raises(billing.BillingError):
        billing.record_payment(db_session, bus, world.company.id, amount=2500, invoice=invoice)
    pending = billing.record_payment(db_session, bus, world.company.id, amount=2000, customer_id=world.customer.id)
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["unallocated"] == 2000 and account["balance"] == 0 and not account["is_up_to_date"]
    _balance_invariant(account)
    billing.allocate_payment(db_session, bus, pending, invoice)
    assert invoice.status == "paid"
    with pytest.raises(billing.BillingError):
        billing.allocate_payment(db_session, bus, pending, invoice)


def test_settlement_statuses_cannot_be_set_by_hand(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)
    with pytest.raises(DocumentError):
        docs.change_status(db_session, bus, invoice, "paid")
    assert invoice.status == "issued"


# --- Customer credit notes ----------------------------------------------------------------------


def _credit_note(db, bus, source, amount_qty=1, price=1000.0):
    cn = docs.derive_document(db, bus, source, K.CUSTOMER_CREDIT_NOTE)
    for ln in cn.lines:
        ln.quantity, ln.unit_price = amount_qty, price
    db.commit()
    return cn




def test_accepted_credit_note_needs_validation_then_is_imputed_once(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)  # 12 000, unpaid
    billing.record_payment(db_session, bus, world.company.id, amount=3600, invoice=invoice)
    cn = _credit_note(db_session, bus, invoice)  # 1 000
    docs.change_status(db_session, bus, cn, "submitted")
    before = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)["balance"]
    docs.change_status(db_session, bus, cn, "accepted")
    # Acceptance alone changes nothing: a validation Task is pending (HITL).
    assert billing.party_account(db_session, world.company.id, customer_id=world.customer.id)["balance"] == before
    task = db_session.query(Task).filter_by(related_entity_id=cn.id, pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION).one()
    assert task.status == TaskStatus.PENDING_VALIDATION and task.domain == "finance"
    with pytest.raises(billing.BillingError):
        billing.apply_credit_note(db_session, bus, cn)  # not validated yet
    with pytest.raises(DocumentError):
        docs.change_status(db_session, bus, cn, "validated")  # only through the approval

    ActionExecutor(ActionsService(db_session, bus)).approve(task.id)
    db_session.refresh(cn)
    assert cn.status == "validated"
    app = billing.apply_credit_note(db_session, bus, cn)
    assert (app.applied_amount, app.refund_amount) == (1000, 0)
    view = billing.settlement(db_session, invoice)
    assert view["credited"] == 1000 and view["remaining"] == 12000 - 3600 - 1000
    with pytest.raises(billing.BillingError):
        billing.apply_credit_note(db_session, bus, cn)  # never twice
    assert db_session.query(CreditApplication).filter_by(credit_note_id=cn.id).count() == 1
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["balance"] == before - 1000
    _balance_invariant(account)


def test_credit_note_on_paid_invoice_becomes_a_refund_recorded_once(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world, qty=3, price=1000.0)
    billing.record_payment(db_session, bus, world.company.id, amount=3000, invoice=invoice)
    assert invoice.status == "paid"
    cn = _credit_note(db_session, bus, invoice, price=300.0)
    for s in ("submitted", "accepted"):
        docs.change_status(db_session, bus, cn, s)
    task = db_session.query(Task).filter_by(related_entity_id=cn.id, pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION).one()
    ActionExecutor(ActionsService(db_session, bus)).approve(task.id)
    app = billing.apply_credit_note(db_session, bus, cn)
    assert (app.applied_amount, app.refund_amount) == (0, 300)
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["refund_due"] == 300 and account["balance"] == -300
    _balance_invariant(account)
    billing.record_refund(db_session, bus, cn)
    db_session.refresh(cn)
    assert cn.status == "refunded"
    with pytest.raises(billing.BillingError):
        billing.record_refund(db_session, bus, cn)
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["balance"] == 0 and account["refund_due"] == 0
    assert db_session.query(CashMovement).filter_by(document_id=cn.id, category="customer_refund").count() == 1


def test_rejected_credit_note_changes_nothing_and_opens_a_task(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)
    cn = _credit_note(db_session, bus, invoice, price=450.0)
    before = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)["balance"]
    docs.change_status(db_session, bus, cn, "submitted")
    docs.change_status(db_session, bus, cn, "rejected")
    assert billing.party_account(db_session, world.company.id, customer_id=world.customer.id)["balance"] == before
    assert db_session.query(CreditApplication).count() == 0
    follow_up = db_session.query(Task).filter_by(related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT, related_entity_id=cn.id, pending_action=None).one()
    assert follow_up.status == TaskStatus.OPEN and follow_up.requires_decision
    with pytest.raises(billing.BillingError):
        billing.apply_credit_note(db_session, bus, cn)


def test_credit_note_events_are_logged(session_factory, db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)
    cn = _credit_note(db_session, bus, invoice)
    docs.change_status(db_session, bus, cn, "submitted")
    docs.change_status(db_session, bus, cn, "accepted")
    types = {e.event_type for e in session_factory().query(EventLogEntry).all()}
    assert {billing.CREDIT_NOTE_ACCEPTED, billing.PAYMENT_RECORDED} & types == {billing.CREDIT_NOTE_ACCEPTED}
    assert "ActionProposed" in types


def test_credit_note_without_invoice_stays_as_credit_on_account(db_session, bus, world):
    order = _order(db_session, bus, world, qty=2, price=500.0)
    docs.change_status(db_session, bus, order, "confirmed")
    cn = _credit_note(db_session, bus, order, price=200.0)
    for s in ("submitted", "accepted"):
        docs.change_status(db_session, bus, cn, s)
    task = db_session.query(Task).filter_by(related_entity_id=cn.id, pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION).one()
    ActionExecutor(ActionsService(db_session, bus)).approve(task.id)
    app = billing.apply_credit_note(db_session, bus, cn)
    assert app.invoice_id is None
    account = billing.party_account(db_session, world.company.id, customer_id=world.customer.id)
    assert account["credit_on_account"] == 200 and account["balance"] == -200
    _balance_invariant(account)


# --- Orders, deliveries, non-conformities, supplier claims -------------------------------------------------


def test_order_acknowledgement_is_recorded_not_assumed(db_session, bus, world):
    order = _order(db_session, bus, world)
    docs.change_status(db_session, bus, order, "sent")
    assert db_session.query(Transaction).filter_by(source_document_id=order.id).count() == 0
    docs.change_status(db_session, bus, order, "acknowledged")
    assert db_session.query(Transaction).filter_by(source_document_id=order.id).count() == 0  # not firm yet
    docs.change_status(db_session, bus, order, "confirmed")
    assert db_session.query(Transaction).filter_by(source_document_id=order.id).count() == 1
    # The historical path draft -> confirmed still works.
    other = _order(db_session, bus, world)
    docs.change_status(db_session, bus, other, "confirmed")
    assert other.status == "confirmed"


def test_partial_delivery_and_transit(db_session, bus, world):
    order = _order(db_session, bus, world, qty=10)
    order.due_at = NOW + timedelta(days=5)
    db_session.commit()
    docs.change_status(db_session, bus, order, "confirmed")
    first = docs.derive_document(db_session, bus, order, K.CUSTOMER_DELIVERY)
    first.lines[0].quantity = 6
    db_session.commit()
    docs.change_status(db_session, bus, first, "shipped")
    docs.change_status(db_session, bus, first, "delivered")
    second = docs.derive_document(db_session, bus, order, K.CUSTOMER_DELIVERY)
    second.lines[0].quantity = 4
    db_session.commit()
    docs.change_status(db_session, bus, second, "shipped")
    view = billing.fulfilment(db_session, order)
    line = view["lines"][0]
    assert view["state"] == "partial" and (line["ordered"], line["done"], line["in_transit"], line["remaining"]) == (10, 6, 4, 4)
    docs.change_status(db_session, bus, second, "delivered")
    assert billing.fulfilment(db_session, order)["state"] == "complete"


def _received_reception(db, bus, world, qty=10, price=600.0):
    po = docs.create_document(db, bus, world.company.id, DocumentInput(kind=K.PURCHASE_ORDER, supplier_id=world.supplier_a.id, lines=[LineInput(product_id=world.product.id, quantity=qty, unit_price=price)]))
    for s in ("sent", "confirmed"):
        docs.change_status(db, bus, po, s)
    reception = docs.derive_document(db, bus, po, K.RECEPTION)
    docs.change_status(db, bus, reception, "received")
    return po, reception


def test_nonconformity_opens_one_risk_and_a_supplier_claim_for_those_units(db_session, bus, world):
    po, reception = _received_reception(db_session, bus, world)
    line = reception.lines[0]
    result = billing.report_nonconformity(db_session, bus, reception, line.id, 2, "Emballage endommagé")
    assert result["risk_created"]
    again = billing.report_nonconformity(db_session, bus, reception, line.id, 3, "Emballage endommagé, 3 unités")
    assert not again["risk_created"]
    assert db_session.query(Risk).filter(Risk.title == f"Non-conformité — {reception.number}").count() == 1
    with pytest.raises(billing.BillingError):
        billing.report_nonconformity(db_session, bus, reception, line.id, 50, "trop")
    assert billing.fulfilment(db_session, po)["nonconforming_total"] == 3

    claim = docs.derive_document(db_session, bus, reception, K.SUPPLIER_CREDIT_NOTE)
    assert claim.status == "requested" and [ln.quantity for ln in claim.lines] == [3] and claim.lines[0].unit_price == 600.0
    # The supplier invoice for the PO, approved, then the claim confirmed and imputed on it.
    invoice = docs.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    docs.change_status(db_session, bus, invoice, "approved")
    with pytest.raises(billing.BillingError):
        billing.apply_credit_note(db_session, bus, claim)  # not confirmed by the supplier yet
    docs.change_status(db_session, bus, claim, "confirmed")
    app = billing.apply_credit_note(db_session, bus, claim)
    assert app.applied_amount == 1800 and billing.settlement(db_session, invoice)["remaining"] == 6000 - 1800
    supplier_account = billing.party_account(db_session, world.company.id, supplier_id=world.supplier_a.id)
    assert supplier_account["balance"] == 4200
    _balance_invariant(supplier_account)


def test_unapproved_supplier_invoice_cannot_be_paid(db_session, bus, world):
    po, _ = _received_reception(db_session, bus, world)
    invoice = docs.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    with pytest.raises(billing.BillingError):
        billing.record_payment(db_session, bus, world.company.id, amount=100, invoice=invoice)
    docs.change_status(db_session, bus, invoice, "approved")
    billing.record_payment(db_session, bus, world.company.id, amount=6000, invoice=invoice)
    assert invoice.status == "paid"


def test_treasury_counts_only_what_remains(db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)  # 12 000
    billing.record_payment(db_session, bus, world.company.id, amount=8000, invoice=invoice)
    flows = [f for f in treasury_overview(db_session, world.company.id)["upcoming"] if f.get("document_id") == invoice.id]
    assert sum(f["amount"] for f in flows) == pytest.approx(4000)


# --- API and permissions ----------------------------------------------------------------------


def test_permissions_on_billing_actions(session_factory, db_session, bus, world):
    _, invoice = _confirmed_invoice(db_session, bus, world)
    cn = _credit_note(db_session, bus, invoice)
    profiles = {role: UserProfile(company_id=world.company.id, name=role.value, role=role, access_grants=[], access_revokes=[]) for role in (Role.DIRECTOR, Role.SALES, Role.OPERATIONS)}
    db_session.add_all(profiles.values())
    db_session.commit()
    h = {role: {"X-User-Id": str(p.id)} for role, p in profiles.items()}
    with api_client(session_factory) as client:
        assert client.post("/billing/payments", json={"invoice_id": str(invoice.id), "amount": 100}, headers=h[Role.SALES]).status_code == 403
        assert client.post("/billing/payments", json={"invoice_id": str(invoice.id), "amount": 100}, headers=h[Role.DIRECTOR]).status_code == 200
        assert client.get(f"/billing/accounts/customer/{world.customer.id}", headers=h[Role.SALES]).status_code == 200
        # The customer's answer is recorded by sales; the validation is a finance-domain approval.
        assert client.post(f"/documents/{cn.id}/status", json={"status": "submitted"}, headers=h[Role.SALES]).status_code == 200
        assert client.post(f"/documents/{cn.id}/status", json={"status": "accepted"}, headers=h[Role.SALES]).status_code == 200
        assert client.post(f"/documents/{cn.id}/status", json={"status": "validated"}, headers=h[Role.DIRECTOR]).status_code == 400
        task = session_factory().query(Task).filter_by(related_entity_id=cn.id, pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION).one()
        assert client.post(f"/actions/tasks/{task.id}/approve", headers=h[Role.SALES]).status_code == 403
        assert client.post(f"/actions/tasks/{task.id}/approve", headers=h[Role.DIRECTOR]).status_code == 200
        assert client.post(f"/billing/credit-notes/{cn.id}/apply", headers=h[Role.SALES]).status_code == 403
        assert client.post(f"/billing/credit-notes/{cn.id}/apply", headers=h[Role.DIRECTOR]).status_code == 200
        assert client.post(f"/billing/credit-notes/{cn.id}/apply", headers=h[Role.DIRECTOR]).status_code == 400
        detail = client.get(f"/documents/{invoice.id}", headers=h[Role.DIRECTOR]).json()
        assert detail["settlement"]["credited"] == 1000 and detail["settlement"]["paid"] == 100
        actions = client.get(f"/objects/commercial_document/{invoice.id}/context", headers=h[Role.DIRECTOR]).json()["actions"]
        assert not any(a["key"] in {"status:paid", "status:partially_paid"} for a in actions)


def test_nonconformity_permission(session_factory, db_session, bus, world):
    _, reception = _received_reception(db_session, bus, world)
    sales = UserProfile(company_id=world.company.id, name="s", role=Role.SALES, access_grants=[], access_revokes=[])
    ops = UserProfile(company_id=world.company.id, name="o", role=Role.OPERATIONS, access_grants=[], access_revokes=[])
    db_session.add_all([sales, ops])
    db_session.commit()
    body = {"line_id": str(reception.lines[0].id), "quantity": 1, "note": "Rayure"}
    with api_client(session_factory) as client:
        assert client.post(f"/billing/documents/{reception.id}/nonconformity", json=body, headers={"X-User-Id": str(sales.id)}).status_code == 403
        assert client.post(f"/billing/documents/{reception.id}/nonconformity", json=body, headers={"X-User-Id": str(ops.id)}).status_code == 200
    assert db_session.get(CommercialDocument, reception.id) is not None
