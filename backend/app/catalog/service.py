"""Catalog (V2): products, supplier terms and stock.

Product is the central object (brain/business_object_model.md); this
module owns writing it and its two satellites -- which suppliers can
provide it on which terms (ProductSupplier) and how much exists where
(StockPosition). Reads go through the object graph/contextual API.

Stock import: one generic CSV path (`import_stock_csv`) that upserts on
the natural key (product, kind, supplier, location) and records its source,
so the same file can be re-imported and a future API source can reuse
`upsert_stock_position` unchanged. No integration framework beyond that.
"""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.core.entities import Product, ProductSupplier, StockKind, StockPosition, Supplier, ValueBasis
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent

STOCK_UPDATED = "StockUpdated"

PRODUCT_FIELDS = {"name", "sku", "brand", "manufacturer", "category", "description", "unit", "sale_price", "sale_price_basis", "unit_cost", "supplier_id"}
TERMS_FIELDS = {
    "supplier_reference", "unit_price", "currency", "price_basis", "moq", "spq", "lead_time_min_days", "lead_time_max_days",
    "lead_time_basis", "payment_terms", "country_of_origin", "certifications", "is_preferred", "last_confirmed_at",
}  # fmt: skip


class CatalogError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_product(session: Session, company_id: uuid.UUID, data: dict) -> Product:
    from app.transactions.service import NewProduct, resolve_or_create_product

    product = resolve_or_create_product(
        session, company_id, NewProduct(name=data.get("name", ""), sku=data.get("sku"), sale_price=data.get("sale_price"), unit_cost=data.get("unit_cost"), brand=data.get("brand"), unit=data.get("unit"))
    )
    for key in ("manufacturer", "category", "description"):
        if data.get(key) is not None:
            setattr(product, key, data[key])
    session.commit()
    session.refresh(product)
    return product


def update_product(session: Session, product: Product, changes: dict) -> Product:
    for key, value in changes.items():
        if key not in PRODUCT_FIELDS:
            raise CatalogError(tx(f"Champ non modifiable : {key}", f"Field cannot be changed: {key}"))
        setattr(product, key, value)
    if changes.get("supplier_id"):
        # The preferred supplier must also be a supplier of the product.
        upsert_product_supplier(session, product, changes["supplier_id"], {"is_preferred": True}, commit=False)
    session.commit()
    session.refresh(product)
    return product


def upsert_product_supplier(session: Session, product: Product, supplier_id: uuid.UUID, terms: dict, *, commit: bool = True) -> ProductSupplier:
    supplier = session.get(Supplier, supplier_id)
    if supplier is None or supplier.company_id != product.company_id:
        raise CatalogError(tx("Fournisseur introuvable", "Supplier not found"))
    row = session.query(ProductSupplier).filter_by(product_id=product.id, supplier_id=supplier_id).first()
    if row is None:
        row = ProductSupplier(company_id=product.company_id, product_id=product.id, supplier_id=supplier_id, certifications=[])
        session.add(row)
    for key, value in terms.items():
        if key not in TERMS_FIELDS:
            raise CatalogError(tx(f"Condition inconnue : {key}", f"Unknown term: {key}"))
        setattr(row, key, value)
    if row.lead_time_min_days is not None and row.lead_time_basis in (None, ValueBasis.UNKNOWN):
        row.lead_time_basis = ValueBasis.DECLARED
    if terms.get("is_preferred"):
        for other in session.query(ProductSupplier).filter(ProductSupplier.product_id == product.id, ProductSupplier.supplier_id != supplier_id).all():
            other.is_preferred = False
        product.supplier_id = supplier_id
    if commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()
    return row


def list_product_suppliers(session: Session, product_id: uuid.UUID) -> list[ProductSupplier]:
    return (
        session.query(ProductSupplier)
        .filter_by(product_id=product_id)
        .order_by(ProductSupplier.is_preferred.desc(), ProductSupplier.created_at)
        .all()
    )


def upsert_stock_position(
    session: Session,
    event_bus: EventBus | None,
    *,
    product: Product,
    kind: StockKind,
    quantity: float,
    basis: ValueBasis,
    supplier_id: uuid.UUID | None = None,
    location: str = "",
    source: str = "manual",
    as_of: datetime | None = None,
    external_ref: str | None = None,
    commit: bool = True,
) -> StockPosition:
    if kind == StockKind.SUPPLIER and supplier_id is None:
        raise CatalogError(tx("Un stock fournisseur doit préciser le fournisseur", "A supplier stock must name the supplier"))
    if kind == StockKind.PHYSICAL and basis not in {ValueBasis.OBSERVED, ValueBasis.DECLARED, ValueBasis.ESTIMATED}:
        raise CatalogError(tx("Nature de quantité invalide pour un stock physique", "Invalid quantity type for a physical stock"))
    position = (
        session.query(StockPosition)
        .filter_by(product_id=product.id, kind=kind, supplier_id=supplier_id, location=location or "")
        .first()
    )
    if position is None:
        position = StockPosition(company_id=product.company_id, product_id=product.id, kind=kind, supplier_id=supplier_id, location=location or "", quantity=quantity, quantity_basis=basis, as_of=as_of or _now())
        session.add(position)
    position.quantity = quantity
    position.quantity_basis = basis
    position.as_of = as_of or _now()
    position.source = source
    position.external_ref = external_ref
    if commit:
        session.commit()
        session.refresh(position)
    else:
        session.flush()
    if event_bus is not None:
        event_bus.publish(
            BusinessEvent(
                event_type=STOCK_UPDATED,
                source="catalog",
                payload={"subject_type": "product", "subject_id": str(product.id), "kind": kind.value, "quantity": quantity, "basis": basis.value, "source": source},
            )
        )
    return position


def stock_summary(session: Session, product_id: uuid.UUID) -> dict:
    """The three stock kinds side by side -- never added together."""

    positions = session.query(StockPosition).filter_by(product_id=product_id).order_by(StockPosition.kind, StockPosition.as_of.desc()).all()
    out: dict = {"physical": [], "supplier": [], "potential": []}
    for p in positions:
        supplier = session.get(Supplier, p.supplier_id) if p.supplier_id else None
        out[p.kind.value].append(
            {
                "id": p.id, "quantity": p.quantity, "basis": p.quantity_basis.value, "as_of": p.as_of,
                "location": p.location or None, "source": p.source, "supplier_id": p.supplier_id,
                "supplier_name": supplier.name if supplier else None, "external_ref": p.external_ref,
            }
        )  # fmt: skip
    return out


@dataclass
class ImportResult:
    source: str
    rows: int = 0
    created_or_updated: int = 0
    errors: list[str] = field(default_factory=list)


_BASIS_BY_KIND = {StockKind.PHYSICAL: ValueBasis.OBSERVED, StockKind.SUPPLIER: ValueBasis.DECLARED, StockKind.POTENTIAL: ValueBasis.ESTIMATED}


def import_stock_csv(session: Session, event_bus: EventBus | None, company_id: uuid.UUID, content: str, *, filename: str = "import.csv") -> ImportResult:
    """Columns (header row, `;` or `,`): `sku` (or `product`), `kind`
    (physical|supplier|potential), `quantity`, optional `supplier`,
    `location`, `basis`, `as_of` (ISO date). A row that cannot be matched is
    reported, never guessed -- products are matched on reference first,
    then exact name; they are never created by a stock import."""

    result = ImportResult(source=f"csv:{filename}")
    dialect = csv.Sniffer().sniff(content.splitlines()[0] if content else ",", delimiters=";,")
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    for i, raw in enumerate(reader, start=2):
        result.rows += 1
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        ref = row.get("sku") or row.get("product")
        product = None
        if ref:
            product = session.query(Product).filter_by(company_id=company_id, sku=ref).first() or (
                session.query(Product).filter(Product.company_id == company_id, Product.name.ilike(ref)).first()
            )
        if product is None:
            result.errors.append(tx(f"Ligne {i} : produit « {ref or '?'} » introuvable", f'Line {i}: product "{ref or "?"}" not found'))
            continue
        try:
            kind = StockKind(row.get("kind", "physical").lower())
        except ValueError:
            result.errors.append(tx(f"Ligne {i} : type de stock « {row.get('kind')} » inconnu", f'Line {i}: unknown stock type "{row.get("kind")}"'))
            continue
        try:
            quantity = float(row.get("quantity", "").replace(",", "."))
        except ValueError:
            result.errors.append(tx(f"Ligne {i} : quantité invalide", f"Line {i}: invalid quantity"))
            continue
        supplier_id = None
        if row.get("supplier"):
            supplier = session.query(Supplier).filter(Supplier.company_id == company_id, Supplier.name.ilike(row["supplier"])).first()
            if supplier is None:
                result.errors.append(tx(f"Ligne {i} : fournisseur « {row['supplier']} » introuvable", f'Line {i}: supplier "{row["supplier"]}" not found'))
                continue
            supplier_id = supplier.id
        try:
            basis = ValueBasis(row["basis"].lower()) if row.get("basis") else _BASIS_BY_KIND[kind]
            as_of = datetime.fromisoformat(row["as_of"]).replace(tzinfo=timezone.utc) if row.get("as_of") else None
            upsert_stock_position(
                session, None, product=product, kind=kind, quantity=quantity, basis=basis, supplier_id=supplier_id,
                location=row.get("location", ""), source=result.source, as_of=as_of, commit=False,
            )  # fmt: skip
            result.created_or_updated += 1
        except (ValueError, CatalogError) as exc:
            result.errors.append(f"Ligne {i} : {exc}")
    session.commit()
    if event_bus is not None and result.created_or_updated:
        event_bus.publish(BusinessEvent(event_type=STOCK_UPDATED, source="catalog", payload={"import": result.source, "rows": result.created_or_updated}))
    return result


def ensure_preferred_supplier_terms(session: Session, company_id: uuid.UUID) -> int:
    """Every V1 `Product.supplier_id` has its ProductSupplier row (preferred,
    V1 unit_cost as a DECLARED price) -- what the V2 migration backfills for
    existing databases, applied to data created by V1 code paths (seed)."""

    created = 0
    for product in session.query(Product).filter(Product.company_id == company_id, Product.supplier_id.isnot(None)).all():
        exists = session.query(ProductSupplier.id).filter_by(product_id=product.id, supplier_id=product.supplier_id).first()
        if exists is None:
            session.add(
                ProductSupplier(
                    company_id=company_id, product_id=product.id, supplier_id=product.supplier_id, unit_price=product.unit_cost,
                    price_basis=ValueBasis.DECLARED, is_preferred=True, certifications=[], source="v1_primary_supplier",
                )
            )  # fmt: skip
            created += 1
    session.commit()
    return created
