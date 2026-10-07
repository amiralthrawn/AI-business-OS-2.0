from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.connectors.ingestion import sync_connector
from app.connectors.registry import connector_registry
from app.core.entities import Communication, Company
from app.database import get_db

router = APIRouter(prefix="/connectors", tags=["connectors"])

_SOURCE_BY_CONNECTOR = {"email": "mock_email", "calendar": "mock_calendar", "website": "mock_website"}


def _status(db: Session, connector_type: str) -> dict:
    source = _SOURCE_BY_CONNECTOR.get(connector_type)
    if source is None:
        raise HTTPException(status_code=404, detail=tx(f"Connecteur inconnu : « {connector_type} »", f'Unknown connector: "{connector_type}"'))

    query = db.query(Communication).filter_by(source=source)
    last = query.order_by(Communication.occurred_at.desc()).first()
    return {
        "connector": connector_type,
        "ingested_count": query.count(),
        "last_ingested_at": last.occurred_at if last else None,
    }


@router.get("")
def list_connectors(db: Session = Depends(get_db)) -> dict:
    return {"connectors": [_status(db, connector_type) for connector_type in connector_registry.list_connectors()]}


@router.get("/{connector_type}/status")
def get_connector_status(connector_type: str, db: Session = Depends(get_db)) -> dict:
    return _status(db, connector_type)


@router.post("/{connector_type}/sync")
def trigger_connector_sync(connector_type: str, db: Session = Depends(get_db)) -> dict:
    """provider -> fetch -> normalize -> ingest -> summary (see
    app.connectors.ingestion.sync_connector). Deterministic and idempotent:
    re-running this for the same provider data never creates duplicates."""

    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))

    try:
        provider = connector_registry.get_connector(connector_type)
        result = sync_connector(db, connector_type, provider, company.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return asdict(result)
