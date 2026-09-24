"""Functional mailboxes, follow-up performance and campaign performance
(app.communications.mailboxes): read-only classification of existing
messages, honest statuses, stages never confused, nothing attributed without
a real link, and no data written."""

import uuid
from datetime import timedelta

import pytest

from app.communications import mailboxes as mb
from app.core.entities import Communication, CommunicationDirection, ObjectLink, RelatedEntityType, Task, TaskStatus
from app.core.entities.commercial_document import CommercialDocument, DocumentKind
from app.core.entities.people import Candidate
from tests.v2_support import NOW, api_client, build_world

IN, OUT = CommunicationDirection.INBOUND, CommunicationDirection.OUTBOUND


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


def _msg(world, **kw) -> Communication:
    base = dict(company_id=world.company.id, channel="email", direction=IN, status="received", subject="", body="", occurred_at=NOW - timedelta(days=2))
    return Communication(**(base | kw))


def _add(db_session, *msgs):
    db_session.add_all(msgs)
    db_session.commit()
    return msgs


def test_classification_rules_are_explicit_and_deterministic(world):
    cases = [
        (_msg(world, related_entity_type=RelatedEntityType.SUPPLIER, related_entity_id=world.supplier_a.id, subject="Nouveau tarif"), "rfq"),
        (_msg(world, related_entity_type=RelatedEntityType.CUSTOMER, related_entity_id=world.customer.id, subject="Retard de livraison de la commande"), "orders"),
        (_msg(world, related_entity_type=RelatedEntityType.CUSTOMER, related_entity_id=world.customer.id, subject="Bonjour"), "sales"),
        (_msg(world, channel="website", channel_detail="quote_form", subject="Quote request"), "sales"),
        (_msg(world, subject="Candidature — poste de comptable"), "careers"),
        (_msg(world, channel="website", channel_detail="contact_form", subject="URGENT -- line down"), "support"),
        (_msg(world, channel="website", channel_detail="contact_form", subject="Pour en savoir plus"), "contact"),  # "sav" only as a word
        (_msg(world, channel="email", channel_detail="agency_proposal", subject="Nouvelle campagne à -50 % du tarif"), "contact"),
    ]
    for message, expected in cases:
        key, reason = mb.classify(message, set())
        assert key == expected, message.subject
        assert reason
    assert mb.classify(_msg(world, channel="internal"), set()) is None
    assert mb.classify(_msg(world, channel="calendar"), set()) is None


def test_linked_candidate_goes_to_careers(db_session, world):
    (m,) = _add(db_session, _msg(world, subject="Bonjour"))
    db_session.add(Candidate(company_id=world.company.id, communication_id=m.id, full_name="Léa Martin"))
    db_session.commit()
    assert [r["id"] for r in mb.list_mailbox(db_session, world.company.id, "careers")] == [m.id]


def test_mailbox_statuses_never_claim_a_connection_with_demo_providers(db_session, world):
    _add(db_session, _msg(world, channel="website", channel_detail="contact_form", source="mock_website", to_address="contact@exemple.fr", subject="Info"))
    boxes = {b["key"]: b for b in mb.mailbox_overview(db_session, world.company.id)["mailboxes"]}
    assert {b["address"] for b in boxes.values()} == {"contact@", "sales@", "orders@", "rfq@", "careers@", "support@"}
    assert boxes["contact"]["status"] == "demo"
    assert all(b["status"] != "connected" for b in boxes.values())
    empty = [b for b in boxes.values() if b["message_count"] == 0]
    assert empty and all(b["status"] == "not_configured" for b in empty)


def test_needs_reply_clears_once_a_real_answer_is_sent_on_the_thread(db_session, world):
    (inbound,) = _add(db_session, _msg(world, channel="website", channel_detail="contact_form", subject="Question", thread_key="t-1"))
    row = next(r for r in mb.list_mailbox(db_session, world.company.id, "contact") if r["id"] == inbound.id)
    assert row["needs_reply"] is True
    # A draft is not an answer.
    _add(db_session, _msg(world, direction=OUT, status="draft", purpose="reply", thread_key="t-1", occurred_at=NOW - timedelta(days=1)))
    row = next(r for r in mb.list_mailbox(db_session, world.company.id, "contact") if r["id"] == inbound.id)
    assert row["needs_reply"] is True
    _add(db_session, _msg(world, direction=OUT, status="sent", purpose="reply", thread_key="t-1", occurred_at=NOW - timedelta(days=1)))
    row = next(r for r in mb.list_mailbox(db_session, world.company.id, "contact") if r["id"] == inbound.id)
    assert row["needs_reply"] is False
    # Drafts never appear in a mailbox.
    assert all(r["status"] not in {"draft", "pending_validation"} for r in mb.list_mailbox(db_session, world.company.id, "contact"))


def test_follow_up_performance_keeps_stages_apart_and_needs_a_sample(db_session, world):
    c = world.customer_contact.id
    _add(
        db_session,
        _msg(world, direction=OUT, status="draft", purpose="follow_up", contact_id=c),
        _msg(world, direction=OUT, status="pending_validation", purpose="follow_up", contact_id=c),
        _msg(world, direction=OUT, status="sent", purpose="follow_up", contact_id=c, thread_key="a", occurred_at=NOW - timedelta(days=5)),
    )
    perf = mb.follow_up_performance(db_session, world.company.id)
    assert (perf["prepared"], perf["draft"], perf["pending_validation"], perf["sent"]) == (3, 1, 1, 1)
    assert perf["sufficient"] is False and perf["reply_rate"] is None and perf["avg_reply_delay_hours"] is None

    other = uuid.uuid4().hex
    _add(
        db_session,
        _msg(world, direction=OUT, status="sent", purpose="follow_up", thread_key=f"b{other}", occurred_at=NOW - timedelta(days=4)),
        _msg(world, direction=OUT, status="sent", purpose="quote_send", thread_key=f"c{other}", occurred_at=NOW - timedelta(days=4)),
        _msg(world, direction=IN, thread_key="a", occurred_at=NOW - timedelta(days=4), subject="Re"),  # reply 24 h later
    )
    perf = mb.follow_up_performance(db_session, world.company.id)
    assert perf["sent"] == 3 and perf["replies_received"] == 1
    assert perf["reply_rate"] == pytest.approx(1 / 3)
    assert perf["avg_reply_delay_hours"] == pytest.approx(24, abs=0.1)
    assert perf["awaiting_their_reply"] == 2
    assert perf["validated"] == 0  # no HITL approval executed yet


def test_orders_are_counted_only_through_a_real_document_chain(db_session, world):
    quote = CommercialDocument(company_id=world.company.id, kind=DocumentKind.CUSTOMER_QUOTE, number="DEV-2026-9001", status="sent", customer_id=world.customer.id)
    order = CommercialDocument(company_id=world.company.id, kind=DocumentKind.CUSTOMER_ORDER, number="CMD-2026-9001", status="confirmed", customer_id=world.customer.id)
    (sent,) = _add(db_session, _msg(world, direction=OUT, status="sent", purpose="follow_up"))
    db_session.add_all([quote, order])
    db_session.flush()
    db_session.add(ObjectLink(company_id=world.company.id, source_type="communication", source_id=sent.id, target_type="commercial_document", target_id=quote.id, relation="concerns"))
    db_session.commit()
    assert mb.follow_up_performance(db_session, world.company.id)["orders_linked"] == []
    db_session.add(ObjectLink(company_id=world.company.id, source_type="commercial_document", source_id=order.id, target_type="commercial_document", target_id=quote.id, relation="derived_from"))
    db_session.commit()
    linked = mb.follow_up_performance(db_session, world.company.id)["orders_linked"]
    assert [o["number"] for o in linked] == ["CMD-2026-9001"]


def test_validated_counts_executed_send_approvals_only(db_session, world):
    db_session.add_all(
        [
            Task(company_id=world.company.id, title="Envoyer", status=TaskStatus.EXECUTED, pending_action="send_email"),
            Task(company_id=world.company.id, title="Envoyer", status=TaskStatus.PENDING_VALIDATION, pending_action="send_email"),
        ]
    )
    db_session.commit()
    assert mb.follow_up_performance(db_session, world.company.id)["validated"] == 1


def test_campaign_figures_separate_declared_observed_and_unattributed(db_session, world):
    sept = NOW.replace(month=9, day=15) if NOW.month != 9 else NOW - timedelta(days=1)
    _add(
        db_session,
        _msg(world, channel="internal", direction=OUT, status="sent", channel_detail="campaign_report", subject="Campagne Septembre — résultats", body="La campagne Septembre génère 34% de demandes en plus.", occurred_at=sept),
        _msg(world, channel="internal", channel_detail="employee_idea", subject="Idée sur la campagne", body="Réutiliser les vidéos de la campagne Septembre.", occurred_at=sept),
        _msg(world, channel="website", channel_detail="contact_form", subject="Info", occurred_at=sept),
    )
    before = db_session.query(Communication).count()
    result = mb.campaign_performance(db_session, world.company.id)
    assert db_session.query(Communication).count() == before  # read-only
    (camp,) = result["campaigns"]
    assert camp["name"] == "Septembre"
    assert camp["declared"][0]["value_pct"] == 34 and camp["declared"][0]["basis"] == "declared"
    assert camp["observed"]["basis"] == "observed" and camp["observed"]["inbound_requests"] >= 1
    assert len(camp["feedback"]) == 1
    assert all(v is None for v in camp["metrics"].values())  # no budget, no attribution
    assert camp["limits"]


def test_api_routes_are_read_only_and_not_parsed_as_ids(session_factory, db_session, world):
    with api_client(session_factory) as client:
        assert client.get("/communications/mailboxes").status_code == 200
        assert client.get("/communications/mailboxes/sales").status_code == 200
        assert client.get("/communications/mailboxes/nope").status_code == 404
        assert client.get("/communications/performance").json()["min_sample"] == mb.MIN_SAMPLE
        assert "campaigns" in client.get("/communications/campaigns").json()
