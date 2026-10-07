"""v2.3 French generated texts (data only)

The V1 monitoring rules used to write their risks, opportunities, review
tasks and the default objective in English; the interface is French-only
(brain/decisions.md #56). This rewrites the texts already stored, with the
same wording the rules now produce. Only texts matching a known generated
pattern are touched -- anything typed by a person is left as is. Idempotent
(a French text matches no pattern). No schema change.

Revision ID: e7a1c2f4b9d3
Revises: d1688efa5611
Create Date: 2026-10-07 10:00:00
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c2f4b9d3"
down_revision: Union[str, None] = "d1688efa5611"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NNBSP = " "


def _num(raw: str, digits: int) -> str:
    return f"{float(raw):,.{digits}f}".replace(",", NNBSP).replace(".", ",")


def _pct(raw: str, digits: int = 1) -> str:
    return f"{float(raw):.{digits}f}".replace(".", ",") + f"{NNBSP}%"


# (pattern, replacement builder) -- applied in order, first match wins.
TITLE_RULES = [
    (re.compile(r"^Margin deterioration on product (?P<x>.+)$"), lambda m: f"Dégradation de marge : {m['x']}"),
    (re.compile(r"^Supplier performance deterioration: (?P<x>.+)$"), lambda m: f"Dégradation des délais fournisseur : {m['x']}"),
    (re.compile(r"^Customer decline: (?P<x>.+)$"), lambda m: f"Baisse d'activité client : {m['x']}"),
    (re.compile(r"^Supplier cost increase of (?P<p>\d+)% on product (?P<x>.+)$"), lambda m: f"Hausse du coût fournisseur : {m['x']} (+{m['p']}{NNBSP}%)"),
    (re.compile(r"^Growing customer: (?P<x>.+)$"), lambda m: f"Client en croissance : {m['x']}"),
]

DESCRIPTION_RULES = [
    # Treasury risk written with a lost comma ("90 jours  sous").
    (re.compile(r"^(?P<a>Projection basse à .+ sur 90 jours)  (?P<b>sous le seuil déclaré de .+)$"), lambda m: f"{m['a']}, {m['b']}"),
    (
        re.compile(r"^Margin moved from (?P<a>-?[\d.]+)% to (?P<b>-?[\d.]+)% \((?P<c>[+-][\d.]+)% pts\) based on recent purchase and sales transactions\.$"),
        lambda m: f"La marge est passée de {_pct(m['a'])} à {_pct(m['b'])} ({'+' if not m['c'].startswith('-') else '−'}{_num(m['c'].lstrip('+-'), 1)} pts), d'après les achats et ventes récents.",
    ),
    (
        re.compile(r"^Average delivery delay rose from (?P<a>[\d.]+) to (?P<b>[\d.]+) days; on-time rate fell from (?P<c>\d+)% to (?P<d>\d+)%\.$"),
        lambda m: f"Le retard moyen de livraison est passé de {_num(m['a'], 1)} à {_num(m['b'], 1)} jours ; le taux de livraison à l'heure est passé de {m['c']}{NNBSP}% à {m['d']}{NNBSP}%.",
    ),
    (
        re.compile(r"^Revenue from (?P<x>.+) fell (?P<p>[\d.]+)% \(from (?P<a>[\d.]+) to (?P<b>[\d.]+)\) -- possible churn risk\.$"),
        lambda m: f"Le chiffre d'affaires de {m['x']} a baissé de {_pct(m['p'])} (de {_num(m['a'], 0)} € à {_num(m['b'], 0)} €) : risque de perte du client.",
    ),
    (
        re.compile(r"^Revenue from (?P<x>.+) increased (?P<p>[\d.]+)% \(from (?P<a>[\d.]+) to (?P<b>[\d.]+)\)\. Consider expanding this relationship\.$"),
        lambda m: f"Le chiffre d'affaires de {m['x']} a augmenté de {_pct(m['p'])} (de {_num(m['a'], 0)} € à {_num(m['b'], 0)} €). Piste : développer cette relation.",
    ),
    (
        re.compile(r"^Unit cost rose from (?P<a>[\d.]+) to (?P<b>[\d.]+) \((?P<p>[\d.]+)%\), detected from event [0-9a-f-]+\.$"),
        lambda m: f"Le coût unitaire est passé de {_num(m['a'], 2)} € à {_num(m['b'], 2)} € (+{_pct(m['p'])}), constaté sur une facture ou un tarif fournisseur.",
    ),
]

LEGACY_OBJECTIVE = "Protect margin on core products and reduce single-supplier dependency."
FRENCH_OBJECTIVE = "Protéger la marge sur les produits clés et réduire la dépendance à un fournisseur unique."
REVIEW_SUFFIX_EN = " Review and decide on next steps."
REVIEW_SUFFIX_FR = " À examiner, puis décider de la suite."


def _apply(rules, text):
    if not text:
        return text
    for pattern, build in rules:
        m = pattern.match(text)
        if m:
            return build(m)
    return text


def translate_title(text: str | None) -> str | None:
    return _apply(TITLE_RULES, text)


def translate_description(text: str | None) -> str | None:
    return _apply(DESCRIPTION_RULES, text)


def translate_task_title(text: str | None) -> str | None:
    if text and text.startswith("Review: "):
        return "À examiner : " + translate_title(text[len("Review: "):])
    return text


def translate_task_description(text: str | None) -> str | None:
    if text and text.endswith(REVIEW_SUFFIX_EN):
        body = text[: -len(REVIEW_SUFFIX_EN)]
        return translate_description(translate_title(body)) + REVIEW_SUFFIX_FR
    return text


def _rewrite(conn, table: str, columns: dict) -> None:
    t = sa.table(table, sa.column("id"), *[sa.column(c) for c in columns])
    for row in conn.execute(sa.select(t)).mappings().all():
        changes = {}
        for col, fn in columns.items():
            new = fn(row[col])
            if new != row[col]:
                changes[col] = new
        if changes:
            conn.execute(sa.update(t).where(t.c.id == row["id"]).values(**changes))


def upgrade() -> None:
    conn = op.get_bind()
    _rewrite(conn, "risks", {"title": translate_title, "description": translate_description})
    _rewrite(conn, "opportunities", {"title": translate_title, "description": translate_description})
    _rewrite(conn, "tasks", {"title": translate_task_title, "description": translate_task_description})
    bc = sa.table("business_contexts", sa.column("stated_objectives"))
    conn.execute(sa.update(bc).where(bc.c.stated_objectives == LEGACY_OBJECTIVE).values(stated_objectives=FRENCH_OBJECTIVE))


def downgrade() -> None:
    # Data-only wording change: nothing to undo structurally. The French
    # texts stay valid for the code before this revision (kinds.py still
    # recognises both prefixes).
    pass
