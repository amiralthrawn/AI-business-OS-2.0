from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.business_context.schemas import BusinessContextRead, BusinessContextUpdate, ConfigurationSuggestionRead
from app.business_context.service import BusinessContextService
from app.core.entities import BusinessContext, Company
from app.database import get_db

router = APIRouter(prefix="/business-context", tags=["business-context"])


def _the_company(db: Session) -> Company:
    # Single-company MVP, same assumption Home already makes: there is
    # exactly one Company. Multi-tenancy would replace this with a real
    # lookup, not change the shape of BusinessContext itself.
    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))
    return company


@router.get("", response_model=BusinessContextRead)
def get_business_context(db: Session = Depends(get_db)) -> BusinessContext:
    company = _the_company(db)
    return BusinessContextService(db).get_or_create(company.id)


@router.patch("", response_model=BusinessContextRead)
def update_business_context(payload: BusinessContextUpdate, db: Session = Depends(get_db)) -> BusinessContext:
    company = _the_company(db)
    return BusinessContextService(db).update(company.id, **payload.model_dump())


@router.get("/suggestions", response_model=list[ConfigurationSuggestionRead])
def get_configuration_suggestions(db: Session = Depends(get_db)) -> list[ConfigurationSuggestionRead]:
    company = _the_company(db)
    suggestions = BusinessContextService(db).suggest_configuration_changes(company.id)
    return [ConfigurationSuggestionRead(**vars(s)) for s in suggestions]
