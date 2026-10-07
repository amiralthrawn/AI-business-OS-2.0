"""The single place V2 code resolves "which company" from.

The product is still single-company (brain/decisions.md, V1 audit): V1
routers each call `db.query(Company).first()` themselves. V2 routers go
through this one function instead, so the day a request carries a tenant
(auth token -> company), exactly one function changes for all V2 code.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.entities import Company
from app.database import get_db


def current_company(db: Session = Depends(get_db)) -> Company:
    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))
    return company
