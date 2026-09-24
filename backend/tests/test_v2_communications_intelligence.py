"""V2 communications (email <-> objects, AI draft -> human validation ->
send, follow-ups computed at read time) and intelligence over the new
business objects (Orchestrator traversal, a V2-fed Observable)."""

from datetime import timedelta

import pytest

from app.ai.capabilities import build_capability_registry
from app.ai.llm import DeterministicLLMClient
from app.ai.orchestrator import AIOrchestrator
from app.core.entities import (
    CommercialDocument,
    Communication,
    CommunicationDirection,
    CostKind,
    DocumentKind,
    ObjectLink,
    RelatedEntityType,
    Role,
    Task,
    TaskStatus,
    UserProfile,
    ValueBasis,
)
from app.event_bus import build_event_bus
from app.observation import build_observable_registry
from app.observation.engine import run_observation_sweep
from app.transactions import service
from app.transactions.service import DocumentInput, LineInput
from tests.v2_support import NOW, api_client, build_world

K = DocumentKind


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def _sent_quote(db_session, bus, world, days_ago=10):
    quote = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_QUOTE, customer_id=world.customer.id, contact_id=world.customer_contact.id, lines=[LineInput(product_id=world.product.id, quantity=20)]))
    service.change_status(db_session, bus, quote, "sent", occurred_at=NOW - timedelta(days=days_ago))
    return quote


def test_inbound_email_analysis_detects_intent_references_and_suggests_links(session_factory, db_session, world, bus):
    quote = _sent_quote(db_session, bus, world)
    email = Communication(
        company_id=world.company.id, channel="email", direction=CommunicationDirection.INBOUND, status="received",
        subject=f"Re: devis {quote.number}", body="Bonjour, pouvez-vous revoir le prix du Séjour séminaire 3 nuits ? Merci",
        occurred_at=NOW, contact_id=world.customer_contact.id, from_address="claire@atlas.example",
        related_entity_type=RelatedEntityType.CUSTOMER, related_entity_id=world.customer.id,
    )  # fmt: skip
    db_session.add(email)
    db_session.commit()
    with api_client(session_factory) as client:
        analysis = client.post(f"/communications/{email.id}/analyze").json()
    assert {"quote_request"} <= {i["key"] for i in analysis["intents"]}
    matched = {r["matched"] for r in analysis["references"]}
    assert quote.number in matched and "Séjour séminaire 3 nuits" in matched
    assert analysis["party"]["title"] == "Groupe Atlas"
    assert any(s["id"] == str(quote.id) for s in analysis["suggested_links"])
    assert analysis["generated_by"] == "rules"  # no LLM configured: says so


def test_ai_follow_up_draft_goes_through_human_validation_before_sending(session_factory, db_session, world, bus):
    quote = _sent_quote(db_session, bus, world)
    sales = UserProfile(company_id=world.company.id, name="Sam", role=Role.SALES)
    buyer = UserProfile(company_id=world.company.id, name="Bea", role=Role.PROCUREMENT)
    db_session.add_all([sales, buyer])
    db_session.commit()

    with api_client(session_factory) as client:
        draft = client.post("/communications/drafts", json={"purpose": "follow_up", "object_type": "commercial_document", "object_id": str(quote.id)}, headers={"X-User-Id": str(sales.id)}).json()
        assert draft["status"] == "draft" and draft["to_address"] == "claire@atlas.example"
        assert quote.number in draft["subject"] and "Séjour séminaire 3 nuits" in draft["body"]
        # The draft is linked to the quote before anything is sent.
        quote_ctx = client.get(f"/objects/commercial_document/{quote.id}/context").json()
        assert any(i["id"] == draft["id"] for g in quote_ctx["related"] if g["type"] == "communication" for i in g["items"])

        edited = client.patch(f"/communications/{draft['id']}", json={"body": draft["body"] + "\nPS : offre valable 15 jours."}).json()
        assert "PS" in edited["body"]

        submitted = client.post(f"/communications/{draft['id']}/submit", headers={"X-User-Id": str(sales.id)}).json()
        task_id = submitted["task_id"]
        assert submitted["communication"]["status"] == "pending_validation"
        assert client.get("/communications", params={"box": "sent"}).json() == []  # nothing sent yet

        # A buyer cannot validate a sales email; the salesperson can.
        assert client.post(f"/actions/tasks/{task_id}/approve", headers={"X-User-Id": str(buyer.id)}).status_code == 403
        approved = client.post(f"/actions/tasks/{task_id}/approve", headers={"X-User-Id": str(sales.id)})
        assert approved.status_code == 200 and approved.json()["status"] == "executed"

        sent = client.get(f"/communications/{draft['id']}").json()
        assert sent["status"] == "sent" and sent["source"] == "mock_email"  # honest: simulated provider
    refreshed = db_session.get(CommercialDocument, quote.id)
    db_session.refresh(refreshed)
    assert refreshed.follow_up_at is not None  # next follow-up rescheduled after sending


def test_rejected_draft_returns_to_editable_and_is_never_sent(session_factory, db_session, world, bus):
    with api_client(session_factory) as client:
        draft = client.post("/communications/drafts", json={"purpose": "generic", "object_type": "supplier", "object_id": str(world.supplier_a.id)}).json()
        assert draft["to_address"] == "marco@riviera.example"
        task_id = client.post(f"/communications/{draft['id']}/submit").json()["task_id"]
        client.post(f"/actions/tasks/{task_id}/reject")
        assert client.get(f"/communications/{draft['id']}").json()["status"] == "rejected"
        assert client.patch(f"/communications/{draft['id']}", json={"subject": "v2"}).json()["status"] == "draft"


def test_draft_without_recipient_cannot_be_submitted(session_factory, db_session, world, bus):
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=10)]))
    rfq = service.derive_document(db_session, bus, pr, K.SUPPLIER_QUOTE, supplier_id=world.supplier_c.id)  # no contact known
    with api_client(session_factory) as client:
        draft = client.post("/communications/drafts", json={"purpose": "rfq_price", "object_type": "commercial_document", "object_id": str(rfq.id)}).json()
        assert "prix" in draft["body"].lower()
        assert client.post(f"/communications/{draft['id']}/submit").status_code == 400


def test_follow_ups_are_computed_at_read_time(session_factory, db_session, world, bus):
    _sent_quote(db_session, bus, world, days_ago=10)
    pr = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.PURCHASE_REQUEST, lines=[LineInput(product_id=world.product.id, quantity=5)]))
    rfq = service.derive_document(db_session, bus, pr, K.SUPPLIER_QUOTE, supplier_id=world.supplier_b.id)
    rfq.issued_at = NOW - timedelta(days=8)
    db_session.add(Communication(company_id=world.company.id, channel="email", direction=CommunicationDirection.INBOUND, status="received", subject="Question", occurred_at=NOW - timedelta(days=5), contact_id=world.customer_contact.id))
    db_session.commit()
    with api_client(session_factory) as client:
        data = client.get("/follow-ups").json()
    assert data["computed_at_read_time"] is True
    reasons = [i["reason"] for i in data["items"]]
    assert "Devis envoyé sans réponse" in reasons and "Devis fournisseur attendu" in reasons and "Message entrant sans réponse" in reasons


def _orchestrator(db_session, bus):
    return AIOrchestrator(db_session, build_capability_registry(), DeterministicLLMClient(), bus)


def test_orchestrator_explains_why_an_order_is_less_profitable_than_planned(db_session, world, bus):
    order = service.create_document(db_session, bus, world.company.id, DocumentInput(kind=K.CUSTOMER_ORDER, customer_id=world.customer.id, lines=[LineInput(product_id=world.product.id, quantity=20)]))
    service.change_status(db_session, bus, order, "confirmed")
    pr = service.derive_document(db_session, bus, order, K.PURCHASE_REQUEST)
    po = service.derive_document(db_session, bus, pr, K.PURCHASE_ORDER, supplier_id=world.supplier_a.id)
    invoice = service.derive_document(db_session, bus, po, K.SUPPLIER_INVOICE)
    service.update_line(db_session, invoice, invoice.lines[0].id, {"unit_price": 690.0})
    service.add_cost_item(db_session, invoice, kind=CostKind.TRANSPORT, amount_min=800, amount_max=None, basis=ValueBasis.OBSERVED)
    service.change_status(db_session, bus, invoice, "approved")

    # Asked from the order's page, without typing its number.
    result = _orchestrator(db_session, bus).ask("Pourquoi cette commande est-elle moins rentable que prévu ?", object_type="commercial_document", object_id=order.id)
    assert result.agent == "deals"
    assert result.capabilities_used == ["read_object_context", "analyze_document_margin"]
    margin = result.context["analyze_document_margin"]["margin"]
    assert margin["current"]["cost_basis"] == "actual"
    assert margin["current"]["margin_max"] < margin["planned"]["margin_min"]
    assert "Principaux écarts" in result.answer and order.number in result.answer

    # Same question naming the document number works from anywhere.
    by_number = _orchestrator(db_session, bus).ask(f"Quelle est la marge de {order.number} ?")
    assert by_number.agent == "deals"


def test_orchestrator_recommends_which_supplier_to_contact(db_session, world, bus):
    result = _orchestrator(db_session, bus).ask("Quel fournisseur contacter pour le Séjour séminaire 3 nuits ?")
    assert result.agent == "deals"
    assert "benchmark_suppliers" in result.capabilities_used
    assert "fournisseur recommandé" in result.answer


def test_v1_questions_still_route_as_before(db_session, world, bus):
    result = _orchestrator(db_session, bus).ask("Quel est notre fournisseur pour le Séjour séminaire 3 nuits ?")
    assert result.agent != "deals"


def test_pending_quote_feeds_the_v1_observation_engine(db_session, world, bus):
    _sent_quote(db_session, bus, world, days_ago=20)
    result = run_observation_sweep(db_session, bus, build_observable_registry(), world.company.id)
    assert result["business_events_published"] >= 1
    from app.core.entities import EventLogEntry

    events = db_session.query(EventLogEntry).filter_by(event_type="ObservationDetected").all()
    quote_events = [e for e in events if e.payload.get("observable") == "customer_quote_pending_age_days"]
    assert len(quote_events) == 1
    assert quote_events[0].subject_type == "customer" and quote_events[0].payload["extra_context"]["document_number"].startswith("DEV-")


def test_event_log_subjects_make_per_object_history_queryable(db_session, world, bus):
    quote = _sent_quote(db_session, bus, world)
    from app.core.entities import EventLogEntry

    rows = db_session.query(EventLogEntry).filter_by(subject_type="commercial_document", subject_id=quote.id).all()
    assert {r.event_type for r in rows} >= {"DocumentCreated", "DocumentStatusChanged"}
    assert not db_session.query(ObjectLink).filter_by(relation="derived_from").count()
    assert db_session.query(Task).filter(Task.status == TaskStatus.PENDING_VALIDATION).count() == 0
