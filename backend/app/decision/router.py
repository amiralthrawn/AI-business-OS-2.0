from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.ai.capabilities import capability_registry
from app.ai.llm import LLMClient, get_llm_client
from app.core.entities import Company
from app.core.events.bus import EventBus
from app.database import get_db
from app.decision.engine import run_decision_sweep
from app.dependencies import get_event_bus

router = APIRouter(prefix="/decision", tags=["decision"])


@router.post("/sweep")
def trigger_decision_sweep(
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Manually triggers the Decision Intelligence sweep (see
    app.decision.engine for why this isn't a scheduled job in the MVP, same
    reasoning as the Observation/Interpretation Engines' own manual triggers)."""

    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))

    return run_decision_sweep(db, event_bus, capability_registry, llm, company.id)
