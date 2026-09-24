"""AI sourcing for a purchase request (V2.1, brain/sourcing.md).

    Purchase request -> sourcing run (visible steps) -> leads with provenance
    -> human converts a lead -> Supplier + supplier-quote request derived from
    the purchase request -> the EXISTING benchmark compares it.

Never invents a supplier or a price: a lead comes either from the
company's own data (a supplier already known but not yet consulted for this
product) or from a real web search result (URL kept); a price is recorded
only when the source's own text states one (DECLARED by that source).
Web search runs only when an API key is configured; otherwise the run says
so ("partial") -- there is no crawler and no scraping of supplier sites.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.entities import (
    AIRun,
    CommercialDocument,
    DocumentKind,
    Opportunity,
    OpportunityStatus,
    Product,
    ProductSupplier,
    RelatedEntityType,
    SourcingLead,
    Supplier,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent

SOURCING_OPPORTUNITY_FOUND = "SourcingOpportunityFound"
PRICE_RE = re.compile(r"(\d{1,6}(?:[.,]\d{1,2})?)\s?(?:€|eur\b|euros?)", re.IGNORECASE)


class SourcingError(ValueError):
    pass


class WebSearchProvider(Protocol):
    name: str

    def search(self, query: str, count: int = 8) -> list[dict]:
        """[{"title", "url", "description"}] -- real results only."""


class BraveSearchProvider:
    name = "brave_search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, count: int = 8) -> list[dict]:
        import httpx

        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")}
            for r in response.json().get("web", {}).get("results", [])
        ]


def default_web_provider() -> WebSearchProvider | None:
    key = get_settings().brave_search_api_key
    return BraveSearchProvider(key) if key else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _step(run: AIRun, label: str, status: str = "done", detail: str | None = None) -> None:
    run.steps = [*run.steps, {"label": label, "status": status, "detail": detail, "at": _now().isoformat()}]


def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def run_sourcing(session: Session, event_bus: EventBus | None, purchase_request: CommercialDocument, web: WebSearchProvider | None = None) -> AIRun:
    if purchase_request.kind != DocumentKind.PURCHASE_REQUEST:
        raise SourcingError("Le sourcing part d'une demande d'achat")
    line = next((ln for ln in purchase_request.lines if ln.product_id), None)
    if line is None:
        raise SourcingError("La demande d'achat n'a aucun produit à sourcer")
    product = session.get(Product, line.product_id)
    web = web if web is not None else default_web_provider()

    run = AIRun(
        company_id=purchase_request.company_id, kind="sourcing", subject_type="commercial_document", subject_id=purchase_request.id,
        mode="real" if web else "partial", status="running", target=product.name, started_at=_now(), steps=[], result={},
    )  # fmt: skip
    session.add(run)
    session.flush()
    _step(run, f"Besoin analysé : {product.name} × {line.quantity:g}")

    known = {ps.supplier_id for ps in session.query(ProductSupplier).filter_by(product_id=product.id).all()}
    existing_names = {lead.name.lower() for lead in session.query(SourcingLead).filter_by(purchase_request_id=purchase_request.id).all()}
    created = 0

    # 1. Internal: suppliers the company already works with, not yet linked to this product.
    query = session.query(Supplier).filter(Supplier.company_id == purchase_request.company_id, Supplier.supplier_kind == "goods")
    if known:
        query = query.filter(Supplier.id.notin_(known))
    candidates = query.all()
    for supplier in candidates:
        if supplier.name.lower() in existing_names:
            continue
        session.add(
            SourcingLead(
                company_id=purchase_request.company_id, purchase_request_id=purchase_request.id, product_id=product.id,
                name=supplier.name, country=supplier.country, source_kind="existing_supplier", supplier_id=supplier.id,
                snippet="Fournisseur déjà référencé par l'entreprise, jamais consulté pour ce produit.",
                price_basis=ValueBasis.UNKNOWN, facts={"certifications": supplier.certifications or []}, retrieved_at=_now(),
            )
        )  # fmt: skip
        created += 1
    _step(run, "Fournisseurs internes non consultés recherchés", detail=f"{len(candidates)} trouvé(s)")

    # 2. Web: only real search results, with their URL.
    if web is None:
        _step(run, "Recherche web", "skipped", "Aucun moteur de recherche configuré (BRAVE_SEARCH_API_KEY) — résultats internes uniquement.")
    else:
        query = f"{product.name} {product.sku or ''} fournisseur grossiste".strip()
        try:
            results = web.search(query)
            _step(run, f"Recherche web : « {query} »", detail=f"{len(results)} résultat(s)")
        except Exception as exc:  # network / quota: reported, never hidden
            results = []
            run.mode = "partial"
            _step(run, "Recherche web", "failed", f"Échec : {type(exc).__name__}")
        for r in results:
            if not r.get("url"):
                continue
            name = r.get("title") or _domain(r["url"])
            if name.lower() in existing_names:
                continue
            price = PRICE_RE.search(f"{r.get('title', '')} {r.get('description', '')}")
            session.add(
                SourcingLead(
                    company_id=purchase_request.company_id, purchase_request_id=purchase_request.id, product_id=product.id,
                    name=name[:255], website=f"https://{_domain(r['url'])}", source_kind="web_search", source_url=r["url"],
                    snippet=(r.get("description") or "")[:500],
                    found_price=float(price.group(1).replace(",", ".")) if price else None,
                    price_basis=ValueBasis.DECLARED if price else ValueBasis.UNKNOWN,
                    facts={}, retrieved_at=_now(),
                )
            )  # fmt: skip
            existing_names.add(name.lower())
            created += 1
        _step(run, "Résultats structurés", detail="Prix retenu seulement s'il figure dans le texte de la source ; sinon « inconnu ».")

    run.status = "done"
    run.finished_at = _now()
    run.result = {"leads_created": created}
    session.commit()
    _flag_price_opportunity(session, event_bus, purchase_request, product)
    return run


def _flag_price_opportunity(session: Session, event_bus: EventBus | None, pr: CommercialDocument, product: Product) -> None:
    """Supplier sourcing opportunity -> Opportunity (V1 Intelligence): a
    lead whose SOURCE states a price >= 10 % below the best known price."""

    prices = [ps.unit_price for ps in session.query(ProductSupplier).filter_by(product_id=product.id).all() if ps.unit_price]
    if not prices:
        return
    best = min(prices)
    for lead in session.query(SourcingLead).filter_by(purchase_request_id=pr.id).filter(SourcingLead.found_price.isnot(None)).all():
        if lead.found_price <= best * 0.9:
            title = f"Source moins chère possible pour {product.name} : {lead.name}"
            if session.query(Opportunity.id).filter_by(company_id=pr.company_id, title=title).first() is None:
                session.add(Opportunity(company_id=pr.company_id, title=title, description=f"Prix annoncé par la source : {lead.found_price:.2f} € (non vérifié) vs meilleur prix connu {best:.2f} €. Source : {lead.source_url}", status=OpportunityStatus.OPEN, related_entity_type=RelatedEntityType.PRODUCT, related_entity_id=product.id))
                session.commit()
                if event_bus is not None:
                    event_bus.publish(BusinessEvent(event_type=SOURCING_OPPORTUNITY_FOUND, source="sourcing", payload={"product_id": str(product.id), "lead": lead.name, "title": title}))


def convert_lead(session: Session, event_bus: EventBus, lead: SourcingLead, *, owner_user_id: uuid.UUID | None = None) -> CommercialDocument:
    """Human decision: the lead becomes a Supplier (reused if it exists)
    and a supplier-quote request derived from the purchase request -- so it
    joins the existing benchmark and the RFQ email flow."""

    from app.transactions.service import derive_document

    if lead.status == "converted":
        raise SourcingError("Piste déjà convertie")
    supplier = session.get(Supplier, lead.supplier_id) if lead.supplier_id else None
    if supplier is None:
        supplier = session.query(Supplier).filter(Supplier.company_id == lead.company_id, Supplier.name.ilike(lead.name)).first()
    if supplier is None:
        supplier = Supplier(company_id=lead.company_id, name=lead.name, country=lead.country, certifications=lead.facts.get("certifications", []))
        session.add(supplier)
        session.flush()
    lead.supplier_id = supplier.id
    lead.status = "converted"
    session.commit()
    pr = session.get(CommercialDocument, lead.purchase_request_id)
    quote = derive_document(session, event_bus, pr, DocumentKind.SUPPLIER_QUOTE, supplier_id=supplier.id, owner_user_id=owner_user_id)
    if lead.found_price is not None:
        # The price the source stated -- DECLARED by that source, pending the real quote.
        ps = session.query(ProductSupplier).filter_by(product_id=lead.product_id, supplier_id=supplier.id).first()
        if ps is not None and ps.unit_price is None:
            ps.unit_price, ps.price_basis, ps.source = lead.found_price, ValueBasis.DECLARED, f"web:{lead.source_url}"[:30]
            session.commit()
    return quote
