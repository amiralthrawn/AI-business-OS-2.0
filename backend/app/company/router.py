from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.company.schemas import CompanyRead, CompanyUpdate
from app.core.entities import Company
from app.database import get_db

router = APIRouter(prefix="/company", tags=["company"])


def _the_company(db: Session) -> Company:
    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))
    return company


@router.get("", response_model=CompanyRead)
def get_company(db: Session = Depends(get_db)) -> Company:
    return _the_company(db)


@router.patch("", response_model=CompanyRead)
def update_company(payload: CompanyUpdate, db: Session = Depends(get_db)) -> Company:
    company = _the_company(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company
