import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.deps import CurrentUser, get_current_user, require
from app.access.policy import ACTION_SUBMIT_EMAIL, WRITE_COMMUNICATIONS
from app.ai.llm import LLMClient, get_llm_client
from app.communications import mailboxes as mailbox_views
from app.communications import service
from app.core.entities import Communication, Company
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus

router = APIRouter(tags=["communications"])


class DraftIn(BaseModel):
    purpose: str
    object_type: str | None = None
    object_id: uuid.UUID | None = None
    reply_to_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class DraftUpdateIn(BaseModel):
    subject: str | None = None
    body: str | None = None
    to_address: str | None = None


def _get(db: Session, company: Company, communication_id: uuid.UUID) -> Communication:
    communication = db.get(Communication, communication_id)
    if communication is None or communication.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Message introuvable", "Message not found"))
    return communication


def _guard(fn, db: Session):
    try:
        return fn()
    except service.CommunicationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/communications")
def list_communications(box: str = "inbox", channel: str | None = None, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    return _guard(lambda: service.list_communications(db, company.id, box=box, channel=channel), db)


@router.get("/communications/purposes")
def purposes() -> dict:
    return service.purpose_labels()


# Read-only views (brain/communications.md "Boîtes fonctionnelles"): declared
# before /communications/{id} so these paths are not parsed as an id.
@router.get("/communications/mailboxes")
def mailboxes(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return mailbox_views.mailbox_overview(db, company.id)


@router.get("/communications/mailboxes/{key}")
def mailbox_messages(key: str, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    if key not in mailbox_views.MAILBOX_KEYS:
        raise HTTPException(status_code=404, detail=tx("Boîte inconnue", "Unknown mailbox"))
    return mailbox_views.list_mailbox(db, company.id, key)


@router.get("/communications/performance")
def follow_up_performance(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return mailbox_views.follow_up_performance(db, company.id)


@router.get("/communications/campaigns")
def campaigns(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return mailbox_views.campaign_performance(db, company.id)


@router.get("/communications/{communication_id}")
def get_communication(communication_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return service.get_detail(db, _get(db, company, communication_id))


@router.post("/communications/{communication_id}/analyze")
def analyze(
    communication_id: uuid.UUID,
    db: Session = Depends(get_db),
    company: Company = Depends(current_company),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    return service.analyze(db, _get(db, company, communication_id), llm).to_dict()


@router.post("/communications/drafts")
def create_draft(
    payload: DraftIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    llm: LLMClient = Depends(get_llm_client),
    _: CurrentUser = Depends(require(WRITE_COMMUNICATIONS)),
) -> dict:
    draft = _guard(lambda: service.compose_draft(db, event_bus, llm, company, **payload.model_dump()), db)
    return service.get_detail(db, draft)


@router.patch("/communications/{communication_id}")
def update_draft(
    communication_id: uuid.UUID,
    payload: DraftUpdateIn,
    db: Session = Depends(get_db),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_COMMUNICATIONS)),
) -> dict:
    draft = _get(db, company, communication_id)
    _guard(lambda: service.update_draft(db, draft, payload.model_dump(exclude_unset=True)), db)
    return service.get_detail(db, draft)


@router.post("/communications/{communication_id}/submit")
def submit(
    communication_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(ACTION_SUBMIT_EMAIL)),
) -> dict:
    draft = _get(db, company, communication_id)
    task = _guard(lambda: service.submit_draft(db, event_bus, draft), db)
    return {"task_id": task.id, "communication": service.get_detail(db, draft)}


@router.get("/follow-ups")
def follow_ups(db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    return {
        "computed_at_read_time": True,
        "note": tx("Calculé à l'ouverture de la page : aucun planificateur n'envoie de relance automatiquement.", "Computed when the page opens: no scheduler sends follow-ups automatically."),
        "items": service.list_follow_ups(db, company.id),
    }
