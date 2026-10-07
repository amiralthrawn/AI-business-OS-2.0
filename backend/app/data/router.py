import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.data import service
from app.data.schemas import (
    ContactListItem,
    CustomerDetail,
    CustomerListItem,
    ProductDetail,
    ProductListItem,
    SupplierDetail,
    SupplierListItem,
    TransactionRead,
)
from app.core.entities import Company
from app.database import get_db

router = APIRouter(tags=["data"])


def _company(db: Session) -> Company:
    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail=tx("Aucune entreprise n'est encore configurée", "No company is configured yet"))
    return company


@router.get("/suppliers", response_model=list[SupplierListItem])
def list_suppliers(db: Session = Depends(get_db)) -> list[dict]:
    return service.list_suppliers(db, _company(db).id)


@router.get("/suppliers/{supplier_id}", response_model=SupplierDetail)
def get_supplier(supplier_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    detail = service.get_supplier_detail(db, _company(db).id, supplier_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=tx(f"Fournisseur {supplier_id} introuvable", f"Supplier {supplier_id} not found"))
    return detail


@router.get("/customers", response_model=list[CustomerListItem])
def list_customers(db: Session = Depends(get_db)) -> list[dict]:
    return service.list_customers(db, _company(db).id)


@router.get("/customers/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    detail = service.get_customer_detail(db, _company(db).id, customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=tx(f"Client {customer_id} introuvable", f"Customer {customer_id} not found"))
    return detail


@router.get("/products", response_model=list[ProductListItem])
def list_products(db: Session = Depends(get_db)) -> list[dict]:
    return service.list_products(db, _company(db).id)


@router.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    detail = service.get_product_detail(db, _company(db).id, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=tx(f"Produit {product_id} introuvable", f"Product {product_id} not found"))
    return detail


@router.get("/contacts", response_model=list[ContactListItem])
def list_contacts(db: Session = Depends(get_db)) -> list[dict]:
    return service.list_contacts(db, _company(db).id)


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(db: Session = Depends(get_db)) -> list[dict]:
    return service.list_transactions(db, _company(db).id)


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    detail = service.get_transaction_detail(db, _company(db).id, transaction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=tx(f"Transaction {transaction_id} introuvable", f"Transaction {transaction_id} not found"))
    return detail
