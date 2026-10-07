"""v2.4 bilingual generated texts

The interface is bilingual (FR / EN, brain/decisions.md #58). Texts the OS
generates and stores -- Risks, Opportunities, system Tasks -- now keep both
languages in a new nullable `i18n` JSON column ({"fr": {"title",
"description"}, "en": {...}}); the `title` / `description` columns keep the
French text.

Rows already stored are backfilled from the known generated patterns (the
wording of the rules, frozen here): the French text is parsed and the English
one rebuilt with the same values. A text that matches no pattern -- anything
a person typed -- gets no `i18n` and is shown as written. Source data quoted
inside a text (names, references, a note, a declared reason) is never
translated. Idempotent: only rows whose `i18n` is NULL are read.

Analyses stored in the Event Log need no backfill: they are re-rendered at
read time (app.interpretation.engine.localize_interpretation,
app.decision.engine.localize_decision).

Revision ID: f3b8d5a2c7e1
Revises: e7a1c2f4b9d3
Create Date: 2026-10-07 18:00:00
"""
import re
from typing import Callable, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b8d5a2c7e1"
down_revision: Union[str, None] = "e7a1c2f4b9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("risks", "opportunities", "tasks")

N = r"-?[\d\s  .,]+"  # a number as French text wrote it


def _f(raw: str) -> float:
    text = re.sub(r"[\s  ]", "", raw)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return float(text)


def _num(raw: str, digits: int) -> str:
    return f"{_f(raw):,.{digits}f}"


def _money(raw: str, digits: int) -> str:
    value = _f(raw)
    return f"-€{abs(value):,.{digits}f}" if value < 0 else f"€{value:,.{digits}f}"


Rule = tuple[re.Pattern, Callable[[re.Match], str]]


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.S)


TITLE_RULES: list[Rule] = [
    (_rx(r"^Hausse du coût fournisseur : (?P<x>.+) \(\+(?P<p>\d+)\s?%\)$"), lambda m: f"Supplier cost increase: {m['x']} (+{m['p']}%)"),
    (_rx(r"^Dégradation de marge : (?P<x>.+)$"), lambda m: f"Margin deterioration: {m['x']}"),
    (_rx(r"^Dégradation des délais fournisseur : (?P<x>.+)$"), lambda m: f"Supplier performance deterioration: {m['x']}"),
    (_rx(r"^Baisse d'activité client : (?P<x>.+)$"), lambda m: f"Customer decline: {m['x']}"),
    (_rx(r"^Client en croissance : (?P<x>.+)$"), lambda m: f"Growing customer: {m['x']}"),
    (_rx(r"^Trésorerie projetée sous le seuil minimum$"), lambda m: "Projected cash below the minimum threshold"),
    (_rx(r"^Non-conformité — (?P<x>.+)$"), lambda m: f"Non-conformity — {m['x']}"),
    (_rx(r"^Recruter ou former : (?P<x>.+)$"), lambda m: f"Hire or train: {m['x']}"),
    (_rx(r"^Source moins chère possible pour (?P<p>.+) : (?P<l>.+)$"), lambda m: f"Possible cheaper source for {m['p']}: {m['l']}"),
]

DESCRIPTION_RULES: list[Rule] = [
    (
        _rx(rf"^Le coût unitaire est passé de (?P<a>{N}) € à (?P<b>{N}) € \(\+(?P<p>{N})\s?%\), constaté sur une facture ou un tarif fournisseur\.$"),
        lambda m: f"The unit cost rose from {_money(m['a'], 2)} to {_money(m['b'], 2)} (+{_num(m['p'], 1)}%), as seen on a supplier invoice or price list.",
    ),
    (
        _rx(rf"^La marge est passée de (?P<a>{N})\s?% à (?P<b>{N})\s?% \((?P<s>[+−-])(?P<d>{N}) pts\), d'après les achats et ventes récents\.$"),
        lambda m: f"The margin went from {_num(m['a'], 1)}% to {_num(m['b'], 1)}% ({'+' if m['s'] == '+' else '−'}{_num(m['d'], 1)} pts), based on recent purchases and sales.",
    ),
    (
        _rx(rf"^Le retard moyen de livraison est passé de (?P<a>{N}) à (?P<b>{N}) jours ; le taux de livraison à l'heure est passé de (?P<c>{N})\s?% à (?P<d>{N})\s?%\.$"),
        lambda m: f"The average delivery delay went from {_num(m['a'], 1)} to {_num(m['b'], 1)} days; the on-time delivery rate went from {_num(m['c'], 0)}% to {_num(m['d'], 0)}%.",
    ),
    (
        _rx(rf"^Le chiffre d'affaires de (?P<x>.+) a baissé de (?P<p>{N})\s?% \(de (?P<a>{N}) € à (?P<b>{N}) €\) : risque de perte du client\.$"),
        lambda m: f"Revenue from {m['x']} fell by {_num(m['p'], 1)}% (from {_money(m['a'], 0)} to {_money(m['b'], 0)}): risk of losing the customer.",
    ),
    (
        _rx(rf"^Le chiffre d'affaires de (?P<x>.+) a augmenté de (?P<p>{N})\s?% \(de (?P<a>{N}) € à (?P<b>{N}) €\)\. Piste : développer cette relation\.$"),
        lambda m: f"Revenue from {m['x']} grew by {_num(m['p'], 1)}% (from {_money(m['a'], 0)} to {_money(m['b'], 0)}). Lead: develop this relationship.",
    ),
    (
        _rx(rf"^Projection basse à (?P<a>{N}) € sur 90 jours, sous le seuil déclaré de (?P<b>{N}) €\.$"),
        lambda m: f"Low projection of {_money(m['a'], 0)} over 90 days, below the declared threshold of {_money(m['b'], 0)}.",
    ),
    (
        _rx(r"^(?P<q>\S+) × (?P<i>.+?) non conforme\(s\) \((?P<n>.*)\)(?: — (?P<p>[^—]+))?\. Envisager un avoir et, si la marchandise vient d'un fournisseur, une réclamation\.$"),
        lambda m: f"{m['q']} × {'item' if m['i'] == 'article' else m['i']} non-conforming ({m['n']})" + (f" — {m['p']}" if m["p"] else "") + ". Consider a credit note and, if the goods came from a supplier, a claim.",
    ),
    (
        _rx(r"^Besoin déclaré « (?P<s>.+?) »(?: : (?P<r>.*?))?\.+ Couverture actuelle : (?P<c>aucune|une seule personne, déjà très chargée)\.(?: Charge observée : (?P<l>[\d.,]+) tâches ouvertes par personne\.)?$"),
        lambda m: f'Declared need "{m["s"]}"' + (f": {m['r']}" if m["r"] else "")
        + f". Current coverage: {'none' if m['c'] == 'aucune' else 'a single person, already very busy'}."
        + (f" Observed load: {_num(m['l'], 1)} open tasks per person." if m["l"] else ""),
    ),
    (
        _rx(rf"^Prix annoncé par la source : (?P<a>{N}) € \(non vérifié\) vs meilleur prix connu (?P<b>{N}) €\. Source : (?P<u>.+)$"),
        lambda m: f"Price stated by the source: {_money(m['a'], 2)} (unverified) vs best known price {_money(m['b'], 2)}. Source: {m['u']}",
    ),
]

# Decision Intelligence (proposed Task): the interpretation title and the
# recommended options, frozen from app.decision.engine.
OBSERVABLES = {
    "la marge": "margin",
    "les délais de livraison": "delivery times",
    "le chiffre d'affaires client": "customer revenue",
    "les messages fournisseur sans réponse": "unanswered supplier messages",
    "les messages client sans réponse": "unanswered customer messages",
    "les devis client en attente de réponse": "customer quotes awaiting an answer",
}
_OBS = "|".join(re.escape(k) for k in OBSERVABLES)
INTERPRETATION_TITLES: list[Rule] = [
    (_rx(rf"^(?P<e>.+) — écart défavorable sur (?P<o>{_OBS})$"), lambda m: f"{m['e']} — unfavourable deviation in {OBSERVABLES[m['o']]}"),
    (_rx(rf"^(?P<e>.+) — amélioration sur (?P<o>{_OBS})$"), lambda m: f"{m['e']} — improvement in {OBSERVABLES[m['o']]}"),
    (_rx(rf"^(?P<e>.+) — anomalie sur (?P<o>{_OBS}) à surveiller$"), lambda m: f"{m['e']} — anomaly in {OBSERVABLES[m['o']]} to watch"),
    (_rx(rf"^(?P<e>.+) — anomalie détectée sur (?P<o>{_OBS})$"), lambda m: f"{m['e']} — anomaly detected in {OBSERVABLES[m['o']]}"),
]
OPTION_LABELS = {
    "Renégocier les prix ou les conditions directement avec {e}": "Renegotiate prices or terms directly with {e}",
    "Rechercher un fournisseur alternatif pour le ou les produits concernés": "Look for an alternative supplier for the products concerned",
    "Contacter {e} pour comprendre la cause du problème": "Contact {e} to understand the cause of the problem",
    "Proposer une offre de fidélisation ou des conditions ajustées à {e}": "Offer {e} a loyalty offer or adjusted terms",
    "Revoir la politique de prix ou la structure de coûts du produit concerné": "Review the pricing policy or cost structure of the product concerned",
    "Investiguer directement le facteur de coût ou de revenu en cause": "Investigate the cost or revenue driver involved directly",
    "Engager {e} pour développer la relation (vente additionnelle ou croisée)": "Engage {e} to grow the relationship (upsell or cross-sell)",
    "Proposer un contrat plus long ou à plus fort volume pour sécuriser la croissance": "Offer a longer or higher-volume contract to secure the growth",
    "Formaliser durablement les conditions améliorées avec {e}": "Lock in the improved terms with {e} for the long term",
    "Explorer une augmentation de volume avec {e} vu la performance actuelle": "Explore higher volumes with {e} given current performance",
    "Identifier ce qui explique l'amélioration pour le reproduire ailleurs": "Identify what explains the improvement to replicate it elsewhere",
    "Renforcer l'approche actuelle de prix ou de coûts": "Reinforce the current pricing or cost approach",
}
REASONING = (
    "Ces deux leviers combinent une action directe sur {e} et une mesure de réduction du risque, sans attendre — l'option la plus prudente à ce stade.",
    "These two levers combine direct action on {e} with a risk-reducing measure, without waiting — the most prudent option at this stage.",
)


def _apply(rules: list[Rule], text: str | None) -> str | None:
    if text is None:
        return None
    for pattern, build in rules:
        m = pattern.match(text)
        if m:
            return build(m)
    return None


def _decision_task(title: str, description: str | None) -> dict | None:
    m = re.match(r"^(?P<e>.+?) — ", title)
    en_title = _apply(INTERPRETATION_TITLES, title)
    d = re.match(r"^Recommended: (?P<c>.+?)\n\n(?P<r>.+)$", description or "", re.S)
    if not (m and en_title and d):
        return None
    entity = m["e"]
    parts = []
    for part in d["c"].split(" + "):
        match = next((en for fr, en in OPTION_LABELS.items() if fr.format(e=entity) == part), None)
        if match is None:
            return None
        parts.append(match.format(e=entity))
    reasoning_fr, reasoning_en = REASONING
    if d["r"] != reasoning_fr.format(e=entity):
        return None
    fr = {"title": title, "description": f"Recommandation : {d['c']}\n\n{d['r']}"}
    en = {"title": en_title, "description": f"Recommended: {' + '.join(parts)}\n\n{reasoning_en.format(e=entity)}"}
    return {"fr": fr, "en": en}


def _risk_like(title: str, description: str | None) -> dict | None:
    en_title = _apply(TITLE_RULES, title)
    if en_title is None:
        return None
    en_description = _apply(DESCRIPTION_RULES, description) if description else None
    if description and en_description is None:
        return None
    return {"fr": {"title": title, "description": description}, "en": {"title": en_title, "description": en_description}}


def _task(title: str, description: str | None) -> dict | None:
    m = re.match(r"^À examiner : (?P<x>.+)$", title, re.S)
    if m:
        inner_title = _apply(TITLE_RULES, m["x"])
        body = re.match(r"^(?P<x>.+) À examiner, puis décider de la suite\.$", description or "", re.S)
        if inner_title is None or body is None:
            return None
        inner = body["x"]
        en_body = _apply(DESCRIPTION_RULES, inner) or _apply(TITLE_RULES, inner)
        if en_body is None:
            return None
        return {
            "fr": {"title": title, "description": description},
            "en": {"title": f"Review: {inner_title}", "description": f"{en_body} To review, then decide what to do next."},
        }
    m = re.match(r"^Valider l'avoir (?P<n>\S+)(?: — (?P<c>.+?))?(?: : (?P<a>" + N + r") €)?$", title)
    if m and description and description.startswith("Le client a accepté cet avoir."):
        en = f"Validate credit note {m['n']}" + (f" — {m['c']}" if m["c"] else "") + (f": {_money(m['a'], 2)}" if m["a"] else "")
        return {
            "fr": {"title": title, "description": description},
            "en": {"title": en, "description": "The customer accepted this credit note. Once validated, it can be applied to their account (reducing their invoice, or refunding any overpayment)."},
        }
    m = re.match(r"^Avoir (?P<n>\S+) refusé(?: par (?P<c>.+?))? : décider de la suite$", title)
    if m and description and description.startswith("Le client a refusé l'avoir proposé."):
        en = f"Credit note {m['n']} rejected" + (f" by {m['c']}" if m["c"] else "") + ": decide what to do next"
        return {
            "fr": {"title": title, "description": description},
            "en": {"title": en, "description": "The customer rejected the proposed credit note. Options: offer another amount, a replacement, or close the claim."},
        }
    m = re.match(r"^Valider l'envoi : (?P<s>.+)$", title, re.S)
    body = re.match(r"^À : (?P<t>[^\n]*)(?P<rest>\n\n.*)?$", description or "", re.S)
    if m and body:
        subject = "(no subject)" if m["s"] == "(sans objet)" else m["s"]
        return {
            "fr": {"title": title, "description": description},
            "en": {"title": f"Approve sending: {subject}", "description": f"To: {body['t']}{body['rest'] or ''}"},
        }
    m = re.match(r"^Review (?P<k>supplier|product) (?P<x>.+)$", title)
    q = re.match(r'^Requested via Ask AI: "(?P<q>.*)"$', description or "", re.S)
    if m and q:
        kind = "le fournisseur" if m["k"] == "supplier" else "le produit"
        return {
            "fr": {"title": f"Examiner {kind} {m['x']}", "description": f"Demandé via l'assistant IA : « {q['q']} »"},
            "en": {"title": title, "description": f'Requested via the AI assistant: "{q["q"]}"'},
        }
    return _decision_task(title, description) or _risk_like(title, description)


def _backfill(conn, table: str, build: Callable[[str, str | None], dict | None]) -> None:
    t = sa.table(table, sa.column("id"), sa.column("title"), sa.column("description"), sa.column("i18n", sa.JSON))
    for row in conn.execute(sa.select(t.c.id, t.c.title, t.c.description).where(t.c.i18n.is_(None))).all():
        texts = build(row.title, row.description)
        if texts is None:
            continue
        values = {"i18n": texts}
        # The French column follows the French text (a former English Ask AI task).
        if texts["fr"]["title"] != row.title or texts["fr"]["description"] != row.description:
            values.update(title=texts["fr"]["title"], description=texts["fr"]["description"])
        conn.execute(sa.update(t).where(t.c.id == row.id).values(**values))


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("i18n", sa.JSON(), nullable=True))
    conn = op.get_bind()
    _backfill(conn, "risks", _risk_like)
    _backfill(conn, "opportunities", _risk_like)
    _backfill(conn, "tasks", _task)


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("i18n")

