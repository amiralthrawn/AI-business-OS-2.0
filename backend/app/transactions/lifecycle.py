"""State machines, numbering prefixes and derivation rules of commercial
documents (V2, brain/transactional_model.md). Pure data + tiny helpers: the
single source every service, the contextual API and the frontend (via
`GET /documents/meta`) read, so a status or a derivation is never
hard-coded in two places."""

from dataclasses import dataclass

from app.core.entities import DocumentKind


@dataclass(frozen=True)
class KindSpec:
    prefix: str
    label: str  # French UI label, singular
    domain: str  # "sales" | "procurement"
    party: str  # "customer" | "supplier"
    initial_status: str
    # status -> allowed next statuses
    transitions: dict[str, tuple[str, ...]]
    status_labels: dict[str, str]
    # Statuses meaning "this document is finished" (won/lost, closed, ...).
    terminal: frozenset[str]


K = DocumentKind

KINDS: dict[DocumentKind, KindSpec] = {
    K.CUSTOMER_REQUEST: KindSpec(
        prefix="DEM",
        label="Demande client",
        domain="sales",
        party="customer",
        initial_status="new",
        transitions={
            "new": ("qualifying", "quoting", "lost"),
            "qualifying": ("quoting", "lost"),
            "quoting": ("negotiating", "won", "lost"),
            "negotiating": ("quoting", "won", "lost"),
        },
        status_labels={
            "new": "Nouvelle",
            "qualifying": "Qualification",
            "quoting": "Chiffrage",
            "negotiating": "Négociation",
            "won": "Gagnée",
            "lost": "Perdue",
        },
        terminal=frozenset({"won", "lost"}),
    ),
    K.CUSTOMER_QUOTE: KindSpec(
        prefix="DEV",
        label="Devis client",
        domain="sales",
        party="customer",
        initial_status="draft",
        transitions={
            "draft": ("sent", "cancelled"),
            "sent": ("accepted", "rejected", "expired", "draft"),
            "expired": ("draft",),
        },
        status_labels={
            "draft": "Brouillon",
            "sent": "Envoyé",
            "accepted": "Accepté",
            "rejected": "Refusé",
            "expired": "Expiré",
            "cancelled": "Annulé",
        },
        terminal=frozenset({"accepted", "rejected", "cancelled"}),
    ),
    K.CUSTOMER_ORDER: KindSpec(
        prefix="CMD",
        label="Commande client",
        domain="sales",
        party="customer",
        initial_status="draft",
        # draft -> confirmed stays possible (an order received firm, e.g. the
        # customer's own PO). "sent"/"acknowledged" record, when it happens,
        # that the order was transmitted and that the CUSTOMER acknowledged
        # receipt -- each set by a person recording that event, never inferred.
        transitions={
            "draft": ("sent", "confirmed", "cancelled"),
            "sent": ("acknowledged", "confirmed", "cancelled"),
            "acknowledged": ("confirmed", "cancelled"),
            "confirmed": ("delivered", "cancelled"),
            "delivered": ("invoiced",),
            "invoiced": ("closed",),
        },
        status_labels={
            "draft": "Brouillon",
            "sent": "Transmise au client",
            "acknowledged": "Réception accusée par le client",
            "confirmed": "Confirmée",
            "delivered": "Livrée",
            "invoiced": "Facturée",
            "closed": "Clôturée",
            "cancelled": "Annulée",
        },
        terminal=frozenset({"closed", "cancelled"}),
    ),
    K.CUSTOMER_DELIVERY: KindSpec(
        prefix="LIV",
        label="Livraison client",
        domain="sales",
        party="customer",
        initial_status="planned",
        transitions={"planned": ("shipped", "cancelled"), "shipped": ("delivered",)},
        status_labels={"planned": "Planifiée", "shipped": "Expédiée", "delivered": "Livrée", "cancelled": "Annulée"},
        terminal=frozenset({"delivered", "cancelled"}),
    ),
    K.CUSTOMER_INVOICE: KindSpec(
        prefix="FAC",
        label="Facture client",
        domain="sales",
        party="customer",
        initial_status="draft",
        transitions={"draft": ("issued", "cancelled"), "issued": ("partially_paid", "paid"), "partially_paid": ("paid",)},
        status_labels={"draft": "Brouillon", "issued": "Émise", "partially_paid": "Partiellement réglée", "paid": "Réglée", "cancelled": "Annulée"},
        terminal=frozenset({"paid", "cancelled"}),
    ),
    K.PURCHASE_REQUEST: KindSpec(
        prefix="DA",
        label="Demande d'achat",
        domain="procurement",
        party="supplier",
        initial_status="draft",
        transitions={
            "draft": ("consulting", "cancelled"),
            "consulting": ("comparing", "cancelled"),
            "comparing": ("decided", "consulting", "cancelled"),
            "decided": ("ordered",),
        },
        status_labels={
            "draft": "Brouillon",
            "consulting": "Consultation fournisseurs",
            "comparing": "Comparaison",
            "decided": "Fournisseur choisi",
            "ordered": "Commandée",
            "cancelled": "Annulée",
        },
        terminal=frozenset({"ordered", "cancelled"}),
    ),
    K.SUPPLIER_QUOTE: KindSpec(
        prefix="DFO",
        label="Devis fournisseur",
        domain="procurement",
        party="supplier",
        initial_status="requested",
        transitions={
            "requested": ("received", "declined"),
            "received": ("selected", "declined"),
        },
        status_labels={
            "requested": "Demandé",
            "received": "Reçu",
            "selected": "Retenu",
            "declined": "Écarté",
        },
        terminal=frozenset({"selected", "declined"}),
    ),
    K.PURCHASE_ORDER: KindSpec(
        prefix="BC",
        label="Commande fournisseur",
        domain="procurement",
        party="supplier",
        initial_status="draft",
        transitions={
            "draft": ("sent", "cancelled"),
            "sent": ("confirmed", "cancelled"),
            "confirmed": ("received", "cancelled"),
            "received": ("closed",),
        },
        status_labels={
            "draft": "Brouillon",
            "sent": "Envoyée",
            "confirmed": "Confirmée",
            "received": "Reçue",
            "closed": "Clôturée",
            "cancelled": "Annulée",
        },
        terminal=frozenset({"closed", "cancelled"}),
    ),
    K.RECEPTION: KindSpec(
        prefix="REC",
        label="Réception",
        domain="procurement",
        party="supplier",
        initial_status="expected",
        transitions={"expected": ("received", "cancelled")},
        status_labels={"expected": "Attendue", "received": "Reçue", "cancelled": "Annulée"},
        terminal=frozenset({"received", "cancelled"}),
    ),
    K.SUPPLIER_INVOICE: KindSpec(
        prefix="FFO",
        label="Facture fournisseur",
        domain="procurement",
        party="supplier",
        initial_status="received",
        transitions={"received": ("approved", "disputed"), "disputed": ("approved",), "approved": ("partially_paid", "paid"), "partially_paid": ("paid",)},
        status_labels={"received": "Reçue", "approved": "Validée", "disputed": "Contestée", "partially_paid": "Partiellement réglée", "paid": "Réglée"},
        terminal=frozenset({"paid"}),
    ),
    K.CUSTOMER_CREDIT_NOTE: KindSpec(
        prefix="AV",
        label="Avoir client",
        domain="sales",
        party="customer",
        initial_status="draft",
        # Offered to the customer, answered by the customer (recorded by a
        # person), validated internally (HITL), then imputed once
        # (app.billing). Creating a credit note never means it is accepted.
        transitions={
            "draft": ("submitted", "cancelled"),
            "submitted": ("accepted", "rejected", "draft"),  # -> draft: the customer asked for a change
            "accepted": ("validated",),
            "validated": ("applied",),
            "applied": ("refunded",),
        },
        status_labels={
            "draft": "Préparé",
            "submitted": "Soumis au client — en attente de réponse",
            "accepted": "Accepté par le client",
            "rejected": "Refusé par le client",
            "validated": "Validé comptablement",
            "applied": "Imputé au compte client",
            "refunded": "Remboursé",
            "cancelled": "Annulé",
        },
        terminal=frozenset({"rejected", "refunded", "cancelled"}),
    ),
    K.SUPPLIER_CREDIT_NOTE: KindSpec(
        prefix="AVF",
        label="Avoir fournisseur",
        domain="procurement",
        party="supplier",
        initial_status="requested",
        # Our claim to a supplier (non-conformity, price error): requested,
        # then confirmed or refused BY THE SUPPLIER (recorded by a person),
        # then imputed once on what we owe them.
        transitions={
            "requested": ("confirmed", "rejected", "cancelled"),
            "confirmed": ("applied",),
        },
        status_labels={
            "requested": "Réclamation envoyée — avoir demandé",
            "confirmed": "Avoir confirmé par le fournisseur",
            "rejected": "Refusé par le fournisseur",
            "applied": "Imputé",
            "cancelled": "Annulé",
        },
        terminal=frozenset({"rejected", "applied", "cancelled"}),
    ),
}

# Statuses only the system may set, because they follow a recorded fact:
# payments (invoice settlement), a human approval in the HITL flow
# (validation) or the imputation/refund bookkeeping of app.billing. They are
# never offered as a plain "change status" button.
SYSTEM_STATUSES: dict[DocumentKind, frozenset[str]] = {
    K.CUSTOMER_INVOICE: frozenset({"partially_paid", "paid"}),
    K.SUPPLIER_INVOICE: frozenset({"partially_paid", "paid"}),
    K.CUSTOMER_CREDIT_NOTE: frozenset({"validated", "applied", "refunded"}),
    K.SUPPLIER_CREDIT_NOTE: frozenset({"applied"}),
}

# Invoice statuses that carry a receivable/payable.
OPEN_INVOICE_STATUSES = {
    K.CUSTOMER_INVOICE: frozenset({"issued", "partially_paid", "paid"}),
    K.SUPPLIER_INVOICE: frozenset({"received", "approved", "disputed", "partially_paid", "paid"}),
}

# source kind -> kinds that can be created from it. Deriving copies parties
# and lines and records a `derived_from` ObjectLink (new -> source).
DERIVATIONS: dict[DocumentKind, tuple[DocumentKind, ...]] = {
    K.CUSTOMER_REQUEST: (K.CUSTOMER_QUOTE, K.PURCHASE_REQUEST),
    K.CUSTOMER_QUOTE: (K.CUSTOMER_ORDER,),
    K.CUSTOMER_ORDER: (K.CUSTOMER_DELIVERY, K.CUSTOMER_INVOICE, K.PURCHASE_REQUEST, K.CUSTOMER_CREDIT_NOTE),
    K.CUSTOMER_DELIVERY: (K.CUSTOMER_CREDIT_NOTE,),
    K.CUSTOMER_INVOICE: (K.CUSTOMER_CREDIT_NOTE,),
    K.PURCHASE_REQUEST: (K.SUPPLIER_QUOTE, K.PURCHASE_ORDER),
    K.SUPPLIER_QUOTE: (K.PURCHASE_ORDER,),
    K.PURCHASE_ORDER: (K.RECEPTION, K.SUPPLIER_INVOICE, K.SUPPLIER_CREDIT_NOTE),
    K.RECEPTION: (K.SUPPLIER_CREDIT_NOTE,),
    K.SUPPLIER_INVOICE: (K.SUPPLIER_CREDIT_NOTE,),
}

# Which write permission edits a kind (app.access.policy). Physical flow
# (receptions/deliveries) is Operations', invoices are Finance's -- a
# commercial can quote but not book a supplier invoice.
KIND_WRITE_PERMISSION: dict[DocumentKind, str] = {
    K.CUSTOMER_REQUEST: "write:sales",
    K.CUSTOMER_QUOTE: "write:sales",
    K.CUSTOMER_ORDER: "write:sales",
    K.CUSTOMER_DELIVERY: "write:operations",
    K.CUSTOMER_INVOICE: "write:finance",
    K.PURCHASE_REQUEST: "write:procurement",
    K.SUPPLIER_QUOTE: "write:procurement",
    K.PURCHASE_ORDER: "write:procurement",
    K.RECEPTION: "write:operations",
    K.SUPPLIER_INVOICE: "write:finance",
    # Offering a credit note / claiming one is commercial work; imputing it
    # and refunding are Finance's (app.billing checks write:finance).
    K.CUSTOMER_CREDIT_NOTE: "write:sales",
    K.SUPPLIER_CREDIT_NOTE: "write:procurement",
}

PREFIX_TO_KIND: dict[str, DocumentKind] = {spec.prefix: kind for kind, spec in KINDS.items()}


def spec(kind: DocumentKind) -> KindSpec:
    return KINDS[kind]


def allowed_transitions(kind: DocumentKind, status: str) -> tuple[str, ...]:
    return KINDS[kind].transitions.get(status, ())


def manual_transitions(kind: DocumentKind, status: str) -> tuple[str, ...]:
    """The transitions a person may trigger directly (status buttons, the
    status API) -- all of them minus the system-only ones."""

    blocked = SYSTEM_STATUSES.get(kind, frozenset())
    return tuple(s for s in allowed_transitions(kind, status) if s not in blocked)


def status_label(kind: DocumentKind, status: str) -> str:
    return KINDS[kind].status_labels.get(status, status)
