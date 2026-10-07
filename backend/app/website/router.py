import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.deps import CurrentUser, require
from app.access.policy import VIEW_COMMUNICATIONS, WRITE_COMMUNICATIONS, WRITE_SETTINGS
from app.ai.llm import LLMClient, get_llm_client
from app.core.entities import AIRun, Company, WebsiteChangeProposal
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.sourcing.router import run_out
from app.website import service

router = APIRouter(prefix="/website", tags=["website"], dependencies=[Depends(require(VIEW_COMMUNICATIONS))])


class SiteIn(BaseModel):
    website_url: str | None


def _proposal_out(p: WebsiteChangeProposal) -> dict:
    return {
        "id": p.id, "page_url": p.page_url, "field": p.field, "current_value": p.current_value, "proposed_value": p.proposed_value,
        "rationale": service.display_rationale(p.rationale), "generated_by": p.generated_by, "status": p.status, "task_id": p.task_id,
    }  # fmt: skip


@router.get("")
def latest(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    run = db.query(AIRun).filter_by(company_id=company.id, kind="website_audit").order_by(AIRun.started_at.desc()).first()
    proposals = db.query(WebsiteChangeProposal).filter_by(run_id=run.id).all() if run else []
    return {"website_url": company.website_url, "run": run_out(run), "proposals": [_proposal_out(p) for p in proposals]}


@router.patch("/site")
def set_site(payload: SiteIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_SETTINGS))) -> dict:
    url = (payload.website_url or "").strip() or None
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    company.website_url = url
    db.commit()
    return {"website_url": company.website_url}


@router.post("/audit")
def run_audit(
    db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company),
    llm: LLMClient = Depends(get_llm_client), _: CurrentUser = Depends(require(WRITE_COMMUNICATIONS)),
) -> dict:  # fmt: skip
    run = service.audit_website(db, event_bus, company, llm=llm)
    return run_out(run) | {"proposals": [_proposal_out(p) for p in db.query(WebsiteChangeProposal).filter_by(run_id=run.id).all()]}


@router.post("/proposals/{proposal_id}/submit")
def submit(proposal_id: uuid.UUID, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_COMMUNICATIONS))) -> dict:
    proposal = db.get(WebsiteChangeProposal, proposal_id)
    if proposal is None or proposal.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Proposition introuvable", "Proposal not found"))
    try:
        task = service.submit_proposal(db, event_bus, proposal)
    except service.WebsiteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _proposal_out(proposal) | {"task_id": task.id}
