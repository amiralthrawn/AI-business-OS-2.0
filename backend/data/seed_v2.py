"""V2 demonstration data, layered on top of the V1 seed (data/seed.py).

Replays real V2 workflows through the services (never inserts rows
directly), on the V1 demo entities, so every V2 relation is visible end to
end in the running app:

  Deal 1 -- complete, and LESS profitable than planned:
     DEM (Metroline Corp) -> DEV (sent, accepted) -> CMD (confirmed)
       -> DA -> 2 supplier quotes (Northline Steel, Pacific Components)
       -> BC (Northline, estimated transport 300-450 EUR)
       -> REC (received 4 days after the promised date)
       -> FFO (approved: higher unit price, actual transport 520 EUR)
  Deal 2 -- in progress: a quote sent 9 days ago (follow-up due), a
     supplier consultation with one quote received and one still awaited.
  Deal 3 -- a prospect request, not yet quoted.
  + supplier terms for a second supplier, the three kinds of stock, and
    three user profiles (one per main role) for the role switcher.

Idempotent: does nothing if the company already has commercial documents.
Usable on a fresh seed (`run()` below) or on an existing V1 database
(`python -m data.seed_v2`).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.catalog.service import ensure_preferred_supplier_terms, upsert_product_supplier, upsert_stock_position
from app.core.entities import (
    CommercialDocument,
    Company,
    Contact,
    CostKind,
    Customer,
    DocumentKind,
    Product,
    Role,
    StockKind,
    Supplier,
    UserProfile,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.objects.links import create_link
from app.transactions import service
from app.transactions.service import DocumentInput, LineInput, NewCustomer

K = DocumentKind


def _by_name(session: Session, model, company: Company, name: str):
    return session.query(model).filter_by(company_id=company.id, name=name).first()


def seed_v2_demo(session: Session, event_bus: EventBus, company: Company | None = None) -> dict:
    company = company or session.query(Company).first()
    if company is None:
        return {"skipped": True, "reason": "no company"}
    if session.query(CommercialDocument.id).filter_by(company_id=company.id).first() is not None:
        return {"skipped": True, "reason": "V2 documents already present"}

    northline = _by_name(session, Supplier, company, "Northline Steel")
    pacific = _by_name(session, Supplier, company, "Pacific Components")
    iberia = _by_name(session, Supplier, company, "Iberia Logistics Parts")
    steel_frame = _by_name(session, Product, company, "Steel Frame Assembly")
    control_board = _by_name(session, Product, company, "Control Board Rev C")
    sensor = _by_name(session, Product, company, "Sensor Module")
    metroline = _by_name(session, Customer, company, "Metroline Corp")
    brightworks = _by_name(session, Customer, company, "BrightWorks Ltd")
    if not all([northline, pacific, iberia, steel_frame, control_board, sensor, metroline, brightworks]):
        return {"skipped": True, "reason": "V1 demo entities not found"}

    now = datetime.now(timezone.utc)
    ensure_preferred_supplier_terms(session, company.id)

    # --- Catalog: list prices, a second supplier per product, declared terms ---
    steel_frame.sale_price, control_board.sale_price, sensor.sale_price = 610.0, 139.0, 98.0
    steel_frame.unit, control_board.unit, sensor.unit = "unité", "unité", "unité"
    upsert_product_supplier(session, steel_frame, northline.id, {"lead_time_min_days": 10, "lead_time_max_days": 14, "moq": 10, "spq": 5, "payment_terms": "30 jours fin de mois", "country_of_origin": "DE", "certifications": ["ISO 9001"]})
    upsert_product_supplier(session, steel_frame, pacific.id, {"unit_price": 455.0, "lead_time_min_days": 6, "lead_time_max_days": 9, "moq": 20, "payment_terms": "45 jours", "country_of_origin": "TW", "certifications": ["ISO 9001", "ISO 14001"]})
    upsert_product_supplier(session, control_board, pacific.id, {"lead_time_min_days": 15, "lead_time_max_days": 25, "spq": 10, "country_of_origin": "TW"})
    upsert_product_supplier(session, control_board, iberia.id, {"unit_price": 104.0, "lead_time_min_days": 7, "lead_time_max_days": 10, "country_of_origin": "ES", "payment_terms": "30 jours"})

    upsert_stock_position(session, event_bus, product=steel_frame, kind=StockKind.PHYSICAL, quantity=12, basis=ValueBasis.OBSERVED, location="Entrepôt Lyon", source="manual")
    upsert_stock_position(session, event_bus, product=steel_frame, kind=StockKind.SUPPLIER, supplier_id=pacific.id, quantity=60, basis=ValueBasis.DECLARED, source="manual")
    upsert_stock_position(session, event_bus, product=control_board, kind=StockKind.PHYSICAL, quantity=4, basis=ValueBasis.OBSERVED, location="Entrepôt Lyon")
    upsert_stock_position(session, event_bus, product=control_board, kind=StockKind.POTENTIAL, quantity=200, basis=ValueBasis.ESTIMATED, location="Place de marché en ligne", source="manual")
    session.commit()

    contact_of = {
        c.related_entity_id: c
        for c in session.query(Contact).filter(Contact.company_id == company.id, Contact.email.isnot(None)).all()
        if c.related_entity_id is not None
    }

    # --- Deal 1: complete, less profitable than planned ---
    request = service.create_document(
        session, event_bus, company.id,
        DocumentInput(
            kind=K.CUSTOMER_REQUEST, customer_id=metroline.id, contact_id=getattr(contact_of.get(metroline.id), "id", None),
            title="Châssis ligne d'assemblage B", external_reference="MET-RFQ-2231",
            lines=[LineInput(product_id=steel_frame.id, quantity=40)],
        ),
    )  # fmt: skip
    quote = service.derive_document(session, event_bus, request, K.CUSTOMER_QUOTE)
    service.change_status(session, event_bus, quote, "sent", occurred_at=now - timedelta(days=40))
    order = service.derive_document(session, event_bus, quote, K.CUSTOMER_ORDER)
    service.update_document(session, order, {"external_reference": "PO-MET-88412", "due_at": now - timedelta(days=5)})
    service.change_status(session, event_bus, order, "confirmed", occurred_at=now - timedelta(days=36))

    pr = service.derive_document(session, event_bus, order, K.PURCHASE_REQUEST)
    rfq_north = service.derive_document(session, event_bus, pr, K.SUPPLIER_QUOTE, supplier_id=northline.id)
    service.update_line(session, rfq_north, rfq_north.lines[0].id, {"unit_price": 420.0, "lead_time_min_days": 10, "lead_time_max_days": 14, "lead_time_basis": ValueBasis.DECLARED})
    service.add_cost_item(session, rfq_north, kind=CostKind.TRANSPORT, amount_min=300, amount_max=450, basis=ValueBasis.ESTIMATED, label="Transport routier (estimation)")
    service.change_status(session, event_bus, rfq_north, "received", occurred_at=now - timedelta(days=34))
    rfq_pacific = service.derive_document(session, event_bus, pr, K.SUPPLIER_QUOTE, supplier_id=pacific.id)
    service.update_line(session, rfq_pacific, rfq_pacific.lines[0].id, {"unit_price": 455.0, "lead_time_min_days": 6, "lead_time_max_days": 9, "lead_time_basis": ValueBasis.DECLARED})
    service.change_status(session, event_bus, rfq_pacific, "received", occurred_at=now - timedelta(days=34))
    service.change_status(session, event_bus, rfq_pacific, "declined")

    po = service.derive_document(session, event_bus, rfq_north, K.PURCHASE_ORDER)
    service.update_document(session, po, {"due_at": now - timedelta(days=22), "external_reference": "NS-SO-55190"})
    service.change_status(session, event_bus, po, "sent", occurred_at=now - timedelta(days=33))
    service.change_status(session, event_bus, po, "confirmed", occurred_at=now - timedelta(days=32))
    reception = service.derive_document(session, event_bus, po, K.RECEPTION)
    service.change_status(session, event_bus, reception, "received", occurred_at=now - timedelta(days=18))
    service.change_status(session, event_bus, po, "received", occurred_at=now - timedelta(days=18))
    supplier_invoice = service.derive_document(session, event_bus, po, K.SUPPLIER_INVOICE)
    service.update_document(session, supplier_invoice, {"external_reference": "NS-INV-20931"})
    service.update_line(session, supplier_invoice, supplier_invoice.lines[0].id, {"unit_price": 447.0})
    service.add_cost_item(session, supplier_invoice, kind=CostKind.TRANSPORT, amount_min=520, amount_max=520, basis=ValueBasis.OBSERVED, label="Transport routier (facturé)", reference="NS-INV-20931")
    service.change_status(session, event_bus, supplier_invoice, "approved", occurred_at=now - timedelta(days=12))
    delivery = service.derive_document(session, event_bus, order, K.CUSTOMER_DELIVERY)
    service.change_status(session, event_bus, delivery, "shipped", occurred_at=now - timedelta(days=11))
    service.change_status(session, event_bus, delivery, "delivered", occurred_at=now - timedelta(days=9))
    service.change_status(session, event_bus, order, "delivered", occurred_at=now - timedelta(days=9))

    # Link the supplier's real renegotiation email (V1 connector data) to the deal.
    from app.core.entities import Communication, RelatedEntityType

    northline_email = (
        session.query(Communication)
        .filter_by(company_id=company.id, related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=northline.id)
        .order_by(Communication.occurred_at.desc())
        .first()
    )
    if northline_email is not None:
        create_link(session, company_id=company.id, source_type="communication", source_id=northline_email.id, target_type="commercial_document", target_id=supplier_invoice.id, relation="concerns", origin="manual")

    # --- Deal 2: in progress ---
    request2 = service.create_document(
        session, event_bus, company.id,
        DocumentInput(kind=K.CUSTOMER_REQUEST, customer_id=brightworks.id, contact_id=getattr(contact_of.get(brightworks.id), "id", None), title="Cartes de contrôle — lot pilote", lines=[LineInput(product_id=control_board.id, quantity=25)]),
    )  # fmt: skip
    quote2 = service.derive_document(session, event_bus, request2, K.CUSTOMER_QUOTE)
    service.update_document(session, quote2, {"due_at": now + timedelta(days=21)})
    service.change_status(session, event_bus, quote2, "sent", occurred_at=now - timedelta(days=9))
    pr2 = service.derive_document(session, event_bus, request2, K.PURCHASE_REQUEST)
    rfq_iberia = service.derive_document(session, event_bus, pr2, K.SUPPLIER_QUOTE, supplier_id=iberia.id)
    service.update_line(session, rfq_iberia, rfq_iberia.lines[0].id, {"unit_price": 101.5, "lead_time_min_days": 8, "lead_time_max_days": 12, "lead_time_basis": ValueBasis.DECLARED})
    service.add_cost_item(session, rfq_iberia, kind=CostKind.TRANSPORT, amount_min=120, amount_max=180, basis=ValueBasis.ESTIMATED, label="Messagerie (estimation)")
    service.change_status(session, event_bus, rfq_iberia, "received", occurred_at=now - timedelta(days=3))
    rfq_pacific2 = service.derive_document(session, event_bus, pr2, K.SUPPLIER_QUOTE, supplier_id=pacific.id)
    rfq_pacific2.issued_at = now - timedelta(days=7)
    session.commit()

    # --- Deal 3: a prospect's request, not quoted yet ---
    service.create_document(
        session, event_bus, company.id,
        DocumentInput(kind=K.CUSTOMER_REQUEST, new_customer=NewCustomer(name="Solaris Events", country="FR"), title="Structures pour salon professionnel", lines=[LineInput(product_id=steel_frame.id, quantity=8), LineInput(product_id=sensor.id, quantity=16)]),
    )  # fmt: skip

    # --- One profile per main role (the role switcher in the top bar) ---
    if session.query(UserProfile.id).filter_by(company_id=company.id).first() is None:
        session.add_all(
            [
                UserProfile(company_id=company.id, name="Camille Laurent", role=Role.DIRECTOR),
                UserProfile(company_id=company.id, name="Hugo Martin", role=Role.SALES),
                UserProfile(company_id=company.id, name="Inès Moreau", role=Role.PROCUREMENT),
            ]
        )
        session.commit()

    return {"skipped": False, "documents": session.query(CommercialDocument).filter_by(company_id=company.id).count(), "order": order.number}


def run() -> None:
    from app.database import SessionLocal
    from app.event_bus import build_event_bus

    session = SessionLocal()
    try:
        result = seed_v2_demo(session, build_event_bus())
        print("V2 demo data:", result)
    finally:
        session.close()


if __name__ == "__main__":
    run()
