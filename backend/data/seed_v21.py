"""V2.1 demonstration data, layered on top of data/seed.py + data/seed_v2.py.

Every figure here is SIMULATED demonstration data and stored as such
(ValueBasis.SIMULATED / source "simulated") -- salaries, balances, cash
movements, candidates -- so the UI labels it and nothing reads as the
company's real data. It reuses the V2 objects (user profiles become
employees, the demo deals get an owner, compliance requests link to the
documents they concern) and replays the real services (sourcing run,
website audit on the bundled demo site). Idempotent.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.actions.service import ActionsService
from app.compliance.service import create_request
from app.core.entities import (
    BankAccount,
    BusinessContext,
    CashMovement,
    CommercialDocument,
    Communication,
    CommunicationDirection,
    Company,
    Contact,
    DocumentKind,
    Employee,
    EmployeeCostItem,
    RelatedEntityType,
    Shareholder,
    SkillNeed,
    Supplier,
    TaskStatus,
    UserProfile,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.objects.links import create_link
from app.people.service import extract_candidate, publish_skill_gaps
from app.sourcing.service import run_sourcing
from app.website.service import audit_website

SIM = ValueBasis.SIMULATED


def _costs(salary: float, software: list[tuple[str, float]], equipment: float) -> list[EmployeeCostItem]:
    items = [EmployeeCostItem(kind="salary", label="Salaire brut annuel", annual_min=salary, annual_max=salary, basis=SIM, confidence="medium", source="simulated")]
    items += [EmployeeCostItem(kind="software", label=label, annual_min=amount, annual_max=amount, basis=SIM, confidence="medium", source="simulated") for label, amount in software]
    items.append(EmployeeCostItem(kind="equipment", label="Ordinateur & téléphone (amortis)", annual_min=equipment * 0.8, annual_max=equipment * 1.2, basis=ValueBasis.ESTIMATED, confidence="low", source="simulated"))
    return items


def seed_v21_demo(session: Session, event_bus: EventBus, company: Company | None = None) -> dict:
    company = company or session.query(Company).first()
    if company is None:
        return {"skipped": True, "reason": "no company"}
    if session.query(Employee.id).filter_by(company_id=company.id).first() is not None:
        return {"skipped": True, "reason": "V2.1 data already present"}
    now = datetime.now(timezone.utc)
    users = {u.role.value: u for u in session.query(UserProfile).filter_by(company_id=company.id).all()}

    # --- People -------------------------------------------------------------------
    people_spec = [
        ("Camille Laurent", "Directrice générale", "Direction", "director", 6.0, ["pilotage", "finance", "négociation"], 78000, [("Suite bureautique", 250)], 1800),
        ("Hugo Martin", "Responsable commercial", "Ventes", "sales", 3.5, ["vente", "négociation", "crm", "anglais"], 46000, [("CRM (licence)", 900), ("Suite bureautique", 250)], 1500),
        ("Inès Moreau", "Acheteuse", "Achats", "procurement", 2.0, ["achats", "négociation", "logistique", "excel"], 41000, [("Suite bureautique", 250)], 1500),
        ("Léa Bernard", "Responsable opérations", "Opérations", None, 5.0, ["logistique", "gestion de projet", "excel"], 43000, [("Suite bureautique", 250), ("Outil de planification", 420)], 1500),
        ("Marc Petit", "Assistant administratif", "Administration", None, 1.0, ["comptabilité", "excel"], 29000, [("Suite bureautique", 250)], 1200),
    ]
    employees: dict[str, Employee] = {}
    for name, title, dept, role, years, skills, salary, software, equipment in people_spec:
        user = users.get(role) if role else None
        e = Employee(
            company_id=company.id, user_id=user.id if user else None, full_name=name, job_title=title, department=dept, status="active",
            hired_at=now - timedelta(days=int(365 * years)), weekly_hours=39 if role != "director" else 45, leave_days_remaining=round(12 - years, 1),
            skills=skills, responsibilities=[], data_basis=SIM,
        )  # fmt: skip
        e.cost_items = _costs(salary, software, equipment)
        session.add(e)
        employees[name] = e
    session.flush()
    for e in employees.values():
        if e.full_name != "Camille Laurent":
            e.manager_id = employees["Camille Laurent"].id
    session.commit()

    # The demo deals get an owner, so a contribution can be traced to them.
    if "sales" in users:
        for doc in session.query(CommercialDocument).filter(CommercialDocument.company_id == company.id, CommercialDocument.owner_user_id.is_(None), CommercialDocument.kind.in_([DocumentKind.CUSTOMER_REQUEST, DocumentKind.CUSTOMER_QUOTE, DocumentKind.CUSTOMER_ORDER])).all():
            doc.owner_user_id = users["sales"].id
        session.commit()

    actions = ActionsService(session, event_bus)
    for who, titles, done in (
        ("Hugo Martin", ["Relancer BrightWorks sur le devis", "Préparer la revue client Metroline", "Mettre à jour les prix catalogue", "Qualifier la demande Solaris Events"], 3),
        ("Inès Moreau", ["Consulter un second fournisseur pour les cartes", "Contrôler la facture Northline", "Négocier le transport routier"], 2),
        ("Léa Bernard", ["Planifier la livraison Metroline", "Inventaire entrepôt Lyon"], 2),
    ):
        for i, title in enumerate(titles):
            t = actions.create_manual_task(company_id=company.id, title=title, description=None, domain="operations", requires_decision=False, related_entity_type=RelatedEntityType.EMPLOYEE, related_entity_id=employees[who].id)
            t.assignee_employee_id = employees[who].id
            t.due_at = now + timedelta(days=5 - 4 * i)
            if i < done:
                t.status = TaskStatus.DONE
    session.commit()

    # --- Skills needs & candidates ---------------------------------------------------
    session.add_all(
        [
            SkillNeed(
                company_id=company.id, skill="Data / automatisation", keywords=["python", "sql", "power bi", "automatisation", "data"], level="confirmé",
                reason="Reporting manuel chronophage et données éparpillées entre ventes, achats et finance.",
                expected_impact="Réduction du travail manuel, reporting fiable, automatisation de relances et d'imports.", priority="high",
            ),
            SkillNeed(
                company_id=company.id, skill="Marketing digital / SEO", keywords=["seo", "marketing", "google ads", "contenu"], level="confirmé",
                reason="Le site génère peu de demandes entrantes.", expected_impact="Plus de demandes qualifiées via le site.", priority="medium",
            ),
        ]
    )  # fmt: skip
    session.commit()
    applications = [
        ("Sofia Rinaldi", "sofia.rinaldi@example.org", "Candidature — poste de Data Analyst",
         "Bonjour,\nJe vous adresse ma candidature au poste de Data Analyst. J'ai 4 ans d'expérience en analyse de données : Python, SQL, Power BI, automatisation de reporting.\nCV en pièce jointe.\nSofia Rinaldi"),
        ("Thomas Leroy", "thomas.leroy@example.org", "Candidature spontanée — Data Analyst",
         "Bonjour,\nJe souhaite postuler au poste de Data Analyst. 2 ans d'expérience, très à l'aise sur Excel et les tableaux de bord.\nCordialement,\nThomas Leroy"),
    ]  # fmt: skip
    created_messages = []
    for i, (name, email, subject, body) in enumerate(applications):
        contact = Contact(company_id=company.id, name=name, email=email)
        session.add(contact)
        session.flush()
        msg = Communication(
            company_id=company.id, channel="email", direction=CommunicationDirection.INBOUND, status="received", subject=subject, body=body,
            occurred_at=now - timedelta(days=2 + i), contact_id=contact.id, from_address=email, source="simulated_demo", external_id=f"sim-application-{i + 1}",
        )  # fmt: skip
        session.add(msg)
        created_messages.append(msg)
    session.commit()
    extract_candidate(session, event_bus, created_messages[0])  # the second one is left for the demo ("Créer la fiche candidat")
    publish_skill_gaps(session, event_bus, company.id)

    # --- Treasury & ownership -----------------------------------------------------------
    current = BankAccount(company_id=company.id, name="Compte courant", bank_name="Banque Démo", kind="current", masked_identifier="FR76 •••• 4821", balance=48200, balance_basis=SIM, balance_as_of=now - timedelta(days=1), source="simulated")
    savings = BankAccount(company_id=company.id, name="Compte épargne", bank_name="Banque Démo", kind="savings", masked_identifier="FR76 •••• 9034", balance=30000, balance_basis=SIM, balance_as_of=now - timedelta(days=1), source="simulated")
    card = BankAccount(company_id=company.id, name="Carte Affaires", bank_name="Banque Démo", kind="card", masked_identifier="•••• 4242", balance=-1840, balance_basis=SIM, balance_as_of=now - timedelta(days=1), source="simulated")
    loan = BankAccount(company_id=company.id, name="Prêt équipement", bank_name="Banque Démo", kind="loan", balance=60000, balance_basis=SIM, balance_as_of=now - timedelta(days=1), interest_rate=0.032, maturity_at=now + timedelta(days=365 * 4), source="simulated")
    session.add_all([current, savings, card, loan])
    session.flush()
    payroll = sum(i.annual_min for e in employees.values() for i in e.cost_items if i.kind == "salary") / 12 * 1.43
    movements = [(current, "in", 12600, "actual", -12, "customer_payment", "Règlement Metroline"), (current, "out", 9400, "actual", -6, "supplier_payment", "Northline Steel — facture")]
    for month in (1, 2, 3):
        movements += [
            (current, "out", round(payroll), "planned", 30 * month - 5, "salary", "Salaires et charges"),
            (current, "out", 1150, "planned", 30 * month - 10, "loan", "Échéance prêt équipement"),
            (current, "out", 2400, "planned", 30 * month - 2, "rent", "Loyer"),
        ]
    movements.append((current, "out", 7800, "planned", 40, "tax", "TVA et acompte d'impôt"))
    for account, direction, amount, status, days, category, label in movements:
        session.add(CashMovement(company_id=company.id, account_id=account.id, direction=direction, amount=amount, status=status, occurred_at=now + timedelta(days=days), category=category, label=label, source="simulated"))
    ctx = session.query(BusinessContext).filter_by(company_id=company.id).first()
    if ctx is not None:
        ctx.finance_settings = {**(ctx.finance_settings or {}), "min_cash": 25000}
    session.add_all(
        [
            Shareholder(company_id=company.id, name="Fondateur A", kind="founder", shares=4500, basis=SIM),
            Shareholder(company_id=company.id, name="Fondateur B", kind="founder", shares=4500, basis=SIM),
            Shareholder(company_id=company.id, name="Camille Laurent (DG)", kind="executive", shares=1000, employee_id=employees["Camille Laurent"].id, basis=SIM),
        ]
    )
    session.commit()

    # --- External experts & compliance ---------------------------------------------------
    for name, kind, lo, hi, email in (
        ("Cabinet Duval Avocats", "law_firm", 180, 260, "contact@duval-avocats.example"),
        ("Fiduciaire Martin & Associés", "accounting_firm", 90, 140, "bonjour@fiduciaire-martin.example"),
        ("Courtage Pro Assurances", "insurance_advisor", None, None, "conseil@courtage-pro.example"),
    ):
        expert = Supplier(company_id=company.id, name=name, supplier_kind=kind, fee_rate_min=lo, fee_rate_max=hi, country="FR", certifications=[])
        session.add(expert)
        session.flush()
        session.add(Contact(company_id=company.id, name=name, email=email, related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=expert.id))
    session.commit()
    order = session.query(CommercialDocument).filter_by(company_id=company.id, kind=DocumentKind.CUSTOMER_ORDER).first()
    prospect_request = session.query(CommercialDocument).filter_by(company_id=company.id, kind=DocumentKind.CUSTOMER_REQUEST, status="new").first()
    contract = create_request(session, event_bus, company.id, title="Vérifier le contrat cadre Metroline", category="contract_review", description="Clauses de pénalité de retard et de révision de prix à valider avant renouvellement.", due_at=now + timedelta(days=10))
    create_request(session, event_bus, company.id, title="Renouvellement assurance RC Pro", category="renewal", description="Échéance annuelle du contrat.", due_at=now + timedelta(days=25))
    nda = create_request(session, event_bus, company.id, title="NDA avec Solaris Events", category="nda", description="Le prospect demande un accord de confidentialité avant de partager son cahier des charges.", due_at=now + timedelta(days=5))
    if order is not None:
        create_link(session, company_id=company.id, source_type="task", source_id=contract.id, target_type="commercial_document", target_id=order.id, relation="concerns", origin="system")
    if prospect_request is not None:
        create_link(session, company_id=company.id, source_type="task", source_id=nda.id, target_type="commercial_document", target_id=prospect_request.id, relation="concerns", origin="system")

    # --- AI runs, replayed through the real services -------------------------------------------
    pr = session.query(CommercialDocument).filter_by(company_id=company.id, kind=DocumentKind.PURCHASE_REQUEST, status="consulting").first()
    if pr is not None:
        run_sourcing(session, event_bus, pr, web=None)
    audit_website(session, event_bus, company)  # no website configured -> bundled demo site, mode "simulated"
    return {"skipped": False, "employees": len(employees)}


def run() -> None:
    from app.database import SessionLocal
    from app.event_bus import build_event_bus

    session = SessionLocal()
    try:
        print("V2.1 demo data:", seed_v21_demo(session, build_event_bus()))
    finally:
        session.close()


if __name__ == "__main__":
    run()
