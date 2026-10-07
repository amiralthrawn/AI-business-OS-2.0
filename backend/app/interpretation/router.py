from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.ai.capabilities import capability_registry
from app.ai.llm import LLMClient, get_llm_client
from app.core.entities import Company
from app.core.events.bus import EventBus
from app.database import get_db
from app.dependencies import get_event_bus
from app.interpretation.engine import run_interpretation_sweep

router = APIRouter(prefix="/interpretation", tags=["interpretation"])


@router.post("/sweep")
def trigger_interpretation_sweep(
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    event_bus: EventBus = Depends(get_event_bus),
) -> dict:
    """Manually triggers the Interpretation Engine sweep (see
    app.interpretation.engine for why this isn't a scheduled job in the MVP,
    same reasoning as the Observation Engine's own manual trigger)."""

    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))

    return run_interpretation_sweep(db, event_bus, capability_registry, llm, company.id)
