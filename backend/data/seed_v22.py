"""V2.2 demonstration data: payments, instalments, deliveries, credit notes and
supplier claims (brain/billing.md), layered on data/seed.py + seed_v2 + seed_v21.

SIMULATED and labelled as such: documents are created with source
"simulated", money movements with source "simulated", messages with source
"simulated_demo". Everything is replayed through the real services (status
changes, payments, HITL approvals, imputation) so balances, events and
statuses are exactly what the product computes -- nothing is written as a
finished number. Deliberately few objects, each with a different story:

Customers
  Metroline Corp       order delivered -> deposit paid, balance due; 2 frames
                       non-conforming -> credit note offered, ACCEPTED, validated
                       (HITL), imputed on the balance; supplier claim to
                       Northline CONFIRMED by the supplier (imputation pending)
  BrightWorks Ltd      12 000 € order, 3 instalments, 2 paid
  Vantix Group         invoice partly paid and LATE, invoice contested ->
                       credit note accepted, WAITING for internal validation;
                       a new order transmitted, not yet acknowledged
  Atelier Rhône        paid in full at order; delivery in transit; a price
  Industrie (new)      adjustment credit note imputed on a paid invoice ->
                       REFUND pending
  Helio Parc Énergie   delivered late, invoice fully paid, credit note REFUSED
  (new)                by the customer -> decision task; account up to date
  Nordic Rail          order acknowledged by the customer, not yet confirmed
  Services (new)
Suppliers
  Pacific Components   complete reception on time, invoice paid
  Coastal Metal Supply partial reception, rest expected, invoice to approve
  Iberia Logistics     reception late (not received)
  Northline Steel      non-conformity + credit note confirmed (above)
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.actions.executor import ActionExecutor
from app.actions.service import ActionsService
from app.billing import service as billing
from app.core.entities import (
    CommercialDocument,
    Communication,
    CommunicationDirection,
    Company,
    Contact,
    Customer,
    DocumentKind,
    Product,
    RelatedEntityType,
    Supplier,
    Task,
)
from app.core.events.bus import EventBus
from app.objects.graph import document_children
from app.objects.links import create_link
from app.transactions import service
from app.transactions.service import DocumentInput, LineInput

K = DocumentKind
SIM = "simulated"


def _by_name(session: Session, model, company: Company, name: str):
    return session.query(model).filter_by(company_id=company.id, name=name).first()


def _customer(session: Session, company: Company, name: str, country: str, contact: tuple[str, str]) -> Customer:
    customer = _by_name(session, Customer, company, name)
    if customer is None:
        customer = Customer(company_id=company.id, name=name, country=country, status="active", notes="Client de démonstration (données simulées).")
        session.add(customer)
        session.flush()
        session.add(Contact(company_id=company.id, name=contact[0], email=contact[1], related_entity_type=RelatedEntityType.CUSTOMER, related_entity_id=customer.id))
        session.commit()
    return customer


def _message(session: Session, company: Company, *, subject: str, body: str, when: datetime, party: Customer | Supplier, doc: CommercialDocument, key: str) -> Communication:
    is_customer = isinstance(party, Customer)
    msg = Communication(
        company_id=company.id, channel="email", direction=CommunicationDirection.INBOUND, status="received", subject=subject, body=body,
        occurred_at=when, source="simulated_demo", external_id=f"sim-v22-{key}",
        related_entity_type=RelatedEntityType.CUSTOMER if is_customer else RelatedEntityType.SUPPLIER, related_entity_id=party.id,
        from_address=f"contact@{party.name.lower().split()[0]}.example",
    )  # fmt: skip
    session.add(msg)
    session.commit()
    create_link(session, company_id=company.id, source_type="communication", source_id=msg.id, target_type="commercial_document", target_id=doc.id, relation="concerns", origin="system")
    return msg


def _order(session, bus, company, customer, lines, *, issued, title, statuses, due=None, ref=None) -> CommercialDocument:
    order = service.create_document(
        session, bus, company.id,
        DocumentInput(kind=K.CUSTOMER_ORDER, customer_id=customer.id, title=title, issued_at=issued, due_at=due, external_reference=ref, source=SIM, lines=lines),
    )  # fmt: skip
    for status, when in statuses:
        service.change_status(session, bus, order, status, occurred_at=when)
    return order


def _deliver(session, bus, order, *, planned, shipped=True, delivered_at=None, carrier=None, tracking=None, quantity=None) -> CommercialDocument:
    delivery = service.derive_document(session, bus, order, K.CUSTOMER_DELIVERY)
    delivery.source, delivery.due_at, delivery.carrier, delivery.tracking_number = SIM, planned, carrier, tracking
    if quantity is not None:
        delivery.lines[0].quantity = quantity
    session.commit()
    if shipped:
        service.change_status(session, bus, delivery, "shipped")
    if delivered_at is not None:
        service.change_status(session, bus, delivery, "delivered", occurred_at=delivered_at)
        # The order follows once everything it carried was delivered.
        if order.status == "confirmed" and billing.fulfilment(session, order)["state"] == "complete":
            service.change_status(session, bus, order, "delivered", occurred_at=delivered_at)
    return delivery


def _invoice(session, bus, order, *, issued, due, schedule=None) -> CommercialDocument:
    invoice = service.derive_document(session, bus, order, K.CUSTOMER_INVOICE)
    invoice.source, invoice.issued_at, invoice.due_at = SIM, issued, due
    session.commit()
    service.change_status(session, bus, invoice, "issued", occurred_at=issued)
    if order.status == "delivered":
        service.change_status(session, bus, order, "invoiced", occurred_at=issued)
    if schedule:
        billing.set_installments(session, bus, invoice, schedule)
    return invoice


def _credit(session, bus, source, *, lines, steps, title) -> CommercialDocument:
    cn = service.derive_document(session, bus, source, K.CUSTOMER_CREDIT_NOTE)
    cn.source, cn.title = SIM, title
    for ln in list(cn.lines):
        cn.lines.remove(ln)
    session.commit()
    for line in lines:
        service.add_line(session, cn, line)
    for status in steps:
        service.change_status(session, bus, cn, status)
    return cn


def _approve_validation(session, bus, cn) -> None:
    task = session.query(Task).filter_by(related_entity_id=cn.id, pending_action=billing.VALIDATE_CREDIT_NOTE_ACTION).first()
    ActionExecutor(ActionsService(session, bus)).approve(task.id)
    session.refresh(cn)


def seed_v22_demo(session: Session, event_bus: EventBus, company: Company | None = None) -> dict:
    company = company or session.query(Company).first()
    if company is None:
        return {"skipped": True, "reason": "no company"}
    if session.query(CommercialDocument.id).filter_by(company_id=company.id, kind=K.CUSTOMER_CREDIT_NOTE).first() is not None:
        return {"skipped": True, "reason": "V2.2 demo already present"}

    metroline = _by_name(session, Customer, company, "Metroline Corp")
    brightworks = _by_name(session, Customer, company, "BrightWorks Ltd")
    vantix = _by_name(session, Customer, company, "Vantix Group")
    northline = _by_name(session, Supplier, company, "Northline Steel")
    pacific = _by_name(session, Supplier, company, "Pacific Components")
    coastal = _by_name(session, Supplier, company, "Coastal Metal Supply")
    iberia = _by_name(session, Supplier, company, "Iberia Logistics Parts")
    frame = _by_name(session, Product, company, "Steel Frame Assembly")
    board = _by_name(session, Product, company, "Control Board Rev C")
    sensor = _by_name(session, Product, company, "Sensor Module")
    hose = _by_name(session, Product, company, "Hydraulic Hose 2m")
    fastener = _by_name(session, Product, company, "Coastal Fastener Kit")
    metro_order = session.query(CommercialDocument).filter_by(company_id=company.id, kind=K.CUSTOMER_ORDER, customer_id=metroline.id if metroline else None).first()
    if not all([metroline, brightworks, vantix, northline, pacific, coastal, iberia, frame, board, sensor, hose, fastener, metro_order]):
        return {"skipped": True, "reason": "V1/V2 demo entities not found"}

    now = datetime.now(timezone.utc)
    d = lambda days: now + timedelta(days=days)  # noqa: E731
    atelier = _customer(session, company, "Atelier Rhône Industrie", "FR", ("Julie Bernard", "julie.bernard@atelier-rhone.example"))
    helio = _customer(session, company, "Helio Parc Énergie", "FR", ("Marc Delorme", "m.delorme@helio-parc.example"))
    nordic = _customer(session, company, "Nordic Rail Services", "SE", ("Erik Lund", "erik.lund@nordicrail.example"))

    # --- Metroline: deposit + balance, non-conformity, credit note accepted -> validated -> imputed ---------
    delivery = next((doc for doc in (session.get(CommercialDocument, cid) for cid in document_children(session, metro_order.id)) if doc and doc.kind == K.CUSTOMER_DELIVERY), None)
    metro_invoice = _invoice(session, event_bus, metro_order, issued=d(-31), due=d(15), schedule=[
        {"due_at": d(-30), "amount": round(0.3 * billing.doc_total(metro_order), 2), "label": "Acompte 30 % à la commande"},
        {"due_at": d(15), "amount": round(0.7 * billing.doc_total(metro_order), 2), "label": "Solde à 45 jours"},
    ])  # fmt: skip
    billing.record_payment(session, event_bus, company.id, amount=round(0.3 * billing.doc_total(metro_order), 2), invoice=metro_invoice, occurred_at=d(-29), label="Virement Metroline — acompte", source=SIM)
    if delivery is not None and delivery.status == "delivered":
        billing.report_nonconformity(session, event_bus, delivery, delivery.lines[0].id, 2, "Soudure défectueuse sur 2 châssis")
    metro_credit = _credit(session, event_bus, delivery or metro_invoice, title="Geste commercial — 2 châssis non conformes",
                           lines=[LineInput(product_id=frame.id, description="Non-conformité : soudure défectueuse (2 châssis)", quantity=2, unit_price=500.0)],
                           steps=["submitted"])  # fmt: skip
    _message(session, company, subject=f"Accord sur l'avoir {metro_credit.number}", body="Bonjour,\nNous acceptons votre proposition d'avoir de 1 000 € pour les deux châssis non conformes.\nCordialement,\nMetroline Corp", when=d(-4), party=metroline, doc=metro_credit, key="metroline-accept")
    service.change_status(session, event_bus, metro_credit, "accepted")
    _approve_validation(session, event_bus, metro_credit)
    billing.apply_credit_note(session, event_bus, metro_credit, now=d(-2))

    # Supplier side: the defective frames came from Northline -> claim, confirmed by the supplier.
    reception = session.query(CommercialDocument).filter_by(company_id=company.id, kind=K.RECEPTION, supplier_id=northline.id).first()
    northline_claim = None
    if reception is not None and reception.status == "received":
        billing.report_nonconformity(session, event_bus, reception, reception.lines[0].id, 2, "Soudure défectueuse (constatée chez le client Metroline)")
        northline_claim = service.derive_document(session, event_bus, reception, K.SUPPLIER_CREDIT_NOTE)
        northline_claim.source, northline_claim.title = SIM, "Réclamation — 2 châssis non conformes"
        session.commit()
        _message(session, company, subject=f"Re: réclamation {northline_claim.number}", body="Bonjour,\nNous confirmons l'émission d'un avoir pour les deux châssis concernés.\nNorthline Steel — service qualité", when=d(-1), party=northline, doc=northline_claim, key="northline-confirm")
        service.change_status(session, event_bus, northline_claim, "confirmed")

    # --- BrightWorks: 12 000 € in three instalments, two paid ---------------------------------------------
    bw_order = _order(session, event_bus, company, brightworks, [LineInput(product_id=sensor.id, quantity=100, unit_price=120.0)], issued=d(-60), title="Modules capteurs — contrat annuel", ref="BW-PO-5521",
                      statuses=[("sent", d(-60)), ("acknowledged", d(-58)), ("confirmed", d(-57))], due=d(-47))  # fmt: skip
    _deliver(session, event_bus, bw_order, planned=d(-47), delivered_at=d(-47), carrier="Geodis", tracking="GEO-55821")
    bw_invoice = _invoice(session, event_bus, bw_order, issued=d(-47), due=d(20), schedule=[
        {"due_at": d(-40), "amount": 4000, "label": "Échéance 1/3"},
        {"due_at": d(-10), "amount": 4000, "label": "Échéance 2/3"},
        {"due_at": d(20), "amount": 4000, "label": "Échéance 3/3"},
    ])  # fmt: skip
    billing.record_payment(session, event_bus, company.id, amount=4000, invoice=bw_invoice, occurred_at=d(-40), label="Virement BrightWorks — 1/3", source=SIM)
    billing.record_payment(session, event_bus, company.id, amount=4000, invoice=bw_invoice, occurred_at=d(-9), label="Virement BrightWorks — 2/3", source=SIM)

    # --- Vantix: partly paid and late, contested, credit note waiting for validation; new order not acknowledged ---
    vx_order = _order(session, event_bus, company, vantix, [LineInput(product_id=board.id, quantity=60, unit_price=160.0)], issued=d(-70), title="Cartes de contrôle — lot 2", ref="VX-8812",
                      statuses=[("confirmed", d(-68))], due=d(-55))  # fmt: skip
    _deliver(session, event_bus, vx_order, planned=d(-55), delivered_at=d(-55), carrier="Kuehne+Nagel")
    vx_invoice = _invoice(session, event_bus, vx_order, issued=d(-55), due=d(-25))
    billing.record_payment(session, event_bus, company.id, amount=5000, invoice=vx_invoice, occurred_at=d(-20), label="Virement Vantix — partiel", source=SIM)
    _message(session, company, subject=f"Contestation facture {vx_invoice.number}", body="Bonjour,\nSix cartes de ce lot présentent un défaut de firmware. Nous ne réglerons le solde qu'après régularisation.\nVantix Group — comptabilité fournisseurs", when=d(-18), party=vantix, doc=vx_invoice, key="vantix-contest")
    vx_credit = _credit(session, event_bus, vx_invoice, title="Régularisation — 6 cartes défectueuses",
                        lines=[LineInput(product_id=board.id, description="6 cartes — défaut firmware", quantity=6, unit_price=100.0)], steps=["submitted", "accepted"])  # fmt: skip
    _order(session, event_bus, company, vantix, [LineInput(product_id=sensor.id, quantity=18, unit_price=130.0)], issued=d(-3), title="Modules capteurs — réassort", statuses=[("sent", d(-3))])

    # --- Atelier Rhône: paid in full at order, delivery in transit, price adjustment -> refund pending ---------
    at_order = _order(session, event_bus, company, atelier, [LineInput(product_id=hose.id, quantity=35, unit_price=110.0)], issued=d(-21), title="Flexibles hydrauliques", statuses=[("sent", d(-21)), ("acknowledged", d(-20)), ("confirmed", d(-20))], due=d(1))
    at_invoice = _invoice(session, event_bus, at_order, issued=d(-20), due=d(-20))
    at_invoice.payment_terms = "Paiement intégral à la commande"
    session.commit()
    billing.record_payment(session, event_bus, company.id, amount=billing.doc_total(at_invoice), invoice=at_invoice, occurred_at=d(-20), label="Carte bancaire — paiement à la commande", source=SIM)
    _deliver(session, event_bus, at_order, planned=d(1), carrier="DHL Freight", tracking="DHL-7741-2209")
    at_credit = _credit(session, event_bus, at_invoice, title="Ajustement tarifaire convenu", lines=[LineInput(description="Ajustement tarifaire (remise volume non appliquée)", quantity=1, unit_price=300.0)], steps=["submitted", "accepted"])
    _approve_validation(session, event_bus, at_credit)
    billing.apply_credit_note(session, event_bus, at_credit, now=d(-5))

    # --- Helio: late delivery, paid in full, credit note refused -> decision task; account up to date ----------
    he_order = _order(session, event_bus, company, helio, [LineInput(product_id=frame.id, quantity=10, unit_price=620.0)], issued=d(-45), title="Châssis — parc solaire", statuses=[("confirmed", d(-44))], due=d(-35))
    _deliver(session, event_bus, he_order, planned=d(-35), delivered_at=d(-30), carrier="Geodis")
    he_invoice = _invoice(session, event_bus, he_order, issued=d(-30), due=d(0))
    billing.record_payment(session, event_bus, company.id, amount=billing.doc_total(he_invoice), invoice=he_invoice, occurred_at=d(-12), label="Virement Helio Parc", source=SIM)
    he_credit = _credit(session, event_bus, he_order, title="Dédommagement retard de livraison", lines=[LineInput(description="Dédommagement — livraison livrée avec 5 jours de retard", quantity=1, unit_price=450.0)], steps=["submitted"])
    _message(session, company, subject=f"Re: proposition d'avoir {he_credit.number}", body="Bonjour,\nNous préférons un engagement ferme sur les dates des prochaines livraisons plutôt qu'un avoir.\nMarc Delorme", when=d(-6), party=helio, doc=he_credit, key="helio-refuse")
    service.change_status(session, event_bus, he_credit, "rejected")

    # --- Nordic Rail: order acknowledged by the customer, not yet confirmed -------------------------------
    _order(session, event_bus, company, nordic, [LineInput(product_id=board.id, quantity=45, unit_price=120.0)], issued=d(-4), title="Cartes de contrôle — pilote", ref="NRS-2026-114", statuses=[("sent", d(-4)), ("acknowledged", d(-1))])

    # --- Suppliers ------------------------------------------------------------------------------------------
    def po(supplier, product, qty, price, *, issued, due, title):
        doc = service.create_document(session, event_bus, company.id, DocumentInput(kind=K.PURCHASE_ORDER, supplier_id=supplier.id, title=title, issued_at=issued, due_at=due, source=SIM, lines=[LineInput(product_id=product.id, quantity=qty, unit_price=price)]))
        service.change_status(session, event_bus, doc, "sent", occurred_at=issued)
        service.change_status(session, event_bus, doc, "confirmed", occurred_at=issued + timedelta(days=1))
        return doc

    def receive(order, *, qty=None, received_at=None, expected=None, carrier=None):
        rec = service.derive_document(session, event_bus, order, K.RECEPTION)
        rec.source, rec.carrier = SIM, carrier
        if expected is not None:
            rec.due_at = expected
        if qty is not None:
            rec.lines[0].quantity = qty
        session.commit()
        if received_at is not None:
            service.change_status(session, event_bus, rec, "received", occurred_at=received_at)
        return rec

    pac = po(pacific, board, 24, 95.0, issued=d(-30), due=d(-16), title="Cartes de contrôle — réassort")
    receive(pac, received_at=d(-17), carrier="DB Schenker")
    service.change_status(session, event_bus, pac, "received", occurred_at=d(-17))
    pac_inv = service.derive_document(session, event_bus, pac, K.SUPPLIER_INVOICE)
    pac_inv.source, pac_inv.due_at = SIM, d(-2)
    session.commit()
    service.change_status(session, event_bus, pac_inv, "approved")
    billing.record_payment(session, event_bus, company.id, amount=billing.doc_total(pac_inv), invoice=pac_inv, occurred_at=d(-5), label="Règlement Pacific Components", source=SIM)

    coa = po(coastal, fastener, 400, 15.0, issued=d(-20), due=d(-3), title="Kits de fixation")
    receive(coa, qty=250, received_at=d(-4), carrier="Transports Coste")
    receive(coa, qty=150, expected=d(6), carrier="Transports Coste")
    coa_inv = service.derive_document(session, event_bus, coa, K.SUPPLIER_INVOICE)
    coa_inv.source, coa_inv.due_at = SIM, d(26)
    coa_inv.lines[0].quantity = 250
    session.commit()

    ibe = po(iberia, board, 30, 104.0, issued=d(-25), due=d(-6), title="Cartes de contrôle — lot urgent")
    receive(ibe, expected=d(-6), carrier="Transportes Ibéricos")

    return {
        "skipped": False,
        "customers_added": 3,
        "credit_notes": session.query(CommercialDocument).filter(CommercialDocument.company_id == company.id, CommercialDocument.kind.in_([K.CUSTOMER_CREDIT_NOTE, K.SUPPLIER_CREDIT_NOTE])).count(),
        "metroline_credit": metro_credit.number,
        "vantix_credit_pending_validation": vx_credit.number,
        "northline_claim": northline_claim.number if northline_claim else None,
    }


def run() -> None:
    from app.database import SessionLocal
    from app.event_bus import build_event_bus

    session = SessionLocal()
    try:
        print("V2.2 demo data:", seed_v22_demo(session, build_event_bus()))
    finally:
        session.close()


if __name__ == "__main__":
    run()
