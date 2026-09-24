import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.access.deps import CurrentUser, get_current_user, require
from app.access.policy import WRITE_CATALOG
from app.catalog import service
from app.core.entities import Company, Product, StockKind, StockPosition, Supplier, ValueBasis
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.domains.procurement.benchmark import benchmark_suppliers

router = APIRouter(tags=["catalog"])


class ProductIn(BaseModel):
    name: str
    sku: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    description: str | None = None
    unit: str | None = None
    sale_price: float | None = None
    unit_cost: float | None = None


class ProductUpdateIn(BaseModel):
    name: str | None = None
    sku: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    description: str | None = None
    unit: str | None = None
    sale_price: float | None = None
    sale_price_basis: ValueBasis | None = None
    unit_cost: float | None = None
    supplier_id: uuid.UUID | None = None


class TermsIn(BaseModel):
    supplier_reference: str | None = None
    unit_price: float | None = None
    currency: str | None = None
    price_basis: ValueBasis | None = None
    moq: float | None = None
    spq: float | None = None
    lead_time_min_days: float | None = None
    lead_time_max_days: float | None = None
    lead_time_basis: ValueBasis | None = None
    payment_terms: str | None = None
    country_of_origin: str | None = None
    certifications: list[str] | None = None
    is_preferred: bool | None = None
    last_confirmed_at: datetime | None = None


class StockIn(BaseModel):
    product_id: uuid.UUID
    kind: StockKind
    quantity: float
    basis: ValueBasis
    supplier_id: uuid.UUID | None = None
    location: str = ""
    as_of: datetime | None = None


def _product(db: Session, company: Company, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None or product.company_id != company.id:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return product


def _terms_out(db: Session, row) -> dict:
    supplier = db.get(Supplier, row.supplier_id)
    return {
        "id": row.id, "supplier_id": row.supplier_id, "supplier_name": supplier.name if supplier else None,
        "supplier_country": supplier.country if supplier else None, "supplier_reference": row.supplier_reference,
        "unit_price": row.unit_price, "currency": row.currency, "price_basis": row.price_basis.value,
        "moq": row.moq, "spq": row.spq, "lead_time_min_days": row.lead_time_min_days, "lead_time_max_days": row.lead_time_max_days,
        "lead_time_basis": row.lead_time_basis.value, "payment_terms": row.payment_terms, "country_of_origin": row.country_of_origin,
        "certifications": row.certifications or [], "is_preferred": row.is_preferred, "last_confirmed_at": row.last_confirmed_at, "source": row.source,
    }  # fmt: skip


def _product_out(db: Session, p: Product) -> dict:
    return {
        "id": p.id, "name": p.name, "sku": p.sku, "brand": p.brand, "manufacturer": p.manufacturer, "category": p.category,
        "description": p.description, "unit": p.unit, "sale_price": p.sale_price, "sale_price_basis": p.sale_price_basis.value,
        "unit_cost": p.unit_cost, "unit_cost_basis": "estimated" if p.unit_cost is not None else "unknown",
        "preferred_supplier_id": p.supplier_id,
        "suppliers": [_terms_out(db, t) for t in service.list_product_suppliers(db, p.id)],
        "stock": service.stock_summary(db, p.id),
    }  # fmt: skip


@router.get("/catalog/products")
def catalog_products(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    """Product list with the V2 catalog fields (suppliers, stock). V1's
    `GET /products` stays as-is for its own consumers."""

    products = db.query(Product).filter_by(company_id=company.id).order_by(Product.name).all()
    return [_product_out(db, p) for p in products]


@router.get("/catalog/products/{product_id}")
def catalog_product(product_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return _product_out(db, _product(db, company, product_id))


@router.post("/catalog/products")
def create_product(payload: ProductIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_CATALOG))) -> dict:
    from app.transactions.service import DocumentError

    try:
        product = service.create_product(db, company.id, payload.model_dump())
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _product_out(db, product)


@router.patch("/catalog/products/{product_id}")
def update_product(product_id: uuid.UUID, payload: ProductUpdateIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_CATALOG))) -> dict:
    product = _product(db, company, product_id)
    try:
        service.update_product(db, product, payload.model_dump(exclude_unset=True))
    except service.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _product_out(db, product)


@router.put("/catalog/products/{product_id}/suppliers/{supplier_id}")
def set_supplier_terms(
    product_id: uuid.UUID, supplier_id: uuid.UUID, payload: TermsIn, db: Session = Depends(get_db),
    company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_CATALOG)),
) -> dict:  # fmt: skip
    product = _product(db, company, product_id)
    try:
        service.upsert_product_supplier(db, product, supplier_id, payload.model_dump(exclude_unset=True))
    except service.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _product_out(db, product)


@router.get("/catalog/products/{product_id}/benchmark")
def product_benchmark(
    product_id: uuid.UUID, quantity: float = Query(default=1.0, gt=0), purchase_request_id: uuid.UUID | None = None,
    db: Session = Depends(get_db), company: Company = Depends(current_company),
) -> dict:  # fmt: skip
    _product(db, company, product_id)
    return benchmark_suppliers(db, product_id, quantity, purchase_request_id).to_dict()


@router.get("/catalog/stock")
def stock_overview(kind: StockKind | None = None, db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    query = db.query(StockPosition).filter_by(company_id=company.id)
    if kind is not None:
        query = query.filter_by(kind=kind)
    rows = []
    for p in query.order_by(StockPosition.as_of.desc()).all():
        product = db.get(Product, p.product_id)
        supplier = db.get(Supplier, p.supplier_id) if p.supplier_id else None
        rows.append(
            {
                "id": p.id, "product_id": p.product_id, "product_name": product.name if product else None, "product_sku": product.sku if product else None,
                "kind": p.kind.value, "quantity": p.quantity, "basis": p.quantity_basis.value, "as_of": p.as_of,
                "location": p.location or None, "supplier_id": p.supplier_id, "supplier_name": supplier.name if supplier else None, "source": p.source,
            }
        )  # fmt: skip
    return rows


@router.post("/catalog/stock")
def set_stock(
    payload: StockIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_CATALOG)),
) -> dict:  # fmt: skip
    product = _product(db, company, payload.product_id)
    try:
        service.upsert_stock_position(
            db, event_bus, product=product, kind=payload.kind, quantity=payload.quantity, basis=payload.basis,
            supplier_id=payload.supplier_id, location=payload.location, as_of=payload.as_of,
        )  # fmt: skip
    except service.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.stock_summary(db, product.id)


@router.post("/catalog/stock/import")
def import_stock(
    content: str = Body(..., media_type="text/csv"),
    filename: str = Query(default="import.csv"),
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company),
    _: CurrentUser = Depends(require(WRITE_CATALOG)),
) -> dict:
    result = service.import_stock_csv(db, event_bus, company.id, content, filename=filename)
    return {"source": result.source, "rows": result.rows, "created_or_updated": result.created_or_updated, "errors": result.errors}
