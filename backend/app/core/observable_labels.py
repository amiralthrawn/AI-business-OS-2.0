"""Business-language French labels for the internal identifiers the
Observation/Interpretation/Decision Engines pass around (Step 27). A machine
identifier like `"delivery_delay_days"` or `"deviating unfavorably"` must
never reach a human-facing string -- every place that builds business text
from one of these uses this single shared mapping, so a name is only ever
translated once, consistently, everywhere.
"""

OBSERVABLE_LABEL_FR: dict[str, str] = {
    "margin_pct": "la marge",
    "delivery_delay_days": "les délais de livraison",
    "customer_revenue_variation_pct": "le chiffre d'affaires client",
    "supplier_unanswered_message_age_days": "les messages fournisseur sans réponse",
    "customer_unanswered_message_age_days": "les messages client sans réponse",
    "customer_quote_pending_age_days": "les devis client en attente de réponse",
}

IMPACT_LABEL_FR: dict[str, str] = {"low": "faible", "medium": "moyen", "high": "élevé"}
URGENCY_LABEL_FR: dict[str, str] = {"low": "faible", "medium": "moyenne", "high": "élevée"}
DOMAIN_LABEL_FR: dict[str, str] = {"finance": "Finance", "procurement": "Achats", "sales": "Ventes"}


def observable_label(observable: str | None) -> str:
    if not observable:
        return ""
    return OBSERVABLE_LABEL_FR.get(observable, observable)
