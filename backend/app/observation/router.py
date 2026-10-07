from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.entities import Company
from app.core.events.bus import EventBus
from app.database import get_db
from app.dependencies import get_event_bus
from app.observation import observable_registry
from app.observation.engine import run_observation_sweep

router = APIRouter(prefix="/observation", tags=["observation"])


@router.post("/sweep")
def trigger_observation_sweep(
    db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus)
) -> dict:
    """Manually triggers the Observation Engine sweep (see
    app.observation.engine for why this isn't a scheduled job in the MVP)."""

    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))

    return run_observation_sweep(db, event_bus, observable_registry, company.id)
