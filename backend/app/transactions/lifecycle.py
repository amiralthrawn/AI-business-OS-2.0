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
        transitions={
            "draft": ("confirmed", "cancelled"),
            "confirmed": ("delivered", "cancelled"),
            "delivered": ("invoiced",),
            "invoiced": ("closed",),
        },
        status_labels={
            "draft": "Brouillon",
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
        transitions={"draft": ("issued", "cancelled"), "issued": ("paid",)},
        status_labels={"draft": "Brouillon", "issued": "Émise", "paid": "Payée", "cancelled": "Annulée"},
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
        transitions={"received": ("approved", "disputed"), "disputed": ("approved",), "approved": ("paid",)},
        status_labels={"received": "Reçue", "approved": "Validée", "disputed": "Contestée", "paid": "Payée"},
        terminal=frozenset({"paid"}),
    ),
}

# source kind -> kinds that can be created from it. Deriving copies parties
# and lines and records a `derived_from` ObjectLink (new -> source).
DERIVATIONS: dict[DocumentKind, tuple[DocumentKind, ...]] = {
    K.CUSTOMER_REQUEST: (K.CUSTOMER_QUOTE, K.PURCHASE_REQUEST),
    K.CUSTOMER_QUOTE: (K.CUSTOMER_ORDER,),
    K.CUSTOMER_ORDER: (K.CUSTOMER_DELIVERY, K.CUSTOMER_INVOICE, K.PURCHASE_REQUEST),
    K.PURCHASE_REQUEST: (K.SUPPLIER_QUOTE, K.PURCHASE_ORDER),
    K.SUPPLIER_QUOTE: (K.PURCHASE_ORDER,),
    K.PURCHASE_ORDER: (K.RECEPTION, K.SUPPLIER_INVOICE),
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
}

PREFIX_TO_KIND: dict[str, DocumentKind] = {spec.prefix: kind for kind, spec in KINDS.items()}


def spec(kind: DocumentKind) -> KindSpec:
    return KINDS[kind]


def allowed_transitions(kind: DocumentKind, status: str) -> tuple[str, ...]:
    return KINDS[kind].transitions.get(status, ())


def status_label(kind: DocumentKind, status: str) -> str:
    return KINDS[kind].status_labels.get(status, status)
