"""Seed script for the step-12 demo dataset: one Company, Suppliers, Products,
Customers and ~6 months of Transactions engineered around several coherent
causal chains (see brain/step12_dataset.md for why this dataset looks like
this). After loading the historical data, the seed replays the SAME
Procurement/Intelligence pipelines the API uses in production -- it doesn't
insert Risks/Opportunities/Tasks directly -- so the demo state is produced by
the real system, not by shortcuts.

Assumes the schema already exists (run `alembic upgrade head` first)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.entities import (
    Communication,
    CommunicationDirection,
    Company,
    Contact,
    Customer,
    Document,
    Product,
    RelatedEntityType,
    Supplier,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.ai.capabilities import capability_registry
from app.ai.llm import get_llm_client
from app.business_context.service import BusinessContextService
from app.connectors.calendar.mock import MockCalendarProvider
from app.connectors.email.mock import MockEmailProvider
from app.connectors.ingestion import ingest_calendar, ingest_email, ingest_website
from app.connectors.website.mock import MockWebsiteProvider
from app.core.events.bus import EventBus
from app.database import SessionLocal
from app.decision.engine import run_decision_sweep
from app.domains.procurement.service import ProcurementService
from app.event_bus import build_event_bus
from app.intelligence.monitoring import run_monitoring_sweep
from app.interpretation.engine import run_interpretation_sweep
from app.observation import observable_registry
from app.observation.engine import run_observation_sweep


def _po(company, supplier, product, days_ago, unit_cost, qty, expected_delay_days=None, now=None):
    occurred_at = now - timedelta(days=days_ago)
    expected_at = occurred_at - timedelta(days=expected_delay_days) if expected_delay_days is not None else None
    return Transaction(
        company_id=company.id,
        supplier_id=supplier.id,
        product_id=product.id,
        type=TransactionType.PURCHASE_ORDER,
        status=TransactionStatus.CONFIRMED,
        amount=round(unit_cost * qty, 2),
        currency="EUR",
        occurred_at=occurred_at,
        expected_at=expected_at,
    )


def _so(company, customer, product, days_ago, unit_price, qty, now=None):
    return Transaction(
        company_id=company.id,
        customer_id=customer.id,
        product_id=product.id,
        type=TransactionType.SALES_ORDER,
        status=TransactionStatus.CONFIRMED,
        amount=round(unit_price * qty, 2),
        currency="EUR",
        occurred_at=now - timedelta(days=days_ago),
    )


def _invoice(company, supplier, product, days_ago, amount, status, now=None):
    """A formal supplier invoice for an already-delivered purchase -- uses
    `TransactionType.INVOICE`/`TransactionStatus.PAID`, both declared in the
    schema since step 2 but never previously seeded (a real gap the step 23
    audit found; see brain/business_domains.md). Kept on the supplier
    (cost) side deliberately: `compute_margin_trend` already treats
    `TransactionType.INVOICE` as a cost-side document alongside
    `PURCHASE_ORDER` (see `app/core/analytics.py`) -- a customer-side
    invoice would have been silently double-counted as a cost there."""

    return Transaction(
        company_id=company.id,
        supplier_id=supplier.id,
        product_id=product.id,
        type=TransactionType.INVOICE,
        status=status,
        amount=amount,
        currency="EUR",
        occurred_at=now - timedelta(days=days_ago),
    )


def seed(session: Session, event_bus: EventBus) -> dict:
    if session.query(Company).first() is not None:
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    company = Company(name="Acme Manufacturing", industry="Industrial equipment")
    session.add(company)
    session.flush()

    # A generic starting Business Context -- see brain/business_context.md.
    # Nothing here is learned yet; it's the declared, human-editable default
    # the OS would ask for during onboarding. `declared_baselines` shows the
    # "declared target != observed history" distinction explicitly: this
    # company considers 30% a good margin (which Steel Frame Assembly's real
    # history falls well short of), a +/-5% revenue swing per customer
    # normal (which Metroline's real growth and BrightWorks' real decline
    # both clear by a wide margin -- see app.interpretation.engine), and a
    # 3-day response time normal for external messages (step 22 -- see
    # brain/external_data_intelligence.md).
    BusinessContextService(session).update(
        company.id,
        company_size="51-200",
        country="DE",
        business_model="B2B manufacturing",
        monitored_domains=["procurement", "finance", "sales"],
        home_focus=["priorities", "risks", "opportunities"],
        notification_level="normal",
        stated_objectives="Protect margin on core products and reduce single-supplier dependency.",
        declared_baselines={
            "margin_pct": 0.30,
            "customer_revenue_variation_pct": 0.05,
            "unanswered_message_age_days": 3,
        },
    )

    northline, pacific, iberia, coastal = (
        Supplier(company_id=company.id, name="Northline Steel", country="DE"),
        Supplier(company_id=company.id, name="Pacific Components", country="TW"),
        Supplier(company_id=company.id, name="Iberia Logistics Parts", country="ES"),
        # A brand-new supplier relationship (Chain 4, for the Interpretation
        # Engine's "insight" MVP case, see brain/interpretation_engine.md):
        # only 3 shipments on record, all badly late -- a real signal, but on
        # too thin a history to confidently call it a Risk yet.
        Supplier(company_id=company.id, name="Coastal Metal Supply", country="PT"),
    )
    session.add_all([northline, pacific, iberia, coastal])
    session.flush()

    steel_frame, steel_bracket, control_board, sensor_module, hydraulic_hose, coastal_fastener_kit = (
        Product(company_id=company.id, supplier_id=northline.id, name="Steel Frame Assembly", sku="STL-001", unit_cost=420.0),
        Product(company_id=company.id, supplier_id=northline.id, name="Steel Bracket Set", sku="STL-002", unit_cost=38.5),
        Product(company_id=company.id, supplier_id=pacific.id, name="Control Board Rev C", sku="PCB-010", unit_cost=95.0),
        Product(company_id=company.id, supplier_id=pacific.id, name="Sensor Module", sku="PCB-011", unit_cost=61.0),
        Product(company_id=company.id, supplier_id=iberia.id, name="Hydraulic Hose 2m", sku="HYD-020", unit_cost=27.0),
        Product(company_id=company.id, supplier_id=coastal.id, name="Coastal Fastener Kit", sku="CST-001", unit_cost=15.0),
    )
    session.add_all([steel_frame, steel_bracket, control_board, sensor_module, hydraulic_hose, coastal_fastener_kit])
    session.flush()

    metroline, brightworks, vantix = (
        Customer(company_id=company.id, name="Metroline Corp", country="FR"),
        Customer(company_id=company.id, name="BrightWorks Ltd", country="GB"),
        Customer(company_id=company.id, name="Vantix Group", country="NL"),
    )
    session.add_all([metroline, brightworks, vantix])
    session.flush()

    transactions: list[Transaction] = []

    # --- Chain 1: gradual supplier cost creep -> margin deterioration ------
    # Steel Frame Assembly unit cost creeps up ~10% over 6 months while
    # aggregate selling price/volume stays roughly flat -> margin compresses.
    for days_ago, unit_cost in [(165, 420.0), (135, 425.0), (105, 435.0), (75, 455.0), (45, 470.0), (15, 490.0)]:
        transactions.append(_po(company, northline, steel_frame, days_ago, unit_cost, 50, now=now))

    # Three customers buying the same product with three different trajectories:
    # growing, declining, and stable (the "ignore routine" control case).
    for days_ago, qty in [(160, 15), (100, 20), (50, 28), (10, 35)]:
        transactions.append(_so(company, metroline, steel_frame, days_ago, 650.0, qty, now=now))
    for days_ago, qty in [(160, 30), (100, 24), (50, 14), (10, 8)]:
        transactions.append(_so(company, brightworks, steel_frame, days_ago, 650.0, qty, now=now))
    for days_ago, qty in [(160, 20), (100, 22), (50, 20), (10, 21)]:
        transactions.append(_so(company, vantix, steel_frame, days_ago, 650.0, qty, now=now))

    # --- Chain 2: supplier delivery performance deterioration --------------
    # Cost stays flat; the promise-to-delivery gap grows steadily.
    for days_ago, delay in [(165, 1.0), (135, 1.5), (105, 1.0), (75, 4.0), (45, 5.0), (15, 5.5)]:
        transactions.append(_po(company, iberia, hydraulic_hose, days_ago, 27.0, 300, expected_delay_days=delay, now=now))

    # --- Chain 3 setup: stable Sensor Module history, the spike itself is
    # triggered live below through the real Procurement pipeline. -----------
    for days_ago in (90, 60, 30):
        transactions.append(_po(company, pacific, sensor_module, days_ago, 61.0, 40, now=now))

    # --- Chain 4: a brand-new supplier, consistently badly late, too little
    # history to be a confirmed Risk yet -- see the Business Context comment
    # above and brain/interpretation_engine.md.
    for days_ago, delay in [(60, 6.0), (40, 6.5), (20, 7.0)]:
        transactions.append(_po(company, coastal, coastal_fastener_kit, days_ago, 15.0, 50, expected_delay_days=delay, now=now))

    # --- Routine, low-volume history for the two products not central to any
    # chain -- present so the dataset isn't suspiciously empty around them. --
    transactions.append(_po(company, northline, steel_bracket, 20, 38.5, 120, now=now))
    transactions.append(_po(company, pacific, control_board, 15, 95.0, 60, now=now))

    # --- Invoicing: a paid invoice and an outstanding one, using the real
    # schema values (Phase 11) so the Finance view has actual payment-status
    # data to show, not just purchase/sales orders. On the two routine,
    # low-volume products so real payment-status data exists without
    # perturbing any of the four detected anomaly chains above. -------------
    transactions.append(_invoice(company, northline, steel_bracket, 5, 4620.0, TransactionStatus.PAID, now=now))
    transactions.append(_invoice(company, pacific, control_board, 3, 5700.0, TransactionStatus.CONFIRMED, now=now))

    session.add_all(transactions)
    session.flush()

    # --- A little Documents/Communications realism (not central to any rule,
    # but the Data Core's cross-entity linking should show real usage). ------
    session.add_all(
        [
            Document(
                company_id=company.id,
                title="Invoice INV-2041 - Pacific Components",
                document_type="invoice",
                related_entity_type=RelatedEntityType.SUPPLIER,
                related_entity_id=pacific.id,
            ),
            Communication(
                company_id=company.id,
                channel="email",
                direction=CommunicationDirection.OUTBOUND,
                subject="Contract renewal - Metroline Corp",
                body="Following up on the expanded order volume, proposing a renewed annual contract.",
                related_entity_type=RelatedEntityType.CUSTOMER,
                related_entity_id=metroline.id,
                occurred_at=now - timedelta(days=5),
            ),
        ]
    )

    # --- Step 27: real people at real Suppliers/Customers, so a detail page
    # can offer a real "Contacter" action instead of an anonymous entity. ----
    session.add_all(
        [
            Contact(
                company_id=company.id,
                name="Jean Dupont",
                role="Directeur des achats",
                email="jean.dupont@brightworks.co.uk",
                phone="+44 20 7946 0123",
                related_entity_type=RelatedEntityType.CUSTOMER,
                related_entity_id=brightworks.id,
            ),
            Contact(
                company_id=company.id,
                name="Ana Silva",
                role="Responsable commerciale",
                email="ana.silva@coastalmetal.pt",
                phone="+351 21 456 7890",
                related_entity_type=RelatedEntityType.SUPPLIER,
                related_entity_id=coastal.id,
            ),
        ]
    )

    # --- Step 27: "the company's own life" -- real Communication rows for
    # events an Intelligence rule will never cover (Marketing/HR/Direction
    # have no Observable/Interpretation of their own, and won't get one just
    # for demo color -- see brain/decisions.md). Each one is honestly what
    # it is: a real message, never something the AI "detected". Surfaced by
    # HomeService.get_company_narrative, grouped by `channel`/`channel_detail`
    # on the frontend -- never through the Observation/Decision pipeline.
    session.add_all(
        [
            Communication(
                company_id=company.id,
                channel="internal",
                channel_detail="campaign_report",
                direction=CommunicationDirection.OUTBOUND,
                subject="Campagne Septembre — résultats",
                body="La campagne Septembre génère 34% de demandes entrantes en plus par rapport au mois précédent.",
                occurred_at=now - timedelta(hours=14),
            ),
            Communication(
                company_id=company.id,
                channel="email",
                channel_detail="agency_proposal",
                direction=CommunicationDirection.INBOUND,
                subject="MediaOne — nouvelle proposition de campagne",
                body="Nous proposons une nouvelle campagne à -50% du tarif habituel, valable jusqu'à vendredi.",
                occurred_at=now - timedelta(days=1, hours=2),
            ),
            Communication(
                company_id=company.id,
                channel="email",
                channel_detail="contract_signed",
                direction=CommunicationDirection.INBOUND,
                subject="Contrat signé — Vantix Group",
                body="Le nouveau contrat annuel a été signé avec Vantix Group.",
                related_entity_type=RelatedEntityType.CUSTOMER,
                related_entity_id=vantix.id,
                occurred_at=now - timedelta(days=2),
            ),
            Communication(
                company_id=company.id,
                channel="internal",
                channel_detail="employee_idea",
                direction=CommunicationDirection.INBOUND,
                subject="Sarah (Marketing) — réutiliser les vidéos de la campagne",
                body="On pourrait réutiliser les vidéos de la campagne Septembre pour LinkedIn, sans nouveau tournage.",
                occurred_at=now - timedelta(hours=20),
            ),
            Communication(
                company_id=company.id,
                channel="internal",
                channel_detail="process_feedback",
                direction=CommunicationDirection.INBOUND,
                subject="Thomas (Production) — étape manuelle chronophage",
                body="On perd environ 20 minutes par commande à cause d'une étape manuelle qui pourrait être automatisée.",
                occurred_at=now - timedelta(days=3),
            ),
            Communication(
                company_id=company.id,
                channel="email",
                channel_detail="price_revision",
                direction=CommunicationDirection.INBOUND,
                subject="Coastal Metal Supply — révision tarifaire",
                body="Nous devons revoir nos tarifs de 8% à partir du mois prochain en raison de la hausse du coût des matières premières.",
                related_entity_type=RelatedEntityType.SUPPLIER,
                related_entity_id=coastal.id,
                occurred_at=now - timedelta(hours=6),
            ),
        ]
    )
    session.commit()

    # --- Replay the real pipelines instead of inserting Risks/Tasks directly.
    # Chain 3: a live 25% Sensor Module cost increase -> SupplierCostIncreased
    # -> RiskCreated -> TaskCreated, exactly as the API would produce it.
    ProcurementService(session, event_bus).record_supplier_cost_increase(
        supplier_id=pacific.id, product_id=sensor_module.id, new_unit_cost=76.25
    )

    # Chains 1, 2 and the customer trends: the monitoring sweep that a
    # scheduler would run periodically in production (see
    # app.intelligence.monitoring for why there's no scheduler here yet).
    monitoring_result = run_monitoring_sweep(session, event_bus)

    # External Connectivity Layer (app.connectors, step 21): ingests the
    # three Mock Providers' realistic datasets on top of the same seeded
    # company -- Communications/Documents/Contacts only, no Business Event.
    # Runs BEFORE the Observation sweep below (step 22): two of its
    # Observables read Communication rows directly (see
    # brain/external_data_intelligence.md), so the external data must exist
    # first for a sweep run right after seeding to see it.
    email_result = ingest_email(session, MockEmailProvider(), company.id)
    calendar_result = ingest_calendar(session, MockCalendarProvider(), company.id)
    website_result = ingest_website(session, MockWebsiteProvider(), company.id)

    # The Observation Engine (app.observation) runs alongside the older
    # per-metric monitoring sweep above -- both read the same Data Core, so
    # the demo dataset also produces real ObservationDetected Business
    # Events (including the Chain 1+2 cross-domain correlation, since Steel
    # Frame Assembly's margin issue and its own supplier Northline's
    # delivery performance are unrelated chains here, kept separate on
    # purpose -- see brain/observation_engine.md for a dataset note). Since
    # step 22, this also includes the two external-data Observables reading
    # the Communications just ingested above.
    observation_result = run_observation_sweep(session, event_bus, observable_registry, company.id)

    # The Interpretation Engine (app.interpretation) runs next: it reads the
    # ObservationDetected events the sweep above just published and turns
    # each into a structured Risk/Opportunity/Insight/Observation -- a
    # narrative and a classification only, no Task proposal at this layer
    # (see brain/interpretation_engine.md).
    interpretation_result = run_interpretation_sweep(
        session, event_bus, capability_registry, get_llm_client(), company.id
    )

    # The Decision Intelligence Engine (app.decision) runs last: it turns
    # each Interpretation into concrete options, trade-offs and a reasoned
    # recommendation, proposing a Task (PENDING_VALIDATION only) for the
    # confidently-recommended ones not already covered by the older
    # per-metric Risks/Opportunities above -- see brain/decision_intelligence.md.
    decision_result = run_decision_sweep(session, event_bus, capability_registry, get_llm_client(), company.id)

    return {
        "skipped": False,
        "suppliers": 4,
        "products": 6,
        "customers": 3,
        "transactions": len(transactions) + 1,  # +1 for the live cost-increase transaction
        "risks_created": monitoring_result["risks_created"],
        "opportunities_created": monitoring_result["opportunities_created"],
        "business_events_published": observation_result["business_events_published"],
        "observations_interpreted": interpretation_result["observations_interpreted"],
        "interpretations_by_type": interpretation_result["by_type"],
        "decisions_made": decision_result["decisions_made"],
        "actions_proposed": decision_result["actions_proposed"],
        "decisions_by_type": decision_result["by_type"],
        "emails_ingested": email_result.created,
        "calendar_events_ingested": calendar_result.created,
        "website_inquiries_ingested": website_result.created,
    }


def run() -> None:
    session = SessionLocal()
    try:
        bus = build_event_bus()
        result = seed(session, bus)
        if result["skipped"]:
            print("Seed already applied, skipping.")
        else:
            print(
                f"Seed applied: 1 company, {result['suppliers']} suppliers, {result['products']} products, "
                f"{result['customers']} customers, {result['transactions']} transactions, "
                f"{result['risks_created']} risks detected, {result['opportunities_created']} opportunities detected, "
                f"{result['business_events_published']} observation events published, "
                f"{result['observations_interpreted']} interpreted ({result['interpretations_by_type']}), "
                f"{result['decisions_made']} decisions made ({result['decisions_by_type']}), "
                f"{result['actions_proposed']} actions proposed. "
                f"Connectors: {result['emails_ingested']} emails, {result['calendar_events_ingested']} calendar events, "
                f"{result['website_inquiries_ingested']} website inquiries ingested."
            )
        # V2 business objects on top of the V1 demo (idempotent, data/seed_v2.py).
        from data.seed_v2 import seed_v2_demo

        print("V2 demo data:", seed_v2_demo(session, bus))
        from data.seed_v21 import seed_v21_demo

        print("V2.1 demo data:", seed_v21_demo(session, bus))
        # V2.2: payments, instalments, deliveries, credit notes (idempotent, data/seed_v22.py).
        from data.seed_v22 import seed_v22_demo

        print("V2.2 demo data:", seed_v22_demo(session, bus))
    finally:
        session.close()


if __name__ == "__main__":
    run()
