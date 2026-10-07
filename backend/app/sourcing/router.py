import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import current_locale, tx
from app.access.deps import CurrentUser, require
from app.access.policy import VIEW_PROCUREMENT, WRITE_PROCUREMENT
from app.core.entities import AIRun, CommercialDocument, Company, SourcingLead
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.sourcing import service

router = APIRouter(prefix="/sourcing", tags=["sourcing"], dependencies=[Depends(require(VIEW_PROCUREMENT))])


class LeadIn(BaseModel):
    name: str
    website: str | None = None
    country: str | None = None
    source_url: str | None = None
    found_price: float | None = None
    note: str | None = None


def _localized_text(text: str | None) -> str | None:
    from app.sourcing.service import STEP_RULES as SOURCING_STEPS
    from app.website.service import STEP_RULES as WEBSITE_STEPS

    if current_locale() == "fr" or not text:
        return text
    for pattern, english in (*WEBSITE_STEPS, *SOURCING_STEPS):
        m = pattern.match(text)
        if m:
            return english.format(**m.groupdict())
    return text


def run_out(run: AIRun | None) -> dict | None:
    if run is None:
        return None
    from app.website.service import localized_result

    steps = [step | {"label": _localized_text(step.get("label")), "detail": _localized_text(step.get("detail"))} for step in run.steps]
    result = localized_result(run.result) if run.kind == "website_audit" else run.result
    return {"id": run.id, "kind": run.kind, "mode": run.mode, "status": run.status, "target": run.target, "started_at": run.started_at, "finished_at": run.finished_at, "steps": steps, "result": result}


def lead_out(lead: SourcingLead) -> dict:
    return {
        "id": lead.id, "name": lead.name, "website": lead.website, "country": lead.country, "source_kind": lead.source_kind,
        "source_url": lead.source_url, "snippet": lead.snippet, "found_price": lead.found_price, "price_basis": lead.price_basis.value,
        "facts": lead.facts, "status": lead.status, "supplier_id": lead.supplier_id, "retrieved_at": lead.retrieved_at,
    }  # fmt: skip


def _pr(db: Session, company: Company, pr_id: uuid.UUID) -> CommercialDocument:
    pr = db.get(CommercialDocument, pr_id)
    if pr is None or pr.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Demande d'achat introuvable", "Purchase request not found"))
    return pr


@router.get("/purchase-requests/{pr_id}")
def sourcing_state(pr_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    pr = _pr(db, company, pr_id)
    last = db.query(AIRun).filter_by(kind="sourcing", subject_id=pr.id).order_by(AIRun.started_at.desc()).first()
    leads = db.query(SourcingLead).filter_by(purchase_request_id=pr.id).order_by(SourcingLead.created_at).all()
    return {"run": run_out(last), "leads": [lead_out(x) for x in leads], "web_search_configured": service.default_web_provider() is not None}


@router.post("/purchase-requests/{pr_id}/run")
def run(pr_id: uuid.UUID, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PROCUREMENT))) -> dict:
    try:
        result = service.run_sourcing(db, event_bus, _pr(db, company, pr_id))
    except service.SourcingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run_out(result)


@router.post("/purchase-requests/{pr_id}/leads")
def add_manual_lead(pr_id: uuid.UUID, payload: LeadIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PROCUREMENT))) -> dict:
    """A supplier a human found themselves -- recorded with its source."""

    from datetime import datetime, timezone

    from app.core.entities import ValueBasis

    pr = _pr(db, company, pr_id)
    line = next((ln for ln in pr.lines if ln.product_id), None)
    lead = SourcingLead(
        company_id=company.id, purchase_request_id=pr.id, product_id=line.product_id if line else None, name=payload.name,
        website=payload.website, country=payload.country, source_kind="manual", source_url=payload.source_url, snippet=payload.note,
        found_price=payload.found_price, price_basis=ValueBasis.DECLARED if payload.found_price is not None else ValueBasis.UNKNOWN,
        facts={}, retrieved_at=datetime.now(timezone.utc),
    )  # fmt: skip
    db.add(lead)
    db.commit()
    return lead_out(lead)


@router.post("/leads/{lead_id}/convert")
def convert(lead_id: uuid.UUID, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), user: CurrentUser = Depends(require(WRITE_PROCUREMENT))) -> dict:
    lead = db.get(SourcingLead, lead_id)
    if lead is None or lead.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Piste introuvable", "Lead not found"))
    try:
        quote = service.convert_lead(db, event_bus, lead, owner_user_id=user.profile.id if user.profile else None)
    except service.SourcingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"supplier_quote_id": quote.id, "supplier_id": lead.supplier_id}


@router.post("/leads/{lead_id}/discard")
def discard(lead_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PROCUREMENT))) -> dict:
    lead = db.get(SourcingLead, lead_id)
    if lead is None or lead.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Piste introuvable", "Lead not found"))
    lead.status = "discarded"
    db.commit()
    return lead_out(lead)
