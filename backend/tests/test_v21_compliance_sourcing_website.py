"""V2.1 compliance (tasks + experts + fee estimate), sourcing (provenance,
never invented prices) and website intelligence (simulated/real modes,
HITL, the real site never modified)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.entities import (
    AIRun,
    Communication,
    Contact,
    DocumentKind,
    ProductSupplier,
    RelatedEntityType,
    SourcingLead,
    Supplier,
    TaskStatus,
    ValueBasis,
    WebsiteChangeProposal,
)
from app.domains.procurement.benchmark import benchmark_suppliers
from app.event_bus import build_event_bus
from app.sourcing import service as sourcing
from app.transactions import service as docs
from app.transactions.service import DocumentInput, LineInput
from app.website import service as website
from app.website.service import FetchResult
from tests.v2_support import api_client, build_world

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


# --- Compliance ------------------------------------------------------------------


def test_compliance_request_gets_expert_recommendation_and_a_draft_never_sent(session_factory, db_session, world):
    law = Supplier(company_id=world.company.id, name="Cabinet Duval", supplier_kind="law_firm", fee_rate_min=200, fee_rate_max=300, certifications=[])
    db_session.add(law)
    db_session.flush()
    db_session.add(Contact(company_id=world.company.id, name="Me Duval", email="duval@example.org", related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=law.id))
    db_session.commit()
    with api_client(session_factory) as client:
        created = client.post("/compliance/requests", json={"title": "Contrat cadre à revoir", "category": "contract_review", "due_at": (NOW + timedelta(days=3)).isoformat()}).json()
        reco = client.get(f"/compliance/requests/{created['id']}/recommendation").json()
        assert reco["needs_expert"] and reco["expert_kind"] == "law_firm"
        option = reco["options"][0]
        assert (option["fee_min"], option["fee_max"]) == (400, 1500) and option["basis"] == "estimated"  # 2-5 h x 200-300 €/h

        draft_id = client.post(f"/compliance/requests/{created['id']}/ask-expert/{law.id}").json()["draft_id"]
        draft = client.get(f"/communications/{draft_id}").json()
        assert draft["status"] == "draft" and draft["to_address"] == "duval@example.org"  # prepared, not sent
        assert client.get("/communications", params={"box": "sent"}).json() == []
        task_ctx = client.get(f"/objects/task/{created['id']}/context").json()
        assert any(i["id"] == draft_id for g in task_ctx["related"] for i in g["items"])  # linked to the request

        listed = client.get("/compliance/requests").json()
        assert listed[0]["category_label"] == "Contrat à vérifier" and listed[0]["open"]
        renewal = client.post("/compliance/requests", json={"title": "RC Pro", "category": "renewal"}).json()
        assert client.get(f"/compliance/requests/{renewal['id']}/recommendation").json()["needs_expert"] is False


# --- Sourcing -------------------------------------------------------------------------


class FakeWeb:
    name = "fake"

    def __init__(self, results=None, fail=False):
        self.results, self.fail = results or [], fail

    def search(self, query, count=8):
        if self.fail:
            raise ConnectionError("offline")
        return self.results


def _pr(db_session, bus, world):
    return docs.create_document(db_session, bus, world.company.id, DocumentInput(kind=DocumentKind.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=10)]))


def test_sourcing_without_web_uses_internal_suppliers_and_says_so(db_session, world, bus):
    pr = _pr(db_session, bus, world)
    run = sourcing.run_sourcing(db_session, bus, pr, web=None)
    assert run.mode == "partial" and any(s["status"] == "skipped" and "configuré" in s["detail"] for s in run.steps)
    leads = db_session.query(SourcingLead).filter_by(purchase_request_id=pr.id).all()
    assert [lead.name for lead in leads] == ["Costa Resorts"]  # known supplier not yet linked to the product
    assert leads[0].price_basis == ValueBasis.UNKNOWN and leads[0].found_price is None  # never invented


def test_web_leads_keep_their_source_and_only_stated_prices(db_session, world, bus):
    pr = _pr(db_session, bus, world)
    web = FakeWeb([
        {"title": "Hôtel Solaria — séminaires", "url": "https://solaria.example/seminaires", "description": "Forfait séminaire 3 nuits dès 480 € par participant."},
        {"title": "Groupes & Co", "url": "https://groupes.example/", "description": "Organisation de voyages de groupe."},
    ])  # fmt: skip
    run = sourcing.run_sourcing(db_session, bus, pr, web=web)
    assert run.mode == "real"
    by_name = {lead.name: lead for lead in db_session.query(SourcingLead).filter_by(source_kind="web_search").all()}
    priced = by_name["Hôtel Solaria — séminaires"]
    assert priced.found_price == 480 and priced.price_basis == ValueBasis.DECLARED and priced.source_url == "https://solaria.example/seminaires"
    assert by_name["Groupes & Co"].found_price is None and by_name["Groupes & Co"].price_basis == ValueBasis.UNKNOWN

    # A stated price >= 10 % under the best known price surfaces as a V1 Opportunity.
    from app.core.entities import Opportunity

    assert db_session.query(Opportunity).filter(Opportunity.title.contains("Hôtel Solaria")).count() == 1

    # Converting a lead is a human act: Supplier + supplier quote request -> joins the existing benchmark.
    quote = sourcing.convert_lead(db_session, bus, priced)
    assert quote.kind == DocumentKind.SUPPLIER_QUOTE and priced.status == "converted"
    names = {c.supplier_name for c in benchmark_suppliers(db_session, world.product.id, 10, purchase_request_id=pr.id).candidates}
    assert "Hôtel Solaria — séminaires" in names
    terms = db_session.query(ProductSupplier).filter_by(supplier_id=priced.supplier_id).one()
    assert terms.unit_price == 480 and terms.price_basis == ValueBasis.DECLARED


def test_web_failure_is_reported_not_hidden(db_session, world, bus):
    run = sourcing.run_sourcing(db_session, bus, _pr(db_session, bus, world), web=FakeWeb(fail=True))
    assert run.mode == "partial" and any(s["status"] == "failed" for s in run.steps)


# --- Website intelligence ---------------------------------------------------------------


def test_without_a_site_the_audit_runs_on_the_demo_site_labelled_simulated(db_session, world, bus):
    run = website.audit_website(db_session, bus, world.company)
    assert run.mode == "simulated" and run.status == "done"
    assert any(s["status"] == "skipped" and "simulation" in s["detail"] for s in run.steps)
    codes = {i["code"] for i in run.result["issues"]}
    assert {"title_short", "meta_missing", "h1_multiple", "img_alt", "lang_missing", "slow", "title_duplicate"} <= codes
    assert all({"what", "why", "change"} <= i.keys() for i in run.result["issues"])
    proposals = db_session.query(WebsiteChangeProposal).filter_by(run_id=run.id).all()
    title = next(p for p in proposals if p.field == "title" and p.page_url.endswith("/"))
    assert title.current_value == "Accueil" and world.company.name in title.proposed_value and 30 <= len(title.proposed_value) <= 60


class FakeSite:
    def __init__(self, pages, robots=None):
        self.pages, self.robots, self.calls = pages, robots, []

    def fetch(self, url):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200 if self.robots else 404, self.robots or "", 0.01, 0)
        html = self.pages.get(url)
        return FetchResult(url, 200 if html else 404, html or "", 0.1, len(html or ""))


def test_real_site_is_crawled_within_limits_and_robots_is_respected(db_session, world, bus):
    world.company.website_url = "https://example.test/"
    site = FakeSite({"https://example.test/": '<html lang="fr"><head><title>Voyages de groupe sur mesure | Horizon</title></head><body><h1>Voyages</h1><a href="/a">a</a><a href="https://other.test/x">ext</a></body></html>', "https://example.test/a": "<html><body><p>court</p></body></html>"})
    run = website.audit_website(db_session, bus, world.company, fetcher=site)
    assert run.mode == "real" and len(run.result["pages"]) == 2
    assert not any("other.test" in c for c in site.calls)  # same domain only

    blocked = FakeSite(site.pages, robots="User-agent: *\nDisallow: /")
    assert website.audit_website(db_session, bus, world.company, fetcher=blocked).status == "failed"


def test_website_change_goes_through_hitl_and_never_touches_the_site(session_factory, db_session, world):
    with api_client(session_factory) as client:
        audit = client.post("/website/audit").json()
        assert audit["mode"] == "simulated"
        proposal = audit["proposals"][0]
        submitted = client.post(f"/website/proposals/{proposal['id']}/submit").json()
        assert submitted["status"] == "pending_validation"
        client.post(f"/actions/tasks/{submitted['task_id']}/approve")
        latest = client.get("/website").json()
    approved = next(p for p in latest["proposals"] if p["id"] == proposal["id"])
    assert approved["status"] == "approved"  # ready to apply -- no CMS connector, nothing written
    assert db_session.query(AIRun).filter_by(kind="website_audit").count() == 1


def test_no_new_feature_executes_on_its_own(db_session, world, bus):
    """Nothing in V2.1 sends, pays, promotes or publishes by itself: every
    external or sensitive effect is a PENDING_VALIDATION Task first."""

    from app.core.entities import Task

    website.audit_website(db_session, bus, world.company)
    sourcing.run_sourcing(db_session, bus, _pr(db_session, bus, world), web=None)
    assert db_session.query(Task).filter(Task.status == TaskStatus.EXECUTED).count() == 0
    assert db_session.query(Communication).filter_by(status="sent").count() == 0
