"""The kinds of monitoring Risks, identified by the start of their title.

Titles are generated in both interface languages (brain/decisions.md #58):
the `title` column keeps the French one and the `i18n` column both. The
English prefix is also the one titles carried before V2.3, so a row written
in either language -- or by a database not yet migrated -- is still
recognised by de-duplication (app.intelligence.risks.service) and by the
Business State Snapshot. One place, so a title and its recognition can never
drift apart again."""

from dataclasses import dataclass

from app.core.i18n import colon, num, pct, tx

__all__ = ["RiskKind", "num", "pct", "review_task_texts"]


@dataclass(frozen=True)
class RiskKind:
    prefix: str  # French
    legacy_prefix: str  # English (also the pre-V2.3 title)

    def title(self, subject: str) -> str:
        return f"{tx(self.prefix, self.legacy_prefix)}{colon()} {subject}"

    def matches(self, title: str | None) -> bool:
        return bool(title) and (title.startswith(self.prefix) or title.startswith(self.legacy_prefix))


MARGIN_DETERIORATION = RiskKind("Dégradation de marge", "Margin deterioration")
SUPPLIER_PERFORMANCE = RiskKind("Dégradation des délais fournisseur", "Supplier performance deterioration")
CUSTOMER_DECLINE = RiskKind("Baisse d'activité client", "Customer decline")
SUPPLIER_COST_INCREASE = RiskKind("Hausse du coût fournisseur", "Supplier cost increase")
# Opportunity, same convention.
GROWING_CUSTOMER = RiskKind("Client en croissance", "Growing customer")

REVIEW_TASK_PREFIX = "À examiner"
LEGACY_REVIEW_TASK_PREFIX = "Review"


def review_task_texts(risk_i18n: dict | None, title: str, description: str | None) -> dict:
    """Both languages of the review Task created for a Risk."""

    def render(locale: str) -> dict:
        source = (risk_i18n or {}).get(locale) or {"title": title, "description": description}
        body = source.get("description") or source["title"]
        if locale == "en":
            return {"title": f"Review: {source['title']}", "description": f"{body} To review, then decide what to do next."}
        return {"title": f"{REVIEW_TASK_PREFIX} : {source['title']}", "description": f"{body} À examiner, puis décider de la suite."}

    return {"fr": render("fr"), "en": render("en")}
