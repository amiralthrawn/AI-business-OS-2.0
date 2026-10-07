"""Business-language labels, in the active interface language
(app.core.i18n), for the internal identifiers the Observation/
Interpretation/Decision Engines pass around (Step 27). A machine identifier
like `"delivery_delay_days"` or `"deviating unfavorably"` must never reach a
human-facing string -- every place that builds business text from one of
these uses this single shared mapping, so a name is only ever translated
once, consistently, everywhere.
"""

from app.core.i18n import current_locale

OBSERVABLE_LABELS: dict[str, dict[str, str]] = {
    "margin_pct": {"fr": "la marge", "en": "margin"},
    "delivery_delay_days": {"fr": "les délais de livraison", "en": "delivery times"},
    "customer_revenue_variation_pct": {"fr": "le chiffre d'affaires client", "en": "customer revenue"},
    "supplier_unanswered_message_age_days": {"fr": "les messages fournisseur sans réponse", "en": "unanswered supplier messages"},
    "customer_unanswered_message_age_days": {"fr": "les messages client sans réponse", "en": "unanswered customer messages"},
    "customer_quote_pending_age_days": {"fr": "les devis client en attente de réponse", "en": "customer quotes awaiting an answer"},
}

IMPACT_LABELS: dict[str, dict[str, str]] = {
    "low": {"fr": "faible", "en": "low"},
    "medium": {"fr": "moyen", "en": "medium"},
    "high": {"fr": "élevé", "en": "high"},
}
DOMAIN_LABELS: dict[str, dict[str, str]] = {
    "finance": {"fr": "Finance", "en": "Finance"},
    "procurement": {"fr": "Achats", "en": "Procurement"},
    "sales": {"fr": "Ventes", "en": "Sales"},
}


def _pick(table: dict[str, dict[str, str]], key: str | None) -> str:
    if not key:
        return ""
    entry = table.get(key)
    return entry[current_locale()] if entry else key


def observable_label(observable: str | None) -> str:
    return _pick(OBSERVABLE_LABELS, observable)


def impact_label(impact: str | None) -> str:
    return _pick(IMPACT_LABELS, impact)


def domain_label(domain: str | None) -> str:
    return _pick(DOMAIN_LABELS, domain)
