import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.deps import CurrentUser, get_current_user, require
from app.access.policy import VIEW_OWNERSHIP, VIEW_TREASURY, WRITE_TREASURY
from app.core.entities import BankAccount, BusinessContext, CashMovement, Company, Shareholder, ValueBasis
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.treasury import service

treasury_router = APIRouter(prefix="/treasury", tags=["treasury"], dependencies=[Depends(require(VIEW_TREASURY))])
ownership_router = APIRouter(prefix="/ownership", tags=["ownership"], dependencies=[Depends(require(VIEW_OWNERSHIP))])


class AccountIn(BaseModel):
    name: str
    bank_name: str | None = None
    kind: str = "current"
    # A full IBAN / card number may be typed; only a masked form is stored.
    identifier: str | None = None
    balance: float = 0.0
    balance_basis: ValueBasis = ValueBasis.DECLARED
    balance_as_of: datetime | None = None
    interest_rate: float | None = None
    maturity_at: datetime | None = None


class MovementIn(BaseModel):
    account_id: uuid.UUID | None = None
    direction: str
    amount: float
    status: str
    occurred_at: datetime
    category: str = "other"
    label: str | None = None
    counterparty: str | None = None


class ShareholderIn(BaseModel):
    name: str
    kind: str = "founder"
    shares: float
    share_class: str = "ordinaires"
    economic_rights_pct: float | None = None
    employee_id: uuid.UUID | None = None


class FinanceSettingsIn(BaseModel):
    min_cash: float | None = None
    declared_valuation: float | None = None
    declared_valuation_date: str | None = None
    revenue_multiple_min: float | None = None
    revenue_multiple_max: float | None = None
    # V2.2: account references to confirm with the accountant, e.g.
    # {"customer_receivable": "411", "bank": "512", "purchases": "601"}.
    accounting_refs: dict[str, str] | None = None


@treasury_router.get("/overview")
def overview(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return service.treasury_overview(db, company.id)


@treasury_router.post("/accounts")
def add_account(payload: AccountIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_TREASURY))) -> dict:
    if payload.kind not in {"current", "savings", "card", "loan"}:
        raise HTTPException(status_code=400, detail=tx("Type de compte inconnu", "Unknown account type"))
    try:
        masked = service.mask_identifier(payload.identifier, payload.kind)
    except service.TreasuryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    account = BankAccount(
        company_id=company.id, name=payload.name, bank_name=payload.bank_name, kind=payload.kind, masked_identifier=masked,
        balance=payload.balance, balance_basis=payload.balance_basis, balance_as_of=payload.balance_as_of or datetime.now(timezone.utc),
        interest_rate=payload.interest_rate, maturity_at=payload.maturity_at, source="manual",
    )  # fmt: skip
    db.add(account)
    db.commit()
    return {"id": account.id, "masked_identifier": account.masked_identifier}


@treasury_router.post("/movements")
def add_movement(payload: MovementIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_TREASURY))) -> dict:
    if payload.direction not in {"in", "out"} or payload.status not in {"actual", "planned", "estimated"} or payload.amount <= 0:
        raise HTTPException(status_code=400, detail=tx("Flux invalide (sens in/out, statut actual/planned/estimated, montant > 0)", "Invalid flow (direction in/out, status actual/planned/estimated, amount > 0)"))
    movement = CashMovement(company_id=company.id, source="manual", **payload.model_dump())
    db.add(movement)
    db.commit()
    return {"id": movement.id}


@treasury_router.post("/monitor")
def monitor(db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company)) -> dict:
    return service.monitor_cash(db, event_bus, company.id)


@ownership_router.get("")
def get_ownership(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return service.ownership(db, company.id)


@ownership_router.get("/company-overview")
def company_overview(db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    data = service.company_overview(db, company.id)
    if not user.can(VIEW_TREASURY):
        data.update({"cash_now": None, "debt": None, "projection_90": None, "below_min_cash": None})
    return data


@ownership_router.post("/shareholders")
def add_shareholder(payload: ShareholderIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_TREASURY))) -> dict:
    if payload.shares <= 0:
        raise HTTPException(status_code=400, detail=tx("Nombre de parts invalide", "Invalid number of shares"))
    holder = Shareholder(company_id=company.id, **payload.model_dump())
    db.add(holder)
    db.commit()
    return service.ownership(db, company.id)


@ownership_router.patch("/settings")
def update_settings(payload: FinanceSettingsIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_TREASURY))) -> dict:
    ctx = db.query(BusinessContext).filter_by(company_id=company.id).first()
    if ctx is None:
        raise HTTPException(status_code=404, detail=tx("Contexte métier non configuré", "Business context not configured"))
    settings = dict(ctx.finance_settings or {})
    settings.update(payload.model_dump(exclude_unset=True))
    ctx.finance_settings = settings
    db.commit()
    return settings
