"""A small bundled demonstration website (travel agency), used when the
company has no website configured or it cannot be reached. Every audit run
on it is recorded with mode="simulated" and shown as such -- it is never
presented as the company's real site. Its pages carry deliberate, typical
issues so the audit and the proposals have something real to analyse."""

DEMO_BASE = "https://demo.agence-voyage.example"

_HEAD = '<head><meta charset="utf-8">{title}{meta}</head>'


def _page(title: str | None, meta: str | None, body: str, lang: bool = True) -> str:
    t = f"<title>{title}</title>" if title is not None else ""
    m = f'<meta name="description" content="{meta}">' if meta is not None else ""
    lang_attr = ' lang="fr"' if lang else ""
    return f"<!doctype html><html{lang_attr}>{_HEAD.format(title=t, meta=m)}<body>{body}</body></html>"


_NAV = '<nav><a href="/">Accueil</a> <a href="/sejours">Séjours</a> <a href="/seminaires">Séminaires</a> <a href="/contact">Contact</a> <a href="/blog/partir-en-groupe">Blog</a></nav>'

DEMO_PAGES: dict[str, str] = {
    "/": _page(
        "Accueil",
        None,
        _NAV + "<h1>Voyages sur mesure pour groupes et entreprises</h1>"
        "<p>Nous organisons des séjours, séminaires et voyages de groupe en Europe depuis 15 ans. Hôtels sélectionnés, transferts, activités.</p>"
        '<img src="/img/hero.jpg"><img src="/img/team.jpg" alt="Notre équipe">',
    ),
    "/sejours": _page(
        "Séjours de groupe en Europe — séjours tout compris, hôtels, transferts et activités pour vos groupes",
        "Séjours de groupe.",
        _NAV + "<h1>Nos séjours</h1><h1>Destinations</h1><p>Italie, Espagne, Portugal, Grèce.</p>" + '<img src="/img/italie.jpg">' * 3,
    ),
    "/seminaires": _page(
        "Séminaires d'entreprise | Agence",
        "Organisation de séminaires d'entreprise clés en main : lieux, hébergement, transport et animations pour vos équipes, en France et en Europe.",
        _NAV + "<h1>Séminaires d'entreprise</h1><p>" + "Des séminaires pensés pour vos équipes, du brief à l'évaluation. " * 30 + "</p>",
    ),
    "/contact": _page("Contact", None, _NAV + "<p>Écrivez-nous.</p>", lang=False),
    "/blog/partir-en-groupe": _page(
        "Accueil",
        "Conseils pour organiser un voyage de groupe.",
        _NAV + "<h2>Partir en groupe : nos conseils</h2><p>Réserver tôt, choisir un hébergement adapté, prévoir les transferts.</p>",
    ),
}
