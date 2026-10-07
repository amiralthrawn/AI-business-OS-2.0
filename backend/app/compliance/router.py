import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import text_of, tx
from app.access.deps import CurrentUser, require
from app.access.policy import VIEW_COMPLIANCE, WRITE_COMPLIANCE
from app.ai.llm import LLMClient, get_llm_client
from app.communications.service import compose_draft
from app.compliance import service
from app.core.entities import Company, Contact, RelatedEntityType, Supplier, Task
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.objects.links import create_link

router = APIRouter(prefix="/compliance", tags=["compliance"], dependencies=[Depends(require(VIEW_COMPLIANCE))])


class RequestIn(BaseModel):
    title: str
    category: str
    description: str | None = None
    due_at: datetime | None = None


class ExpertIn(BaseModel):
    name: str
    supplier_kind: str
    country: str | None = None
    fee_rate_min: float | None = None
    fee_rate_max: float | None = None
    contact_email: str | None = None
    contact_name: str | None = None


def _task(db: Session, company: Company, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.company_id != company.id or task.domain != service.COMPLIANCE_DOMAIN:
        raise HTTPException(status_code=404, detail=tx("Demande introuvable", "Request not found"))
    return task


@router.get("/categories")
def categories() -> dict:
    return {k: service.category_label(k) for k in service.CATEGORIES}


@router.get("/requests")
def list_requests(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    return service.list_requests(db, company.id)


@router.post("/requests")
def create_request(payload: RequestIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_COMPLIANCE))) -> dict:
    try:
        task = service.create_request(db, event_bus, company.id, **payload.model_dump())
    except service.ComplianceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task.id}


@router.get("/requests/{task_id}/recommendation")
def recommendation(task_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return service.recommend(db, _task(db, company, task_id))


@router.post("/requests/{task_id}/ask-expert/{supplier_id}")
def ask_expert(
    task_id: uuid.UUID, supplier_id: uuid.UUID, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company), llm: LLMClient = Depends(get_llm_client), _: CurrentUser = Depends(require(WRITE_COMPLIANCE)),
) -> dict:  # fmt: skip
    """Prepares the intervention request to the expert as a DRAFT email,
    linked to the compliance request -- sent only after human validation;
    no engagement or payment happens here."""

    task = _task(db, company, task_id)
    expert = db.get(Supplier, supplier_id)
    if expert is None or expert.company_id != company.id or expert.supplier_kind == "goods":
        raise HTTPException(status_code=404, detail=tx("Cabinet introuvable", "Firm not found"))
    draft = compose_draft(db, event_bus, llm, company, purpose="expert_request", object_type="supplier", object_id=expert.id)
    # A draft in the interface language; the person reviews and edits it before any sending (HITL).
    title, description = text_of(task, "title"), text_of(task, "description")
    draft.subject = tx(f"Demande d'intervention — {title}", f"Request for assistance — {title}")
    draft.body = tx(
        f"Bonjour,\n\nNous souhaiterions votre intervention sur le sujet suivant : {title}.\n\n"
        f"{description or '[Décrire la demande]'}\n\n"
        + (f"Échéance souhaitée : {task.due_at.date().isoformat()}.\n\n" if task.due_at else "")
        + f"Pourriez-vous nous indiquer vos disponibilités et une estimation de vos honoraires ?\n\nBien cordialement,\n{company.name}",
        f"Hello,\n\nWe would like your assistance on the following matter: {title}.\n\n"
        f"{description or '[Describe the request]'}\n\n"
        + (f"Desired deadline: {task.due_at.date().isoformat()}.\n\n" if task.due_at else "")
        + f"Could you let us know your availability and an estimate of your fees?\n\nBest regards,\n{company.name}",
    )
    db.commit()
    create_link(db, company_id=company.id, source_type="communication", source_id=draft.id, target_type="task", target_id=task.id, relation="concerns", origin="system")
    return {"draft_id": draft.id}


@router.get("/experts")
def list_experts(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    experts = db.query(Supplier).filter(Supplier.company_id == company.id, Supplier.supplier_kind != "goods").order_by(Supplier.name).all()
    return [
        {"id": e.id, "name": e.name, "kind": e.supplier_kind, "kind_label": service.expert_kind_label(e.supplier_kind), "fee_rate_min": e.fee_rate_min, "fee_rate_max": e.fee_rate_max, "country": e.country}
        for e in experts
    ]


@router.post("/experts")
def add_expert(payload: ExpertIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_COMPLIANCE))) -> dict:
    if payload.supplier_kind not in service.EXPERT_KINDS:
        raise HTTPException(status_code=400, detail=tx("Type de cabinet inconnu", "Unknown firm type"))
    expert = Supplier(company_id=company.id, name=payload.name, country=payload.country, supplier_kind=payload.supplier_kind, fee_rate_min=payload.fee_rate_min, fee_rate_max=payload.fee_rate_max, certifications=[])
    db.add(expert)
    db.flush()
    if payload.contact_email:
        db.add(Contact(company_id=company.id, name=payload.contact_name or payload.contact_email, email=payload.contact_email, related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=expert.id))
    db.commit()
    return {"id": expert.id}
