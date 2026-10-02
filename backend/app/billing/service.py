"""Payments, instalments, account balances, credit notes and delivery follow-up
(V2.2, brain/billing.md).

One source of truth, derived views:

- what is owed comes from the INVOICES (commercial documents);
- what was paid is a real money movement, a `CashMovement` (status "actual"),
  allocated to an invoice through `document_id` -- or attributed to a party
  but not yet reconciled ("à rapprocher");
- a credit note reduces what is owed only once it is VALIDATED and IMPUTED:
  its single `CreditApplication` row records how much reduced the invoice and
  how much must be refunded (a refund is again a real CashMovement).

Invoice settlement statuses, account balances, overdue amounts, instalment
progress and order fulfilment are all computed from those rows -- never
stored twice, never typed in by hand. Deterministic; no LLM.

Accounting: account numbers (411, 512, 601...) are optional, configurable
references attached to the operations for traceability -- NOT a ledger
(see brain/billing.md "À confirmer avec le comptable").
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.actions.service import ActionsService
from app.core.analytics import _as_aware_utc
from app.core.entities import (
    BusinessContext,
    CashMovement,
    CommercialDocument,
    CreditApplication,
    Customer,
    DocumentKind,
    PaymentInstallment,
    RelatedEntityType,
    Risk,
    Supplier,
    Task,
    TaskStatus,
)
from app.core.entities.risk import RiskSeverity, RiskStatus
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.objects.graph import document_chain, document_children, document_parents
from app.transactions.lifecycle import KINDS, OPEN_INVOICE_STATUSES, status_label

K = DocumentKind
TOLERANCE = 0.005  # half a cent: amounts are compared at the cent

BILLING_DOMAIN = "finance"
VALIDATE_CREDIT_NOTE_ACTION = "validate_credit_note"

PAYMENT_RECORDED = "PaymentRecorded"
PAYMENT_ALLOCATED = "PaymentAllocated"
INSTALLMENTS_SET = "PaymentScheduleSet"
CREDIT_NOTE_ACCEPTED = "CreditNoteAccepted"
CREDIT_NOTE_REJECTED = "CreditNoteRejected"
CREDIT_NOTE_VALIDATED = "CreditNoteValidated"
CREDIT_NOTE_APPLIED = "CreditNoteApplied"
REFUND_RECORDED = "RefundRecorded"
SUPPLIER_CREDIT_CONFIRMED = "SupplierCreditNoteConfirmed"
SUPPLIER_CREDIT_REJECTED = "SupplierCreditNoteRejected"
ORDER_ACKNOWLEDGED = "CustomerOrderAcknowledged"
NONCONFORMITY_REPORTED = "NonConformityReported"

INVOICE_KINDS = {K.CUSTOMER_INVOICE, K.SUPPLIER_INVOICE}
CREDIT_KINDS = {K.CUSTOMER_CREDIT_NOTE, K.SUPPLIER_CREDIT_NOTE}
# Credit notes that exist but do not (yet) change any balance.
PENDING_CREDIT_STATUSES = {
    K.CUSTOMER_CREDIT_NOTE: {"draft", "submitted", "accepted", "validated"},
    K.SUPPLIER_CREDIT_NOTE: {"requested", "confirmed"},
}

# Suggested account references, shown as EXAMPLES until the company's
# accountant confirms a chart (finance_settings["accounting_refs"]). Never
# applied by default.
ACCOUNTING_REF_EXAMPLES = {
    "customer_receivable": ("411", "Clients"),
    "supplier_payable": ("401", "Fournisseurs"),
    "bank": ("512", "Banque"),
    "purchases": ("601", "Achats"),
    "sales": ("706", "Ventes"),
}


class BillingError(ValueError):
    """A billing rule refused the operation (message shown as-is)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    return _as_aware_utc(value) if value is not None else None


def doc_total(doc: CommercialDocument) -> float | None:
    """Same rule as the document API: incomplete if any line has no price."""

    if not doc.lines or any(ln.unit_price is None for ln in doc.lines):
        return None
    return round(sum(ln.quantity * ln.unit_price for ln in doc.lines), 2)


def _eur(amount: float) -> str:
    """French amount for messages shown as-is: 4 000,00 €."""

    return f"{amount:,.2f}".replace(",", "\u202f").replace(".", ",") + " €"


def _is_customer_side(doc: CommercialDocument) -> bool:
    return KINDS[doc.kind].party == "customer"


def _payment_category(doc: CommercialDocument) -> str:
    return "customer_payment" if _is_customer_side(doc) else "supplier_payment"


def _payment_direction(doc: CommercialDocument) -> str:
    return "in" if _is_customer_side(doc) else "out"


def _is_simulated(source: str | None) -> bool:
    return bool(source) and source.startswith("simulated")


def _publish(event_bus: EventBus, event_type: str, doc: CommercialDocument | None, extra: dict) -> None:
    payload = dict(extra)
    if doc is not None:
        payload |= {
            "subject_type": "commercial_document",
            "subject_id": str(doc.id),
            "document_id": str(doc.id),
            "number": doc.number,
            "kind": doc.kind.value,
            "customer_id": str(doc.customer_id) if doc.customer_id else None,
            "supplier_id": str(doc.supplier_id) if doc.supplier_id else None,
        }
    event_bus.publish(BusinessEvent(event_type=event_type, source="billing", payload=payload))


# --- Accounting references ------------------------------------------------------------


def accounting_refs(session: Session, company_id: uuid.UUID) -> dict:
    """Configured references (may be empty) + the examples to confirm."""

    ctx = session.query(BusinessContext).filter_by(company_id=company_id).first()
    configured = dict((ctx.finance_settings or {}).get("accounting_refs") or {}) if ctx else {}
    return {
        "configured": configured,
        "examples": {k: {"account": a, "label": label} for k, (a, label) in ACCOUNTING_REF_EXAMPLES.items()},
        "status": "configured" if configured else "to_confirm",
        "note": "Références indicatives pour la traçabilité, à confirmer avec le comptable. Aucune écriture comptable n'est générée.",
    }


# --- Invoice settlement ---------------------------------------------------------------------


def payments_on(session: Session, invoice: CommercialDocument) -> list[CashMovement]:
    return (
        session.query(CashMovement)
        .filter(
            CashMovement.document_id == invoice.id,
            CashMovement.status == "actual",
            CashMovement.category == _payment_category(invoice),
        )
        .order_by(CashMovement.occurred_at)
        .all()
    )


def credits_on(session: Session, invoice: CommercialDocument) -> list[CreditApplication]:
    return session.query(CreditApplication).filter(CreditApplication.invoice_id == invoice.id).order_by(CreditApplication.applied_at).all()


def _schedule(session: Session, invoice: CommercialDocument, total: float) -> list[dict]:
    rows = session.query(PaymentInstallment).filter_by(document_id=invoice.id).order_by(PaymentInstallment.sequence).all()
    if rows:
        return [{"id": r.id, "sequence": r.sequence, "label": r.label, "due_at": _aware(r.due_at), "amount": r.amount, "stored": True} for r in rows]
    due = _aware(invoice.due_at) or _aware(invoice.issued_at) or _aware(invoice.created_at)
    return [{"id": None, "sequence": 1, "label": "Paiement unique", "due_at": due, "amount": total, "stored": False}]


def settlement(session: Session, invoice: CommercialDocument, now: datetime | None = None) -> dict:
    """What an invoice is worth, what settled it (payments + imputed credit
    notes), what remains, instalment by instalment (settled amounts are
    allocated to instalments in due-date order), and what is late."""

    if invoice.kind not in INVOICE_KINDS:
        raise BillingError("Seule une facture a un règlement")
    now = now or _now()
    total = doc_total(invoice)
    base = {"invoice_id": invoice.id, "number": invoice.number, "status": invoice.status, "status_label": status_label(invoice.kind, invoice.status)}
    if total is None:
        return base | {"available": False, "reason": "Montant incomplet : une ligne n'a pas de prix."}
    if invoice.status not in OPEN_INVOICE_STATUSES[invoice.kind]:
        return base | {"available": False, "total": total, "reason": "Facture non émise : aucun montant n'est encore dû." if invoice.status == "draft" else "Facture annulée."}

    payments = payments_on(session, invoice)
    credits = credits_on(session, invoice)
    paid = round(sum(p.amount for p in payments), 2)
    credited = round(sum(c.applied_amount for c in credits), 2)
    settled = round(paid + credited, 2)
    remaining = round(max(0.0, total - settled), 2)

    left = settled
    installments = []
    for row in _schedule(session, invoice, total):
        covered = round(min(row["amount"], max(0.0, left)), 2)
        left = round(left - covered, 2)
        rest = round(row["amount"] - covered, 2)
        due = row["due_at"]
        if rest <= TOLERANCE:
            state = "paid"
        elif due is not None and due < now:
            state = "overdue"
        elif covered > TOLERANCE:
            state = "partial"
        else:
            state = "due"
        installments.append(row | {"settled": covered, "remaining": max(rest, 0.0), "state": state, "days_late": (now - due).days if state == "overdue" else 0})

    overdue = [i for i in installments if i["state"] == "overdue"]
    upcoming = [i for i in installments if i["state"] in {"due", "partial", "overdue"}]
    if remaining <= TOLERANCE:
        state, label = "paid", "Réglée"
    elif settled > TOLERANCE:
        state, label = "partially_paid", "Partiellement réglée"
    else:
        state, label = "unpaid", "Non réglée"
    return base | {
        "available": True,
        "total": total,
        "paid": paid,
        "credited": credited,
        "remaining": remaining,
        "state": state,
        "state_label": label,
        "is_late": bool(overdue),
        "overdue_amount": round(sum(i["remaining"] for i in overdue), 2),
        "installments": installments,
        "installments_paid": sum(1 for i in installments if i["state"] == "paid"),
        "installments_count": len(installments),
        "schedule_is_default": not any(i["stored"] for i in installments),
        "next_due": upcoming[0] if upcoming else None,
        "payments": [
            {"id": p.id, "amount": p.amount, "occurred_at": p.occurred_at, "label": p.label, "source": p.source, "simulated": _is_simulated(p.source)} for p in payments
        ],
        "credits": [
            {"credit_note_id": c.credit_note_id, "number": _number(session, c.credit_note_id), "amount": c.applied_amount, "applied_at": c.applied_at} for c in credits
        ],
    }


def _number(session: Session, doc_id: uuid.UUID | None) -> str | None:
    doc = session.get(CommercialDocument, doc_id) if doc_id else None
    return doc.number if doc else None


def sync_invoice_status(session: Session, event_bus: EventBus, invoice: CommercialDocument) -> None:
    """Moves the invoice to "Partiellement réglée" / "Réglée" when (and only
    when) recorded payments and imputed credit notes say so."""

    from app.transactions.lifecycle import allowed_transitions
    from app.transactions.service import change_status

    view = settlement(session, invoice)
    if not view.get("available"):
        return
    target = view["state"]
    if target != "unpaid" and target in allowed_transitions(invoice.kind, invoice.status):
        change_status(session, event_bus, invoice, target, system=True)


def _check_payable(invoice: CommercialDocument) -> None:
    if invoice.kind == K.CUSTOMER_INVOICE and invoice.status not in {"issued", "partially_paid"}:
        raise BillingError("Un paiement s'enregistre sur une facture émise et non soldée")
    if invoice.kind == K.SUPPLIER_INVOICE and invoice.status not in {"approved", "partially_paid"}:
        raise BillingError("Une facture fournisseur doit être validée avant d'enregistrer un règlement")


def record_payment(
    session: Session,
    event_bus: EventBus,
    company_id: uuid.UUID,
    *,
    amount: float,
    invoice: CommercialDocument | None = None,
    customer_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    account_id: uuid.UUID | None = None,
    label: str | None = None,
    source: str = "manual",
) -> CashMovement:
    """A payment that really happened. On an invoice: allocated to it (never
    above what remains). Without an invoice: attributed to its customer or
    supplier and left "à rapprocher" until allocated."""

    if amount is None or amount <= 0:
        raise BillingError("Le montant doit être positif")
    amount = round(float(amount), 2)
    if invoice is not None:
        if invoice.kind not in INVOICE_KINDS or invoice.company_id != company_id:
            raise BillingError("Document de règlement invalide")
        _check_payable(invoice)
        remaining = settlement(session, invoice)["remaining"]
        if amount > remaining + TOLERANCE:
            raise BillingError(f"Le montant dépasse le reste à payer ({_eur(remaining)}) : enregistrez l'excédent comme paiement à rapprocher")
        customer_id, supplier_id = invoice.customer_id, invoice.supplier_id
        category, direction = _payment_category(invoice), _payment_direction(invoice)
        party = session.get(Customer, customer_id) if customer_id else session.get(Supplier, supplier_id)
        default_label = f"Règlement {invoice.number}"
    else:
        if bool(customer_id) == bool(supplier_id):
            raise BillingError("Un paiement non affecté doit être rattaché à un client ou à un fournisseur")
        category, direction = ("customer_payment", "in") if customer_id else ("supplier_payment", "out")
        party = session.get(Customer, customer_id) if customer_id else session.get(Supplier, supplier_id)
        if party is None or party.company_id != company_id:
            raise BillingError("Client ou fournisseur introuvable")
        default_label = "Paiement à rapprocher"
    movement = CashMovement(
        company_id=company_id, account_id=account_id, direction=direction, amount=amount, status="actual",
        occurred_at=occurred_at or _now(), category=category, label=label or default_label,
        counterparty=party.name if party else None, document_id=invoice.id if invoice else None,
        customer_id=customer_id, supplier_id=supplier_id, source=source,
    )  # fmt: skip
    session.add(movement)
    session.commit()
    _publish(event_bus, PAYMENT_RECORDED, invoice, {"movement_id": str(movement.id), "amount": amount, "allocated": invoice is not None, "customer_id": str(customer_id) if customer_id else None, "supplier_id": str(supplier_id) if supplier_id else None})
    if invoice is not None:
        sync_invoice_status(session, event_bus, invoice)
    return movement


def allocate_payment(session: Session, event_bus: EventBus, movement: CashMovement, invoice: CommercialDocument) -> CashMovement:
    """Reconciles an attributed-but-unallocated payment with an invoice of the same party."""

    if movement.status != "actual" or movement.document_id is not None:
        raise BillingError("Ce paiement est déjà rapproché")
    if invoice.kind not in INVOICE_KINDS or movement.category != _payment_category(invoice):
        raise BillingError("Ce paiement ne peut pas régler ce document")
    if (invoice.customer_id and movement.customer_id != invoice.customer_id) or (invoice.supplier_id and movement.supplier_id != invoice.supplier_id):
        raise BillingError("Le paiement et la facture ne concernent pas le même tiers")
    _check_payable(invoice)
    remaining = settlement(session, invoice)["remaining"]
    if movement.amount > remaining + TOLERANCE:
        raise BillingError(f"Le paiement ({_eur(movement.amount)}) dépasse le reste à payer ({_eur(remaining)})")
    movement.document_id = invoice.id
    session.commit()
    _publish(event_bus, PAYMENT_ALLOCATED, invoice, {"movement_id": str(movement.id), "amount": movement.amount})
    sync_invoice_status(session, event_bus, invoice)
    return movement


def set_installments(session: Session, event_bus: EventBus, invoice: CommercialDocument, items: list[dict]) -> list[PaymentInstallment]:
    """Replaces an invoice's schedule. Free terms (one, two, n instalments,
    deposit + balance...) as long as they add up to the invoice total."""

    if invoice.kind not in INVOICE_KINDS:
        raise BillingError("Un échéancier s'applique à une facture")
    if invoice.status in {"paid", "cancelled"}:
        raise BillingError("Cette facture est soldée ou annulée")
    total = doc_total(invoice)
    if total is None:
        raise BillingError("Montant de la facture incomplet")
    if not items:
        raise BillingError("Au moins une échéance est nécessaire")
    if any((it.get("amount") or 0) <= 0 or it.get("due_at") is None for it in items):
        raise BillingError("Chaque échéance a une date et un montant positif")
    if abs(round(sum(float(it["amount"]) for it in items), 2) - total) > 0.01:
        raise BillingError(f"La somme des échéances doit être égale au montant de la facture ({_eur(total)})")
    session.query(PaymentInstallment).filter_by(document_id=invoice.id).delete()
    rows = []
    for i, it in enumerate(sorted(items, key=lambda x: _aware(x["due_at"])), start=1):
        row = PaymentInstallment(company_id=invoice.company_id, document_id=invoice.id, sequence=i, label=it.get("label") or f"Échéance {i}/{len(items)}", due_at=it["due_at"], amount=round(float(it["amount"]), 2))
        session.add(row)
        rows.append(row)
    # The invoice's due date is its last instalment.
    invoice.due_at = rows[-1].due_at
    session.commit()
    _publish(event_bus, INSTALLMENTS_SET, invoice, {"count": len(rows)})
    return rows


# --- Credit notes ------------------------------------------------------------------------------


def credit_application(session: Session, credit_note: CommercialDocument) -> CreditApplication | None:
    return session.query(CreditApplication).filter_by(credit_note_id=credit_note.id).first()


def target_invoice(session: Session, credit_note: CommercialDocument) -> CommercialDocument | None:
    """The invoice a credit note corrects: the one it was drawn from, or the
    open invoice of the same party in the same deal (the one with the most
    left to pay). None when nothing has been invoiced yet."""

    invoice_kind = K.CUSTOMER_INVOICE if credit_note.kind == K.CUSTOMER_CREDIT_NOTE else K.SUPPLIER_INVOICE
    for parent_id in document_parents(session, credit_note.id):
        parent = session.get(CommercialDocument, parent_id)
        if parent is not None and parent.kind == invoice_kind and parent.status in OPEN_INVOICE_STATUSES[invoice_kind]:
            return parent
    candidates = [
        d for d in document_chain(session, credit_note.id)
        if d.kind == invoice_kind and d.status in OPEN_INVOICE_STATUSES[invoice_kind]
        and d.customer_id == credit_note.customer_id and d.supplier_id == credit_note.supplier_id
    ]  # fmt: skip
    if not candidates:
        return None
    return max(candidates, key=lambda d: settlement(session, d).get("remaining", 0.0))


def credit_view(session: Session, credit_note: CommercialDocument) -> dict:
    """Where a credit note stands and what it did (or will do) to the balance."""

    total = doc_total(credit_note)
    app = credit_application(session, credit_note)
    invoice = session.get(CommercialDocument, app.invoice_id) if app and app.invoice_id else target_invoice(session, credit_note)
    refund = (
        session.query(CashMovement).filter_by(document_id=credit_note.id, category="customer_refund", status="actual").first()
        if credit_note.kind == K.CUSTOMER_CREDIT_NOTE else None
    )  # fmt: skip
    pending_task = (
        session.query(Task)
        .filter_by(related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT, related_entity_id=credit_note.id, pending_action=VALIDATE_CREDIT_NOTE_ACTION, status=TaskStatus.PENDING_VALIDATION)
        .first()
    )
    if credit_note.kind == K.CUSTOMER_CREDIT_NOTE:
        effect = {
            "draft": "Aucun effet sur le solde : l'avoir n'a pas encore été proposé au client.",
            "submitted": "Aucun effet sur le solde : en attente de la réponse du client.",
            "accepted": "Aucun effet sur le solde : accepté par le client, en attente de validation interne.",
            "rejected": "Aucun effet : refusé par le client.",
            "validated": "Validé : l'imputation au compte client reste à faire.",
            "applied": "Imputé une fois au compte client.",
            "refunded": "Imputé, puis l'excédent a été remboursé.",
            "cancelled": "Aucun effet : annulé.",
        }.get(credit_note.status, "")
    else:
        effect = {
            "requested": "Aucun effet : avoir demandé, en attente du fournisseur.",
            "confirmed": "Confirmé par le fournisseur : l'imputation sur sa facture reste à faire.",
            "rejected": "Aucun effet : refusé par le fournisseur.",
            "applied": "Imputé une fois sur ce que nous devons au fournisseur.",
            "cancelled": "Aucun effet : annulé.",
        }.get(credit_note.status, "")
    return {
        "credit_note_id": credit_note.id,
        "amount": total,
        "status": credit_note.status,
        "status_label": status_label(credit_note.kind, credit_note.status),
        "effect": effect,
        "counts_in_balance": app is not None,
        "invoice": {"id": invoice.id, "number": invoice.number, "status_label": status_label(invoice.kind, invoice.status)} if invoice else None,
        "application": {"applied_amount": app.applied_amount, "refund_amount": app.refund_amount, "applied_at": app.applied_at, "invoice_id": app.invoice_id} if app else None,
        "refund": {"id": refund.id, "amount": refund.amount, "occurred_at": refund.occurred_at} if refund else None,
        "refund_due": round(app.refund_amount, 2) if app and app.refund_amount > TOLERANCE and refund is None and credit_note.kind == K.CUSTOMER_CREDIT_NOTE else 0.0,
        "validation_task_id": pending_task.id if pending_task else None,
        "can_request_validation": credit_note.kind == K.CUSTOMER_CREDIT_NOTE and credit_note.status == "accepted" and pending_task is None,
        "can_apply": (credit_note.kind == K.CUSTOMER_CREDIT_NOTE and credit_note.status == "validated") or (credit_note.kind == K.SUPPLIER_CREDIT_NOTE and credit_note.status == "confirmed"),
        "can_refund": credit_note.kind == K.CUSTOMER_CREDIT_NOTE and credit_note.status == "applied" and app is not None and app.refund_amount > TOLERANCE and refund is None,
    }


def request_credit_validation(session: Session, event_bus: EventBus, credit_note: CommercialDocument) -> Task:
    """HITL: an accepted credit note becomes a PENDING_VALIDATION Task in the
    finance domain (director approval by default). The customer's acceptance
    alone never changes a balance."""

    if credit_note.kind != K.CUSTOMER_CREDIT_NOTE or credit_note.status != "accepted":
        raise BillingError("Seul un avoir accepté par le client se soumet à la validation comptable")
    existing = (
        session.query(Task)
        .filter_by(related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT, related_entity_id=credit_note.id, pending_action=VALIDATE_CREDIT_NOTE_ACTION, status=TaskStatus.PENDING_VALIDATION)
        .first()
    )
    if existing is not None:
        return existing
    total = doc_total(credit_note)
    customer = session.get(Customer, credit_note.customer_id) if credit_note.customer_id else None
    task = ActionsService(session, event_bus).propose_task(
        company_id=credit_note.company_id,
        title=f"Valider l'avoir {credit_note.number}" + (f" — {customer.name}" if customer else "") + (f" : {_eur(total)}" if total is not None else ""),
        description="Le client a accepté cet avoir. Une fois validé, il pourra être imputé sur son compte (réduction de sa facture, ou remboursement de l'excédent déjà payé).",
        related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT,
        related_entity_id=credit_note.id,
        pending_action=VALIDATE_CREDIT_NOTE_ACTION,
        agent="billing",
    )
    task.domain = BILLING_DOMAIN
    task.category = "credit_note"
    task.requires_decision = True
    task.action_payload = {"credit_note_id": str(credit_note.id), "amount": total}
    session.commit()
    return task


def finalize_credit_validation(session: Session, event_bus: EventBus, task: Task) -> Task:
    """ActionExecutor branch, run only after an authorised person approved."""

    from app.transactions.service import change_status

    credit_note = session.get(CommercialDocument, task.related_entity_id) if task.related_entity_id else None
    if credit_note is None or credit_note.kind != K.CUSTOMER_CREDIT_NOTE:
        raise BillingError("Avoir introuvable")
    if credit_note.status != "accepted":
        raise BillingError("L'avoir n'est plus en attente de validation")
    change_status(session, event_bus, credit_note, "validated", system=True)
    task.status = TaskStatus.EXECUTED
    session.commit()
    _publish(event_bus, CREDIT_NOTE_VALIDATED, credit_note, {"task_id": str(task.id), "amount": doc_total(credit_note)})
    return task


def apply_credit_note(session: Session, event_bus: EventBus, credit_note: CommercialDocument, now: datetime | None = None) -> CreditApplication:
    """Imputes a validated (customer) / confirmed (supplier) credit note ONCE.
    The part still owed on the corrected invoice is reduced; any excess (the
    invoice was already paid) becomes a refund to record. The unique
    CreditApplication row makes a second imputation impossible."""

    from app.transactions.service import change_status

    if credit_note.kind == K.CUSTOMER_CREDIT_NOTE and credit_note.status != "validated":
        raise BillingError("Un avoir client s'impute après acceptation du client ET validation interne")
    if credit_note.kind == K.SUPPLIER_CREDIT_NOTE and credit_note.status != "confirmed":
        raise BillingError("Un avoir fournisseur s'impute une fois confirmé par le fournisseur")
    if credit_note.kind not in CREDIT_KINDS:
        raise BillingError("Ce document n'est pas un avoir")
    if credit_application(session, credit_note) is not None:
        raise BillingError("Cet avoir a déjà été imputé")
    total = doc_total(credit_note)
    if total is None or total <= 0:
        raise BillingError("Montant de l'avoir incomplet")
    invoice = target_invoice(session, credit_note)
    if invoice is not None:
        # Reduces what is still owed on the invoice; anything above it was
        # already paid and must be refunded.
        applied = round(min(total, settlement(session, invoice)["remaining"]), 2)
        refund = round(total - applied, 2)
    else:
        # Nothing invoiced to reduce: the whole credit stays on the account.
        applied, refund = 0.0, 0.0
    app = CreditApplication(company_id=credit_note.company_id, credit_note_id=credit_note.id, invoice_id=invoice.id if invoice else None, applied_amount=applied, refund_amount=refund, applied_at=now or _now())
    session.add(app)
    session.commit()
    change_status(session, event_bus, credit_note, "applied", system=True)
    _publish(event_bus, CREDIT_NOTE_APPLIED, credit_note, {"amount": total, "applied_to_invoice": app.applied_amount, "refund_amount": refund, "invoice_id": str(invoice.id) if invoice else None})
    if invoice is not None:
        sync_invoice_status(session, event_bus, invoice)
    return app


def record_refund(session: Session, event_bus: EventBus, credit_note: CommercialDocument, *, occurred_at: datetime | None = None, account_id: uuid.UUID | None = None, source: str = "manual") -> CashMovement:
    """Records that the refund due on an imputed customer credit note was
    really paid (a person did the transfer: no bank connection here)."""

    from app.transactions.service import change_status

    view = credit_view(session, credit_note)
    if not view["can_refund"]:
        raise BillingError("Aucun remboursement n'est dû sur cet avoir")
    customer = session.get(Customer, credit_note.customer_id) if credit_note.customer_id else None
    movement = CashMovement(
        company_id=credit_note.company_id, account_id=account_id, direction="out", amount=view["refund_due"], status="actual",
        occurred_at=occurred_at or _now(), category="customer_refund", label=f"Remboursement avoir {credit_note.number}",
        counterparty=customer.name if customer else None, document_id=credit_note.id, customer_id=credit_note.customer_id, source=source,
    )  # fmt: skip
    session.add(movement)
    session.commit()
    change_status(session, event_bus, credit_note, "refunded", system=True)
    _publish(event_bus, REFUND_RECORDED, credit_note, {"amount": movement.amount, "movement_id": str(movement.id)})
    return movement


def on_document_status_changed(session: Session, event_bus: EventBus, doc: CommercialDocument, old_status: str) -> None:
    """Called by app.transactions.service.change_status. The customer's (or
    supplier's) answer surfaces everywhere as an event; an accepted credit
    note goes to internal validation (HITL); a refused one becomes a Task."""

    if doc.kind == K.CUSTOMER_CREDIT_NOTE and doc.status == "accepted":
        _publish(event_bus, CREDIT_NOTE_ACCEPTED, doc, {"amount": doc_total(doc)})
        request_credit_validation(session, event_bus, doc)
    elif doc.kind == K.CUSTOMER_CREDIT_NOTE and doc.status == "rejected":
        _publish(event_bus, CREDIT_NOTE_REJECTED, doc, {"amount": doc_total(doc)})
        customer = session.get(Customer, doc.customer_id) if doc.customer_id else None
        ActionsService(session, event_bus).create_manual_task(
            company_id=doc.company_id,
            title=f"Avoir {doc.number} refusé" + (f" par {customer.name}" if customer else "") + " : décider de la suite",
            description="Le client a refusé l'avoir proposé. Options : proposer un autre montant, un remplacement, ou clore la réclamation.",
            domain="sales",
            requires_decision=True,
            related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT,
            related_entity_id=doc.id,
        )
    elif doc.kind == K.SUPPLIER_CREDIT_NOTE and doc.status == "confirmed":
        _publish(event_bus, SUPPLIER_CREDIT_CONFIRMED, doc, {"amount": doc_total(doc)})
    elif doc.kind == K.SUPPLIER_CREDIT_NOTE and doc.status == "rejected":
        _publish(event_bus, SUPPLIER_CREDIT_REJECTED, doc, {"amount": doc_total(doc)})
    elif doc.kind == K.CUSTOMER_ORDER and doc.status == "acknowledged":
        _publish(event_bus, ORDER_ACKNOWLEDGED, doc, {})


# --- Deliveries, receptions, non-conformities ---------------------------------------------


_PHYSICAL = {K.CUSTOMER_ORDER: K.CUSTOMER_DELIVERY, K.PURCHASE_ORDER: K.RECEPTION}


def _key(line) -> str:
    return str(line.product_id) if line.product_id else (line.description or "?")


def fulfilment(session: Session, order: CommercialDocument, now: datetime | None = None) -> dict:
    """Ordered vs shipped vs delivered/received, per line, from the
    deliveries/receptions derived from the order -- with dates, delays,
    carriers and recorded non-conformities. Nothing counts as shipped or
    received without the corresponding document status."""

    if order.kind not in _PHYSICAL:
        raise BillingError("Le suivi de livraison concerne une commande")
    now = now or _now()
    physical_kind = _PHYSICAL[order.kind]
    done_status = "delivered" if physical_kind == K.CUSTOMER_DELIVERY else "received"
    children = [session.get(CommercialDocument, cid) for cid in document_children(session, order.id)]
    shipments = sorted([d for d in children if d is not None and d.kind == physical_kind and d.status != "cancelled"], key=lambda d: d.created_at)

    lines: dict[str, dict] = {}
    for ln in order.lines:
        row = lines.setdefault(_key(ln), {"key": _key(ln), "product_id": ln.product_id, "label": (ln.product.name if ln.product else None) or ln.description or "Article", "unit": ln.unit, "ordered": 0.0, "shipped": 0.0, "done": 0.0, "nonconforming": 0.0})
        row["ordered"] += ln.quantity
    for doc in shipments:
        for ln in doc.lines:
            row = lines.setdefault(_key(ln), {"key": _key(ln), "product_id": ln.product_id, "label": (ln.product.name if ln.product else None) or ln.description or "Article", "unit": ln.unit, "ordered": 0.0, "shipped": 0.0, "done": 0.0, "nonconforming": 0.0})
            if doc.status in {"shipped", done_status}:
                row["shipped"] += ln.quantity
            if doc.status == done_status:
                row["done"] += ln.quantity
                row["nonconforming"] += ln.quantity_nonconforming or 0.0
    for row in lines.values():
        row["remaining"] = round(max(0.0, row["ordered"] - row["done"]), 3)
        row["in_transit"] = round(max(0.0, row["shipped"] - row["done"]), 3)

    docs = []
    for d in shipments:
        due, done = _aware(d.due_at), _aware(d.completed_at)
        late_days = (done - due).days if (due and done and done > due) else ((now - due).days if (due and not done and now > due and d.status not in {done_status, "cancelled"}) else 0)
        docs.append({
            "id": d.id, "number": d.number, "status": d.status, "status_label": status_label(d.kind, d.status),
            "planned_at": d.due_at, "done_at": d.completed_at, "late_days": max(late_days, 0),
            "carrier": d.carrier, "tracking_number": d.tracking_number,
            "nonconforming_lines": sum(1 for ln in d.lines if (ln.quantity_nonconforming or 0) > 0),
        })  # fmt: skip
    ordered = sum(r["ordered"] for r in lines.values())
    done = sum(min(r["done"], r["ordered"]) for r in lines.values())
    in_transit = sum(r["in_transit"] for r in lines.values())
    if not shipments:
        state, label = "not_started", "Aucune livraison enregistrée" if physical_kind == K.CUSTOMER_DELIVERY else "Aucune réception enregistrée"
    elif ordered and done >= ordered - 1e-9:
        state, label = "complete", "Livrée en totalité" if physical_kind == K.CUSTOMER_DELIVERY else "Reçue en totalité"
    elif done > 0:
        state, label = "partial", "Livraison partielle" if physical_kind == K.CUSTOMER_DELIVERY else "Réception partielle"
    elif in_transit > 0:
        state, label = "in_transit", "Expédiée, en transit"
    else:
        state, label = "planned", "Planifiée" if physical_kind == K.CUSTOMER_DELIVERY else "Attendue"
    promised = _aware(order.due_at)
    late = any(d["late_days"] > 0 for d in docs) or (promised is not None and now > promised and state not in {"complete"})
    return {
        "order_id": order.id,
        "kind": "delivery" if physical_kind == K.CUSTOMER_DELIVERY else "reception",
        "state": state,
        "state_label": label,
        "is_late": late,
        "promised_at": order.due_at,
        "progress": round(done / ordered, 3) if ordered else 0.0,
        "lines": list(lines.values()),
        "documents": docs,
        "nonconforming_total": round(sum(r["nonconforming"] for r in lines.values()), 3),
    }


def parent_order(session: Session, doc: CommercialDocument) -> CommercialDocument | None:
    for parent_id in document_parents(session, doc.id):
        parent = session.get(CommercialDocument, parent_id)
        if parent is not None and parent.kind in _PHYSICAL:
            return parent
    return None


def report_nonconformity(session: Session, event_bus: EventBus, doc: CommercialDocument, line_id: uuid.UUID, quantity: float, note: str) -> dict:
    """A person records that part of a delivered/received line is not
    conforming. Opens (once per document) a V1 Risk, whose RiskCreated
    reaction creates the review Task like any other Risk."""

    if doc.kind not in {K.CUSTOMER_DELIVERY, K.RECEPTION}:
        raise BillingError("Une non-conformité se signale sur une livraison ou une réception")
    if doc.status not in {"delivered", "received"}:
        raise BillingError("Seule une livraison livrée / une réception reçue peut être déclarée non conforme")
    line = next((ln for ln in doc.lines if ln.id == line_id), None)
    if line is None:
        raise BillingError("Ligne introuvable")
    if quantity is None or quantity <= 0 or quantity > line.quantity:
        raise BillingError(f"Quantité non conforme invalide (entre 0 et {line.quantity:g})")
    if not (note or "").strip():
        raise BillingError("Décrivez la non-conformité constatée")
    line.quantity_nonconforming = float(quantity)
    line.nonconformity_note = note.strip()[:255]
    session.commit()
    _publish(event_bus, NONCONFORMITY_REPORTED, doc, {"line_id": str(line.id), "quantity": quantity, "note": line.nonconformity_note})

    title = f"Non-conformité — {doc.number}"
    risk = session.query(Risk).filter_by(company_id=doc.company_id, title=title, status=RiskStatus.OPEN).first()
    created = False
    if risk is None:
        party = session.get(Customer, doc.customer_id) if doc.kind == K.CUSTOMER_DELIVERY and doc.customer_id else (session.get(Supplier, doc.supplier_id) if doc.supplier_id else None)
        risk = Risk(
            company_id=doc.company_id, title=title, severity=RiskSeverity.MEDIUM, status=RiskStatus.OPEN,
            description=f"{quantity:g} × {(line.product.name if line.product else line.description) or 'article'} non conforme(s) ({line.nonconformity_note})"
            + (f" — {party.name}" if party else "") + ". Envisager un avoir et, si la marchandise vient d'un fournisseur, une réclamation.",
            related_entity_type=RelatedEntityType.COMMERCIAL_DOCUMENT, related_entity_id=doc.id,
        )  # fmt: skip
        session.add(risk)
        session.commit()
        created = True
        from app.intelligence.risks.service import RISK_CREATED

        event_bus.publish(BusinessEvent(event_type=RISK_CREATED, source="billing", payload={"risk_id": str(risk.id), "severity": risk.severity.value}))
    return {"line_id": line.id, "quantity_nonconforming": line.quantity_nonconforming, "note": line.nonconformity_note, "risk_id": risk.id, "risk_created": created}


# --- Orders: payment summary --------------------------------------------------------------------


def order_payment(session: Session, order: CommercialDocument, now: datetime | None = None) -> dict:
    """The payment position of an order, read from the invoices derived from it."""

    invoice_kind = K.CUSTOMER_INVOICE if order.kind == K.CUSTOMER_ORDER else K.SUPPLIER_INVOICE
    invoices = [d for d in (session.get(CommercialDocument, cid) for cid in document_children(session, order.id)) if d is not None and d.kind == invoice_kind]
    views = [settlement(session, d, now) for d in invoices]
    live = [v for v in views if v.get("available")]
    total = doc_total(order)
    if not live:
        return {"order_total": total, "invoiced": 0.0, "invoices": [{"id": v["invoice_id"], "number": v["number"], "status_label": v["status_label"]} for v in views], "state": "not_invoiced", "state_label": "Non facturée"}
    paid = round(sum(v["paid"] for v in live), 2)
    credited = round(sum(v["credited"] for v in live), 2)
    remaining = round(sum(v["remaining"] for v in live), 2)
    installments = [i for v in live for i in v["installments"]]
    upcoming = sorted([i for i in installments if i["state"] in {"due", "partial", "overdue"}], key=lambda i: i["due_at"])
    late = any(v["is_late"] for v in live)
    state = "paid" if remaining <= TOLERANCE else ("partially_paid" if paid + credited > TOLERANCE else "unpaid")
    return {
        "order_total": total,
        "invoiced": round(sum(v["total"] for v in live), 2),
        "paid": paid,
        "credited": credited,
        "remaining": remaining,
        "installments_paid": sum(1 for i in installments if i["state"] == "paid"),
        "installments_count": len(installments),
        "next_due": upcoming[0] if upcoming else None,
        "is_late": late,
        "overdue_amount": round(sum(v["overdue_amount"] for v in live), 2),
        "state": state,
        "state_label": {"paid": "Réglée", "partially_paid": "Partiellement réglée", "unpaid": "Non réglée"}[state] + (" — en retard" if late else ""),
        "invoices": [{"id": v["invoice_id"], "number": v["number"], "status_label": v["status_label"], "remaining": v.get("remaining")} for v in views],
    }


# --- Accounts (customer / supplier) ------------------------------------------------------------


@dataclass
class _Entry:
    date: datetime
    kind: str
    label: str
    amount: float  # + increases what the party owes (customer) / what we owe (supplier)
    document_id: uuid.UUID | None
    document_number: str | None
    account_ref: str | None
    simulated: bool
    note: str | None = None


def party_account(session: Session, company_id: uuid.UUID, *, customer_id: uuid.UUID | None = None, supplier_id: uuid.UUID | None = None, now: datetime | None = None) -> dict:
    """ONE balance per party, derived from invoices, payments, imputed credit
    notes and refunds -- the same function feeds the customer/supplier page,
    the order view and Finance, so they cannot disagree.

    Customer: balance > 0 = the customer owes us; < 0 = we owe the customer.
    Supplier: balance > 0 = we owe the supplier."""

    if bool(customer_id) == bool(supplier_id):
        raise BillingError("Un compte concerne un client ou un fournisseur")
    now = now or _now()
    is_customer = customer_id is not None
    invoice_kind = K.CUSTOMER_INVOICE if is_customer else K.SUPPLIER_INVOICE
    credit_kind = K.CUSTOMER_CREDIT_NOTE if is_customer else K.SUPPLIER_CREDIT_NOTE
    party_filter = {"customer_id": customer_id} if is_customer else {"supplier_id": supplier_id}
    refs = accounting_refs(session, company_id)["configured"]
    party_ref = refs.get("customer_receivable" if is_customer else "supplier_payable")
    bank_ref = refs.get("bank")

    invoices = [d for d in session.query(CommercialDocument).filter_by(company_id=company_id, kind=invoice_kind, **party_filter).all() if d.status in OPEN_INVOICE_STATUSES[invoice_kind]]
    views = {d.id: settlement(session, d, now) for d in invoices}
    invoice_ids = {d.id for d in invoices}
    entries: list[_Entry] = []
    for d in invoices:
        v = views[d.id]
        if not v.get("available"):
            continue
        entries.append(_Entry(_aware(d.issued_at) or _aware(d.created_at), "invoice", f"Facture {d.number}", v["total"], d.id, d.number, party_ref, d.source == "simulated"))

    category = "customer_payment" if is_customer else "supplier_payment"
    party_col = CashMovement.customer_id if is_customer else CashMovement.supplier_id
    movements = session.query(CashMovement).filter(CashMovement.company_id == company_id, CashMovement.status == "actual", CashMovement.category == category).all()
    unallocated = []
    for m in movements:
        if m.document_id in invoice_ids:
            entries.append(_Entry(_aware(m.occurred_at), "payment", m.label or "Règlement", -m.amount, m.document_id, _number(session, m.document_id), bank_ref, _is_simulated(m.source)))
        elif m.document_id is None and getattr(m, party_col.key) == (customer_id or supplier_id):
            entries.append(_Entry(_aware(m.occurred_at), "unallocated_payment", m.label or "Paiement à rapprocher", -m.amount, None, None, bank_ref, _is_simulated(m.source), "Reçu, pas encore rapproché d'une facture"))
            unallocated.append({"id": m.id, "amount": m.amount, "occurred_at": m.occurred_at, "label": m.label, "simulated": _is_simulated(m.source)})

    credit_notes = session.query(CommercialDocument).filter_by(company_id=company_id, kind=credit_kind, **party_filter).all()
    pending_credits, refund_due, credit_on_account = [], 0.0, 0.0
    for cn in credit_notes:
        app = credit_application(session, cn)
        total = doc_total(cn) or 0.0
        if app is not None:
            # The whole credit leaves the balance once imputed: the part that
            # reduced the invoice, plus any excess (a refund owed, or a credit
            # kept on the account when nothing was invoiced).
            note = ("Imputé sur la facture" + (f", dont {_eur(app.refund_amount)} à rembourser" if app.refund_amount > TOLERANCE else "")) if app.invoice_id else "Crédit disponible sur le compte"
            entries.append(_Entry(_aware(app.applied_at), "credit_note", f"Avoir {cn.number}", -round(total, 2), cn.id, cn.number, party_ref, cn.source == "simulated", note))
            if app.invoice_id is None:
                credit_on_account += total
        elif cn.status in PENDING_CREDIT_STATUSES[credit_kind]:
            pending_credits.append({"id": cn.id, "number": cn.number, "amount": total, "status": cn.status, "status_label": status_label(cn.kind, cn.status)})
        if is_customer:
            v = credit_view(session, cn)
            refund_due += v["refund_due"]
            if v["refund"]:
                entries.append(_Entry(_aware(v["refund"]["occurred_at"]), "refund", f"Remboursement avoir {cn.number}", v["refund"]["amount"], cn.id, cn.number, bank_ref, cn.source == "simulated"))

    entries.sort(key=lambda e: (e.date or now, 0 if e.kind == "invoice" else 1))
    running, statement = 0.0, []
    for e in entries:
        running = round(running + e.amount, 2)
        statement.append({"date": e.date, "kind": e.kind, "label": e.label, "amount": round(e.amount, 2), "balance": running, "document_id": e.document_id, "document_number": e.document_number, "account_ref": e.account_ref, "simulated": e.simulated, "note": e.note})

    live = [v for v in views.values() if v.get("available")]
    upcoming = sorted([i | {"invoice_number": v["number"], "invoice_id": v["invoice_id"]} for v in live for i in v["installments"] if i["state"] in {"due", "partial", "overdue"}], key=lambda i: i["due_at"])
    balance = round(sum(e.amount for e in entries), 2)
    return {
        "party_type": "customer" if is_customer else "supplier",
        "party_id": customer_id or supplier_id,
        "invoiced": round(sum(v["total"] for v in live), 2),
        "paid": round(sum(v["paid"] for v in live), 2),
        "credited": round(sum(v["credited"] for v in live), 2),
        "outstanding": round(sum(v["remaining"] for v in live), 2),
        "overdue": round(sum(v["overdue_amount"] for v in live), 2),
        "unallocated": round(sum(u["amount"] for u in unallocated), 2),
        "credit_on_account": round(credit_on_account, 2),
        "refund_due": round(refund_due, 2),
        "balance": balance,
        "is_up_to_date": abs(balance) <= TOLERANCE and not unallocated,
        "next_due": upcoming[0] if upcoming else None,
        "open_invoices": [
            {"id": v["invoice_id"], "number": v["number"], "total": v["total"], "remaining": v["remaining"], "state_label": v["state_label"], "is_late": v["is_late"],
             "installments_paid": v["installments_paid"], "installments_count": v["installments_count"], "next_due": v["next_due"]}
            for v in live if v["remaining"] > TOLERANCE
        ],  # fmt: skip
        "unallocated_payments": unallocated,
        "pending_credit_notes": pending_credits,
        "statement": statement,
        "has_simulated": any(e["simulated"] for e in statement),
        "method": "Solde = factures émises − paiements reçus − avoirs imputés + remboursements versés. Les avoirs non validés ne sont pas déduits.",
    }


# --- Company-wide overview (Finance, Centre de contrôle) ---------------------------------------------


def billing_overview(session: Session, company_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or _now()
    customer_invoices = [d for d in session.query(CommercialDocument).filter_by(company_id=company_id, kind=K.CUSTOMER_INVOICE).all() if d.status in OPEN_INVOICE_STATUSES[K.CUSTOMER_INVOICE]]
    supplier_invoices = [d for d in session.query(CommercialDocument).filter_by(company_id=company_id, kind=K.SUPPLIER_INVOICE).all() if d.status in OPEN_INVOICE_STATUSES[K.SUPPLIER_INVOICE]]
    cv = [(d, settlement(session, d, now)) for d in customer_invoices]
    sv = [(d, settlement(session, d, now)) for d in supplier_invoices]
    cv = [(d, v) for d, v in cv if v.get("available")]
    sv = [(d, v) for d, v in sv if v.get("available")]

    def party_name(d: CommercialDocument) -> str | None:
        if KINDS[d.kind].party == "supplier":
            p = session.get(Supplier, d.supplier_id) if d.supplier_id else None
        else:
            p = session.get(Customer, d.customer_id) if d.customer_id else None
        return p.name if p else None

    upcoming = sorted(
        [{"invoice_id": d.id, "invoice_number": d.number, "party": party_name(d), "due_at": i["due_at"], "amount": i["remaining"], "label": i["label"], "state": i["state"], "days_late": i["days_late"]}
         for d, v in cv for i in v["installments"] if i["state"] in {"due", "partial", "overdue"}],
        key=lambda x: x["due_at"],
    )  # fmt: skip
    unallocated = [
        {"id": m.id, "amount": m.amount, "occurred_at": m.occurred_at, "label": m.label, "direction": m.direction, "counterparty": m.counterparty, "customer_id": m.customer_id, "supplier_id": m.supplier_id, "simulated": _is_simulated(m.source)}
        for m in session.query(CashMovement).filter(CashMovement.company_id == company_id, CashMovement.status == "actual", CashMovement.category.in_(["customer_payment", "supplier_payment"]), CashMovement.document_id.is_(None)).order_by(CashMovement.occurred_at.desc()).all()
    ]  # fmt: skip

    credits = session.query(CommercialDocument).filter(CommercialDocument.company_id == company_id, CommercialDocument.kind.in_(list(CREDIT_KINDS))).all()
    credit_rows = []
    for cn in credits:
        v = credit_view(session, cn)
        credit_rows.append({"id": cn.id, "number": cn.number, "kind": cn.kind.value, "party": party_name(cn), "amount": v["amount"], "status": cn.status, "status_label": v["status_label"],
                            "needs_action": v["can_apply"] or v["can_refund"] or v["can_request_validation"] or bool(v["validation_task_id"]) or cn.status in {"submitted", "requested"},
                            "refund_due": v["refund_due"], "validation_task_id": v["validation_task_id"]})  # fmt: skip

    orders = session.query(CommercialDocument).filter(CommercialDocument.company_id == company_id, CommercialDocument.kind == K.CUSTOMER_ORDER, CommercialDocument.status.in_(["sent", "acknowledged"])).all()
    awaiting = [{"id": o.id, "number": o.number, "party": party_name(o), "status": o.status, "status_label": status_label(o.kind, o.status), "total": doc_total(o), "since": o.updated_at} for o in orders]

    physical = []
    for o in session.query(CommercialDocument).filter(CommercialDocument.company_id == company_id, CommercialDocument.kind.in_([K.CUSTOMER_ORDER, K.PURCHASE_ORDER]), CommercialDocument.status.in_(["confirmed", "delivered", "sent", "received"])).all():
        f = fulfilment(session, o, now)
        if f["state"] in {"partial", "in_transit", "planned"} or f["is_late"] or f["nonconforming_total"] > 0:
            physical.append({"order_id": o.id, "number": o.number, "party": party_name(o), "kind": f["kind"], "state": f["state"], "state_label": f["state_label"], "is_late": f["is_late"], "progress": f["progress"], "nonconforming": f["nonconforming_total"]})

    return {
        "receivables": {
            "outstanding": round(sum(v["remaining"] for _, v in cv), 2),
            "overdue": round(sum(v["overdue_amount"] for _, v in cv), 2),
            "overdue_invoices": [{"id": d.id, "number": d.number, "party": party_name(d), "overdue": v["overdue_amount"], "remaining": v["remaining"]} for d, v in cv if v["is_late"]],
            "upcoming": upcoming[:8],
        },
        "payables": {
            "outstanding": round(sum(v["remaining"] for _, v in sv), 2),
            "overdue": round(sum(v["overdue_amount"] for _, v in sv), 2),
            "open_invoices": [{"id": d.id, "number": d.number, "party": party_name(d), "remaining": v["remaining"], "is_late": v["is_late"], "status_label": v["status_label"]} for d, v in sv if v["remaining"] > TOLERANCE],
        },
        "unallocated_payments": unallocated,
        "credit_notes": credit_rows,
        "refunds_due": round(sum(r["refund_due"] for r in credit_rows), 2),
        "orders_awaiting_confirmation": awaiting,
        "deliveries_to_watch": physical,
        "accounting_refs": accounting_refs(session, company_id),
        "method": "Calculé à la lecture depuis les factures, les paiements enregistrés et les avoirs imputés. Aucun montant n'est saisi deux fois.",
    }

