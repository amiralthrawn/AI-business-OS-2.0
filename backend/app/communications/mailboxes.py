"""Functional mailboxes, follow-up performance and campaign performance --
READ-ONLY views over the Communications already in the database
(brain/communications.md "Boîtes fonctionnelles").

Nothing here connects an account, creates a message or changes data:

- A functional mailbox (contact@, sales@, orders@, rfq@, careers@, support@)
  is a *classification* of existing messages by explicit, deterministic rules
  (linked candidate, linked party, intent keywords, website form). Every row
  carries the rule that placed it there. The address itself is only shown as
  configured when a message was really addressed to it; today no connector
  provides real addresses, so each box is "demo" (messages from the demo
  providers) or "not_configured" (no message) -- never "connected".
- Follow-up metrics keep draft / pending validation / sent / reply received /
  order apart, and say "insufficient data" below a minimum sample.
- Campaign figures separate what is declared (text of a report), observed
  (counted messages) and not established (attribution without a real link).
"""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.i18n import text_of, tx
from app.communications.service import _INTENTS, _row
from app.connectors.registry import connector_registry
from app.core.analytics import _as_aware_utc
from app.core.entities import CommercialDocument, Communication, Task
from app.core.entities.task import TaskStatus
from app.core.entities.base import RelatedEntityType
from app.core.entities.commercial_document import DocumentKind
from app.core.entities.communication import CommunicationDirection
from app.core.entities.object_link import ObjectLink
from app.core.entities.people import Candidate

# Below this many sent messages a rate or an average means nothing.
MIN_SAMPLE = 3

# Labels and rules in both interface languages (French, English) -- see _localized().
MAILBOXES: list[dict] = [
    {"key": "sales", "address": "sales@", "group": ("Commercial", "Sales"), "label": ("Ventes", "Sales"),
     "rule": ("Client lié au message, ou demande de devis/prix d'un expéditeur qui n'est pas fournisseur.", "Customer linked to the message, or a quote/price request from a sender who is not a supplier.")},
    {"key": "orders", "address": "orders@", "group": ("Commandes", "Orders"), "label": ("Commandes", "Orders"),
     "rule": ("Message d'un client parlant de commande, livraison ou facture.", "Message from a customer about an order, a delivery or an invoice.")},
    {"key": "rfq", "address": "rfq@", "group": ("Achats", "Procurement"), "label": ("Achats & devis fournisseurs", "Procurement & supplier quotes"),
     "rule": ("Fournisseur lié au message (devis, prix, délais, factures fournisseur).", "Supplier linked to the message (quotes, prices, lead times, supplier invoices).")},
    {"key": "careers", "address": "careers@", "group": ("Recrutement", "Recruitment"), "label": ("Candidatures", "Applications"),
     "rule": ("Candidat créé à partir du message, ou intention « candidature ».", 'Candidate created from the message, or an "application" intent.')},
    {"key": "support", "address": "support@", "group": ("Support", "Support"), "label": ("Support client", "Customer support"),
     "rule": ("Mots d'incident (panne, urgence, réclamation, défaut, SAV).", "Incident words (breakdown, urgent, complaint, defect, after-sales).")},
    {"key": "contact", "address": "contact@", "group": ("Général", "General"), "label": ("Contact général", "General contact"),
     "rule": ("Tout autre message externe (formulaire du site, email non classé).", "Any other external message (website form, unclassified email).")},
]  # fmt: skip


def _localized(box: dict) -> dict:
    return {k: tx(*v) if isinstance(v, tuple) else v for k, v in box.items()}


MAILBOX_KEYS = {m["key"] for m in MAILBOXES}

_SUPPORT_RE = re.compile(r"\b(panne|urgent|urgence|réclamation|reclamation|défaut|defaut|sav|line down|is down|broken|complaint|support)\b", re.IGNORECASE)
_DEMO_SOURCES = {"mock_email", "mock_website", "mock_calendar", "simulated_demo"}


def _intent_keys(c: Communication) -> set[str]:
    text = f"{c.subject or ''} {c.body or ''}".lower()
    return {key for key, _label, words in _INTENTS if any(w in text for w in words)}


def classify(c: Communication, candidate_comm_ids: set[uuid.UUID]) -> tuple[str, str] | None:
    """(mailbox key, reason) for an external email/website message, None for
    internal notes and calendar events (not mail)."""

    if c.channel not in {"email", "website"}:
        return None
    intents = _intent_keys(c)
    text = f"{c.subject or ''} {c.body or ''}".lower()
    if c.id in candidate_comm_ids or c.related_entity_type == RelatedEntityType.CANDIDATE:
        return "careers", tx("Candidat lié à ce message", "Candidate linked to this message")
    if c.purpose in {"interview_invite"} or "application" in intents:
        return "careers", tx("Intention « candidature » détectée", '"Application" intent detected')
    if c.related_entity_type == RelatedEntityType.SUPPLIER:
        return "rfq", tx("Fournisseur lié", "Linked supplier")
    if c.channel_detail == "agency_proposal":
        return "contact", tx("Sollicitation commerciale reçue (agence)", "Commercial solicitation received (agency)")
    if _SUPPORT_RE.search(text):
        return "support", tx("Mots d'incident détectés", "Incident words detected")
    if c.related_entity_type == RelatedEntityType.CUSTOMER and intents & {"order", "delivery", "invoice"}:
        return "orders", tx("Client lié · commande/livraison/facture", "Linked customer · order/delivery/invoice")
    if c.related_entity_type == RelatedEntityType.CUSTOMER:
        return "sales", tx("Client lié", "Linked customer")
    if "quote_request" in intents or c.channel_detail == "quote_form":
        return "sales", tx("Demande de devis/prix", "Quote/price request")
    if c.channel_detail == "contact_form":
        return "contact", tx("Formulaire de contact du site", "Website contact form")
    return "contact", tx("Aucune règle plus précise", "No more specific rule")


def _is_answered(msg: Communication, sent: list[Communication], now: datetime) -> Communication | None:
    received = _as_aware_utc(msg.occurred_at)
    replies = [
        o
        for o in sent
        if received < _as_aware_utc(o.occurred_at) <= now and ((msg.thread_key and o.thread_key == msg.thread_key) or (msg.contact_id and o.contact_id == msg.contact_id))
    ]
    return min(replies, key=lambda o: o.occurred_at) if replies else None


def _load(session: Session, company_id: uuid.UUID):
    comms = session.query(Communication).filter(Communication.company_id == company_id).order_by(Communication.occurred_at.desc()).all()
    candidate_ids = {c.communication_id for c in session.query(Candidate).filter(Candidate.company_id == company_id, Candidate.communication_id.isnot(None))}
    sent = [c for c in comms if c.direction == CommunicationDirection.OUTBOUND and c.status == "sent"]
    return comms, candidate_ids, sent


def _email_provider_is_demo() -> bool:
    try:
        return type(connector_registry.get_connector("email")).__name__.startswith("Mock")
    except KeyError:
        return True


def _box_status(messages: list[Communication]) -> tuple[str, str]:
    """"connected" needs a real (non-mock) email provider AND a message it
    delivered to this address; seeded/demo messages never make a box connected."""

    if not messages:
        return "not_configured", tx("Aucune adresse ni aucun message : boîte non configurée.", "No address and no message: mailbox not configured.")
    real = [m for m in messages if m.direction == CommunicationDirection.INBOUND and m.to_address and m.source and m.source not in _DEMO_SOURCES]
    if real and not _email_provider_is_demo():
        return "connected", tx("Messages reçus par une source connectée.", "Messages received from a connected source.")
    return "demo", tx("Messages issus des fournisseurs de démonstration ; aucune boîte réelle n'est connectée.", "Messages from the demo providers; no real mailbox is connected.")


def mailbox_overview(session: Session, company_id: uuid.UUID) -> dict:
    now = datetime.now(timezone.utc)
    comms, candidate_ids, sent = _load(session, company_id)
    placed: dict[str, list[Communication]] = {k: [] for k in MAILBOX_KEYS}
    excluded = 0
    for c in comms:
        if c.status in {"draft", "pending_validation", "rejected"}:
            continue
        box = classify(c, candidate_ids)
        if box is None:
            excluded += 1
        else:
            placed[box[0]].append(c)
    boxes = []
    for m in MAILBOXES:
        msgs = placed[m["key"]]
        inbound = [c for c in msgs if c.direction == CommunicationDirection.INBOUND]
        status, status_reason = _box_status(msgs)
        boxes.append(
            _localized(m)
            | {
                "status": status,
                "status_reason": status_reason,
                "message_count": len(msgs),
                "inbound_count": len(inbound),
                "awaiting_reply": sum(1 for c in inbound if _is_answered(c, sent, now) is None),
                "last_at": msgs[0].occurred_at if msgs else None,
            }
        )
    providers = {name: type(connector_registry.get_connector(name)).__name__ for name in connector_registry.list_connectors()}
    return {
        "mailboxes": boxes,
        "excluded_count": excluded,
        "providers": [{"connector": k, "provider": v, "demo": v.startswith("Mock")} for k, v in providers.items()],
        "method": tx("Classement déterministe des messages existants (règle affichée sur chaque message). Aucune adresse réelle n'est connectée.", "Deterministic classification of existing messages (rule shown on each message). No real address is connected."),
    }


def list_mailbox(session: Session, company_id: uuid.UUID, key: str) -> list[dict]:
    if key not in MAILBOX_KEYS:
        raise ValueError(key)
    now = datetime.now(timezone.utc)
    comms, candidate_ids, sent = _load(session, company_id)
    rows = []
    for c in comms:
        if c.status in {"draft", "pending_validation", "rejected"}:
            continue
        box = classify(c, candidate_ids)
        if box is None or box[0] != key:
            continue
        needs_reply = c.direction == CommunicationDirection.INBOUND and _is_answered(c, sent, now) is None
        rows.append(_row(session, c) | {"mailbox": key, "mailbox_reason": box[1], "needs_reply": needs_reply})
    return rows


def _replies_to(out: Communication, inbound: list[Communication]) -> Communication | None:
    sent_at = _as_aware_utc(out.occurred_at)
    replies = [
        i
        for i in inbound
        if _as_aware_utc(i.occurred_at) > sent_at and ((out.thread_key and i.thread_key == out.thread_key) or (out.contact_id and i.contact_id == out.contact_id))
    ]
    return min(replies, key=lambda i: i.occurred_at) if replies else None


def follow_up_performance(session: Session, company_id: uuid.UUID) -> dict:
    """Outbound emails prepared in the app, stage by stage. `validated` counts
    HITL approvals (send_email tasks executed); `sent` counts messages
    actually handed to the provider; a reply is an inbound message on the
    same thread/contact after the send; an order is a customer/purchase
    order derived from a document the message concerns."""

    now = datetime.now(timezone.utc)
    comms, _candidate_ids, _sent = _load(session, company_id)
    outbound = [c for c in comms if c.direction == CommunicationDirection.OUTBOUND and c.channel == "email" and c.purpose]
    inbound = [c for c in comms if c.direction == CommunicationDirection.INBOUND and c.channel in {"email", "website"}]
    sent = [c for c in outbound if c.status == "sent"]
    tasks = session.query(Task).filter(Task.company_id == company_id).all()
    validated = sum(1 for t in tasks if t.pending_action == "send_email" and t.status == TaskStatus.EXECUTED)

    replied: list[tuple[Communication, Communication]] = [(o, r) for o in sent if (r := _replies_to(o, inbound)) is not None]
    reply_delays = [(_as_aware_utc(r.occurred_at) - _as_aware_utc(o.occurred_at)).total_seconds() / 3600 for o, r in replied]

    # Our own response delay: inbound message -> first sent answer.
    answered = [(i, a) for i in inbound if (a := _is_answered(i, sent, now)) is not None]
    our_delays = [(_as_aware_utc(a.occurred_at) - _as_aware_utc(i.occurred_at)).total_seconds() / 3600 for i, a in answered]

    orders = []
    sent_ids = {o.id for o in sent}
    links = session.query(ObjectLink).filter(ObjectLink.company_id == company_id, ObjectLink.source_type == "communication", ObjectLink.target_type == "commercial_document").all()
    concerned = {(l.source_id, l.target_id) for l in links if l.source_id in sent_ids}
    for comm_id, doc_id in concerned:
        derived = (
            session.query(ObjectLink)
            .filter(ObjectLink.company_id == company_id, ObjectLink.relation == "derived_from", ObjectLink.target_type == "commercial_document", ObjectLink.target_id == doc_id)
            .all()
        )
        for d in derived:
            doc = session.get(CommercialDocument, d.source_id)
            if doc is not None and doc.kind in {DocumentKind.CUSTOMER_ORDER, DocumentKind.PURCHASE_ORDER}:
                orders.append({"communication_id": comm_id, "document_id": doc.id, "number": doc.number, "kind": doc.kind.value})

    enough = len(sent) >= MIN_SAMPLE
    by_purpose: dict[str, dict] = {}
    for o in outbound:
        b = by_purpose.setdefault(o.purpose, {"purpose": o.purpose, "prepared": 0, "sent": 0, "replied": 0})
        b["prepared"] += 1
        b["sent"] += o.status == "sent"
    for o, _r in replied:
        by_purpose[o.purpose]["replied"] += 1

    return {
        "prepared": len(outbound),
        "draft": sum(1 for c in outbound if c.status == "draft"),
        "pending_validation": sum(1 for c in outbound if c.status == "pending_validation"),
        "rejected": sum(1 for c in outbound if c.status == "rejected"),
        "validated": validated,
        "sent": len(sent),
        "replies_received": len(replied),
        "reply_rate": (len(replied) / len(sent)) if enough else None,
        "avg_reply_delay_hours": (sum(reply_delays) / len(reply_delays)) if enough and reply_delays else None,
        "avg_our_response_hours": (sum(our_delays) / len(our_delays)) if len(our_delays) >= MIN_SAMPLE else None,
        "awaiting_their_reply": len(sent) - len(replied),
        "awaiting_our_reply": sum(1 for i in inbound if _is_answered(i, sent, now) is None),
        "orders_linked": orders,
        "by_purpose": sorted(by_purpose.values(), key=lambda b: -b["prepared"]),
        "sufficient": enough,
        "min_sample": MIN_SAMPLE,
        "method": tx("Comptage des messages réels. Envoi = remis au fournisseur email (simulé en démonstration). Réponse = message entrant sur le même fil ou du même contact après l'envoi. Commande = commande dérivée d'un document concerné par le message.", "Count of real messages. Sent = handed to the email provider (simulated in the demo). Reply = incoming message on the same thread or from the same contact after sending. Order = order derived from a document the message concerns."),
    }


_CAMPAIGN_RE = re.compile(r"(?i:campagne)\s+([A-ZÀ-Ý][\wÀ-ÿ-]+)")
_PCT_RE = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s?%")
_MONTHS_FR = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def campaign_performance(session: Session, company_id: uuid.UUID) -> dict:
    """Campaigns exist only as messages today (internal reports, agency
    proposals, team ideas). A campaign is named by the text "Campagne X";
    its figures are what the text DECLARES, checked against what the
    database OBSERVES (inbound website/email requests per month). No budget,
    lead or sale is attributed without a real link."""

    comms = session.query(Communication).filter(Communication.company_id == company_id).order_by(Communication.occurred_at.asc()).all()
    related = [c for c in comms if c.channel_detail in {"campaign_report", "agency_proposal"} or "campagne" in f"{c.subject or ''} {c.body or ''}".lower()]
    inbound_requests = [c for c in comms if c.direction == CommunicationDirection.INBOUND and c.channel in {"website", "email"} and c.channel_detail not in {"agency_proposal"}]

    def month_count(year: int, month: int) -> int:
        return sum(1 for c in inbound_requests if (d := _as_aware_utc(c.occurred_at)).year == year and d.month == month)

    campaigns: dict[str, dict] = {}
    proposals = []
    for c in related:
        if c.channel_detail == "agency_proposal":
            proposals.append(_row(session, c))
            continue
        m = _CAMPAIGN_RE.search(c.subject or "") or _CAMPAIGN_RE.search(c.body or "")
        name = m.group(1) if m else tx("Sans nom", "Unnamed")
        camp = campaigns.setdefault(name, {"name": name, "reports": [], "feedback": [], "declared": [], "observed": None})
        if c.channel_detail == "campaign_report":
            camp["reports"].append(_row(session, c))
            for pct in _PCT_RE.findall(c.body or ""):
                camp["declared"].append({"text": (c.body or "")[:200], "value_pct": float(pct.replace(",", ".")), "source": tx("Rapport interne", "Internal report"), "basis": "declared"})
        else:
            camp["feedback"].append(_row(session, c))
        month = _MONTHS_FR.get(name.lower())
        if month and camp["observed"] is None:
            year = _as_aware_utc(c.occurred_at).year
            prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
            cur, prev = month_count(year, month), month_count(prev_y, prev_m)
            camp["observed"] = {
                "period": f"{year:04d}-{month:02d}",
                "previous_period": f"{prev_y:04d}-{prev_m:02d}",
                "inbound_requests": cur,
                "previous_inbound_requests": prev,
                "change_pct": ((cur - prev) / prev) if prev else None,
                "basis": "observed",
                "note": tx("Demandes entrantes (site + email) comptées dans la base sur la période. Toutes les demandes, pas seulement celles liées à la campagne.", "Incoming requests (website + email) counted in the database over the period. All requests, not only those linked to the campaign."),
            }

    # Team feedback also lives in tasks mentioning a campaign.
    tasks = [t for t in session.query(Task).filter(Task.company_id == company_id).all() if "campagne" in f"{t.title or ''} {t.description or ''}".lower()]
    for camp in campaigns.values():
        camp["tasks"] = [{"id": t.id, "title": text_of(t, "title"), "status": getattr(t.status, "value", t.status)} for t in tasks if camp["name"].lower() in f"{t.title or ''} {t.description or ''}".lower()]
        camp["metrics"] = {
            "budget": None,
            "prospects_attributed": None,
            "opportunities_attributed": None,
            "sales_attributed": None,
            "roi": None,
            "cost_per_prospect": None,
        }
        camp["limits"] = [
            tx("Budget non enregistré : ROI et coût par prospect incalculables.", "No budget recorded: ROI and cost per prospect cannot be computed."),
            tx("Aucun lien entre les demandes entrantes et la campagne (pas de source ni de code de suivi) : attribution non établie.", "No link between incoming requests and the campaign (no source or tracking code): attribution not established."),
        ]
    return {
        "campaigns": list(campaigns.values()),
        "agency_proposals": proposals,
        "channels_connected": [],
        "method": tx("Campagnes identifiées dans les messages existants. Déclaré = écrit dans un rapport ; observé = compté dans la base ; rien n'est attribué sans lien réel.", "Campaigns identified in existing messages. Declared = written in a report; observed = counted in the database; nothing is attributed without a real link."),
    }
