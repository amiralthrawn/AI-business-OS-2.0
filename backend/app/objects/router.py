import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.deps import CurrentUser, get_current_user
from app.access.policy import DOMAIN_VIEW_PERMISSION, OBJECT_VIEW_PERMISSION, WRITE_COMMUNICATIONS
from app.core.entities import CommercialDocument, Company, Contact, Customer, Product, Supplier
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.objects.context import build_context
from app.objects.links import LinkError, create_link, delete_link
from app.objects.registry import OBJECT_TYPES, summarize

router = APIRouter(prefix="/objects", tags=["objects"])


class LinkIn(BaseModel):
    source_type: str
    source_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    relation: str = "concerns"
    origin: str = "manual"


@router.get("/{obj_type}/{obj_id}/context")
def object_context(
    obj_type: str,
    obj_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if obj_type not in OBJECT_TYPES:
        raise HTTPException(status_code=404, detail=tx(f"Type d'objet inconnu : {obj_type}", f"Unknown object type: {obj_type}"))
    try:
        context = build_context(db, user, obj_type, obj_id).to_dict()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    needed = DOMAIN_VIEW_PERMISSION.get(context["object"]["domain"]) if obj_type == "commercial_document" else OBJECT_VIEW_PERMISSION.get(obj_type)
    if needed and not user.can(needed):
        raise HTTPException(status_code=403, detail=tx("Votre profil n'a pas accès à cet objet.", "Your profile does not have access to this object."))
    # Related objects the profile cannot open are not listed (no dead links, no leak).
    context["related"] = [g for g in context["related"] if not OBJECT_VIEW_PERMISSION.get(g["type"]) or user.can(OBJECT_VIEW_PERMISSION[g["type"]])]
    return context


@router.get("/search")
def search_objects(
    q: str = Query(min_length=1),
    types: list[str] | None = Query(default=None),
    limit: int = 20,
    db: Session = Depends(get_db),
    company: Company = Depends(current_company),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """One search box for every picker (link an email to a quote, pick a
    customer or a product while quoting)."""

    wanted = set(types or ["customer", "supplier", "product", "contact", "commercial_document"])
    like = f"%{q}%"
    results = []
    sources = [
        ("customer", Customer, [Customer.name]),
        ("supplier", Supplier, [Supplier.name]),
        ("product", Product, [Product.name, Product.sku]),
        ("contact", Contact, [Contact.name, Contact.email]),
        ("commercial_document", CommercialDocument, [CommercialDocument.number, CommercialDocument.title, CommercialDocument.external_reference]),
    ]
    for key, model, columns in sources:
        if key not in wanted:
            continue
        condition = columns[0].ilike(like)
        for column in columns[1:]:
            condition = condition | column.ilike(like)
        for row in db.query(model).filter(model.company_id == company.id, condition).limit(limit).all():
            summary = asdict(summarize(key, row))
            needed = DOMAIN_VIEW_PERMISSION.get(summary["domain"]) if key == "commercial_document" else OBJECT_VIEW_PERMISSION.get(key)
            if not needed or user.can(needed):
                results.append(summary)
    return results[:limit]


@router.post("/links")
def link_objects(
    payload: LinkIn,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    if not user.can(WRITE_COMMUNICATIONS):
        raise HTTPException(status_code=403, detail=tx("Votre rôle ne permet pas de lier des objets.", "Your role does not allow linking objects."))
    try:
        link = create_link(db, company_id=company.id, event_bus=event_bus, **payload.model_dump())
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": link.id, "source_type": link.source_type, "source_id": link.source_id, "target_type": link.target_type, "target_id": link.target_id, "relation": link.relation}


@router.delete("/links/{link_id}")
def unlink_objects(link_id: uuid.UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> dict:
    if not user.can(WRITE_COMMUNICATIONS):
        raise HTTPException(status_code=403, detail=tx("Votre rôle ne permet pas de modifier des liens.", "Your role does not allow changing links."))
    try:
        delete_link(db, link_id)
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True}
