from data.seed import seed
from app.core.entities import (
    BusinessContext,
    Communication,
    Company,
    Contact,
    Customer,
    Opportunity,
    Product,
    Risk,
    RiskSeverity,
    Supplier,
    Task,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.event_bus import build_event_bus


def test_seed_creates_a_coherent_dataset(db_session, session_factory):
    result = seed(db_session, build_event_bus(session_factory))
    assert result["skipped"] is False

    company = db_session.query(Company).one()
    suppliers = db_session.query(Supplier).all()
    products = db_session.query(Product).all()
    customers = db_session.query(Customer).all()
    transactions = db_session.query(Transaction).all()

    assert len(suppliers) == 4
    assert len(products) == 6
    assert len(customers) == 3
    assert len(transactions) >= 20  # enough rows for baseline-vs-recent trend comparisons

    business_context = db_session.query(BusinessContext).filter_by(company_id=company.id).one()
    assert business_context.monitored_domains == ["procurement", "finance", "sales"]
    assert business_context.stated_objectives is not None

    supplier_ids = {s.id for s in suppliers}
    customer_ids = {c.id for c in customers}
    assert all(s.company_id == company.id for s in suppliers)
    assert all(p.supplier_id in supplier_ids for p in products)
    assert all(t.company_id == company.id for t in transactions)
    # Every transaction is tied to a supplier (purchase side) or a customer
    # (sales side), never neither -- this dataset has both, unlike step 3's.
    assert all((t.supplier_id in supplier_ids) or (t.customer_id in customer_ids) for t in transactions)
    assert any(t.customer_id is not None for t in transactions)


def test_seed_produces_the_intended_causal_chains_via_the_real_pipelines(db_session, session_factory):
    """The seed doesn't insert Risks/Opportunities directly -- it replays the
    real Procurement/Intelligence pipelines. This test is the proof that the
    engineered anomalies are actually strong enough to be detected by the
    real rules, not just plausible-looking on paper."""

    seed(db_session, build_event_bus(session_factory))

    risks = {r.title: r for r in db_session.query(Risk).all()}
    opportunities = {o.title: o for o in db_session.query(Opportunity).all()}

    from app.intelligence.risks.kinds import CUSTOMER_DECLINE, GROWING_CUSTOMER, MARGIN_DETERIORATION, SUPPLIER_COST_INCREASE, SUPPLIER_PERFORMANCE

    # Generated titles are French (decision #56).
    assert any(SUPPLIER_COST_INCREASE.matches(title) and title.startswith("Hausse") for title in risks)  # reactive chain (Sensor Module)
    assert any(MARGIN_DETERIORATION.matches(title) for title in risks)  # Steel Frame Assembly
    assert any(SUPPLIER_PERFORMANCE.matches(title) for title in risks)  # Iberia Logistics Parts
    assert any(CUSTOMER_DECLINE.matches(title) and "BrightWorks" in title for title in risks)
    assert any(GROWING_CUSTOMER.matches(title) and "Metroline" in title for title in opportunities)

    # Vantix Group's flat order pattern is the "ignore routine" control case:
    # it must not trigger anything.
    assert not any("Vantix" in title for title in risks)
    assert not any("Vantix" in title for title in opportunities)

    # The reactive chain also produces a pending Task, same as before step 12.
    assert db_session.query(Task).count() >= 1

    assert any(r.severity == RiskSeverity.HIGH for r in risks.values())


def test_seed_is_idempotent(db_session, session_factory):
    bus = build_event_bus(session_factory)
    seed(db_session, bus)
    second = seed(db_session, bus)

    assert second["skipped"] is True
    assert db_session.query(Company).count() == 1


def test_seed_uses_the_real_invoice_and_paid_status_enum_values(db_session, session_factory):
    """Step 23B: TransactionType.INVOICE and TransactionStatus.PAID existed
    in the schema since step 2 but no seed data ever used them (a real gap
    the step 23 audit found) -- Finance now has real payment-status data to
    show, on the supplier/cost side so `compute_margin_trend` (which already
    treats INVOICE as a cost-side document) isn't double-counted."""

    seed(db_session, build_event_bus(session_factory))

    invoices = db_session.query(Transaction).filter_by(type=TransactionType.INVOICE).all()
    assert len(invoices) >= 1
    assert all(t.supplier_id is not None and t.customer_id is None for t in invoices)
    assert any(t.status == TransactionStatus.PAID for t in invoices)
    assert any(t.status == TransactionStatus.CONFIRMED for t in invoices)


def test_seed_tells_a_cross_domain_story_beyond_finance_procurement_sales(db_session, session_factory):
    """Step 27: Marketing/HR/Direction have no Intelligence engine of their
    own, so their "life of the company" content is real, seeded Communication
    rows (never something an AI pipeline claims to have detected) -- and real
    Contacts so a Supplier/Customer detail page can offer an actual person to
    contact, not just a company name."""

    seed(db_session, build_event_bus(session_factory))

    channel_details = {c.channel_detail for c in db_session.query(Communication).all()}
    assert {"campaign_report", "agency_proposal", "contract_signed", "employee_idea", "process_feedback", "price_revision"} <= channel_details

    contacts = db_session.query(Contact).all()
    assert len(contacts) >= 2
    assert all(c.email is not None for c in contacts)
    assert any(c.related_entity_type is not None and c.related_entity_id is not None for c in contacts)
