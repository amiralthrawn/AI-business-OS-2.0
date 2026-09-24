"""Website intelligence (V2.1, brain/website_intelligence.md):

    current site -> limited crawl -> SEO analysis -> issues (what / why / change)
    -> proposed changes with a before/after diff -> human approval (V1 HITL)
    -> "ready to apply"

Deliberately small: at most MAX_PAGES same-domain pages, robots.txt
respected, standard-library HTML parsing, no JavaScript rendering, no
industrial crawler. The real site is NEVER modified in this MVP -- there is
no CMS connector, so an approved change is marked ready to apply by a human.
Every run records its mode: "real" (the company's site was fetched) or
"simulated" (the bundled demo site, shown as such).
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from app.actions.service import ActionsService
from app.ai.llm import DeterministicLLMClient, LLMClient
from app.core.entities import AIRun, Company, RelatedEntityType, Task, TaskStatus, WebsiteChangeProposal
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.website.demo_site import DEMO_BASE, DEMO_PAGES

MAX_PAGES = 20
APPLY_ACTION = "apply_website_change"
WEBSITE_DOMAIN = "website"  # approval domain: director only
WEBSITE_AUDITED = "WebsiteAudited"
WEBSITE_CHANGE_APPROVED = "WebsiteChangeApproved"


class WebsiteError(ValueError):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    seconds: float
    size: int


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


class HttpFetcher:
    def __init__(self) -> None:
        import httpx

        self.client = httpx.Client(timeout=8.0, follow_redirects=True, headers={"User-Agent": "AIBusinessOS-SiteAudit/0.1 (+analyse interne)"})

    def fetch(self, url: str) -> FetchResult:
        start = time.perf_counter()
        response = self.client.get(url)
        text = response.text if "html" in response.headers.get("content-type", "") else ""
        return FetchResult(str(response.url), response.status_code, text, time.perf_counter() - start, len(response.content))


class DemoFetcher:
    """Serves the bundled demo site (simulated mode)."""

    def fetch(self, url: str) -> FetchResult:
        path = urlparse(url).path or "/"
        html = DEMO_PAGES.get(path.rstrip("/") or "/", DEMO_PAGES.get(path))
        if html is None:
            return FetchResult(url, 404, "", 0.05, 0)
        return FetchResult(url, 200, html, 0.12 if path != "/sejours" else 2.3, len(html.encode()))


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta_description: str | None = None
        self.canonical: str | None = None
        self.lang: str | None = None
        self.h1: list[str] = []
        self.images = 0
        self.images_without_alt = 0
        self.links: list[str] = []
        self.words = 0
        self._in: str | None = None
        self._buf = ""
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in, self._buf = "title", ""
        elif tag == "h1":
            self._in, self._buf = "h1", ""
        elif tag == "meta" and (a.get("name") or "").lower() == "description":
            self.meta_description = a.get("content")
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        elif tag == "img":
            self.images += 1
            if not (a.get("alt") or "").strip():
                self.images_without_alt += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = max(0, self._skip - 1)
        if tag == self._in == "title":
            self.title = self._buf.strip()
            self._in = None
        elif tag == self._in == "h1":
            self.h1.append(self._buf.strip())
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf += data
        if not self._skip:
            self.words += len(data.split())


@dataclass
class PageReport:
    url: str
    status: int
    seconds: float
    size: int
    title: str | None
    meta_description: str | None
    h1: list[str]
    images: int
    images_without_alt: int
    words: int
    lang: str | None
    canonical: str | None
    issues: list[dict] = field(default_factory=list)


def _issue(code: str, severity: str, what: str, why: str, change: str) -> dict:
    return {"code": code, "severity": severity, "what": what, "why": why, "change": change}


def _analyse(page: PageReport, duplicate_titles: set[str]) -> list[dict]:
    issues = []
    if page.status >= 400:
        return [_issue("http_error", "high", f"La page répond {page.status}.", "Une page en erreur n'est ni indexée ni utile aux visiteurs.", "Corriger ou rediriger l'URL.")]
    t = page.title or ""
    if not t:
        issues.append(_issue("title_missing", "high", "Titre absent.", "Le titre est le premier élément affiché par les moteurs de recherche.", "Ajouter un titre de 30 à 60 caractères décrivant la page."))
    elif len(t) < 30:
        issues.append(_issue("title_short", "medium", f"Titre trop court ({len(t)} car.) : « {t} ».", "Un titre vague ne dit ni le sujet ni l'offre.", "Allonger le titre avec le sujet précis et la marque."))
    elif len(t) > 60:
        issues.append(_issue("title_long", "low", f"Titre trop long ({len(t)} car.).", "Au-delà de ~60 caractères, le titre est tronqué dans les résultats.", "Raccourcir en gardant les mots importants au début."))
    if t and t in duplicate_titles:
        issues.append(_issue("title_duplicate", "medium", f"Titre identique à une autre page : « {t} ».", "Deux pages au même titre se concurrencent et sont mal distinguées.", "Donner à chaque page un titre unique."))
    d = page.meta_description or ""
    if not d:
        issues.append(_issue("meta_missing", "medium", "Méta-description absente.", "Le moteur choisit alors un extrait au hasard, souvent peu engageant.", "Rédiger 70 à 160 caractères résumant la page et incitant au clic."))
    elif len(d) < 70:
        issues.append(_issue("meta_short", "low", f"Méta-description trop courte ({len(d)} car.).", "Un résumé trop court exploite mal l'espace affiché.", "L'enrichir (70–160 caractères)."))
    if not page.h1:
        issues.append(_issue("h1_missing", "medium", "Aucun titre H1.", "Le H1 indique le sujet principal de la page.", "Ajouter un H1 unique."))
    elif len(page.h1) > 1:
        issues.append(_issue("h1_multiple", "low", f"{len(page.h1)} titres H1.", "Plusieurs H1 brouillent la hiérarchie du contenu.", "Garder un seul H1, passer les autres en H2."))
    if page.images_without_alt:
        issues.append(_issue("img_alt", "low", f"{page.images_without_alt} image(s) sans texte alternatif.", "Accessibilité et référencement des images.", "Décrire chaque image dans l'attribut alt."))
    if not page.lang:
        issues.append(_issue("lang_missing", "low", "Langue de la page non déclarée.", "Les moteurs et lecteurs d'écran s'appuient sur la langue déclarée.", 'Ajouter lang="fr" sur la balise html.'))
    if page.words < 60:
        issues.append(_issue("thin_content", "medium", f"Contenu très court ({page.words} mots).", "Une page quasi vide a peu de chances d'être bien positionnée.", "Ajouter un contenu utile décrivant l'offre."))
    if page.seconds > 1.5:
        issues.append(_issue("slow", "medium", f"Réponse lente ({page.seconds:.1f} s).", "La lenteur dégrade l'expérience et le référencement.", "Alléger les images, activer le cache/compression."))
    return issues


def _propose(page: PageReport, company_name: str, llm: LLMClient | None) -> list[tuple[str, str | None, str, str]]:
    """Deterministic proposals from the page's own content (its H1, its
    text); an LLM may only rephrase them when configured."""

    codes = {i["code"] for i in page.issues}
    proposals = []
    subject = (page.h1[0] if page.h1 else None) or (page.title if page.title and page.title != "Accueil" else None) or urlparse(page.url).path.strip("/").replace("-", " ").capitalize() or "Accueil"
    if codes & {"title_missing", "title_short", "title_long", "title_duplicate"}:
        suffix = f" | {company_name}" if len(company_name) <= 30 else ""
        proposed = f"{subject}{suffix}"
        if len(proposed) > 60:
            # Cut the subject on a word boundary so subject + brand fit in 60 characters.
            room = 60 - len(suffix) - 1
            proposed = subject[:room].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…" + suffix
        proposals.append(("title", page.title, proposed, "Titre unique, 30–60 caractères, sujet de la page d'abord puis la marque."))
    if codes & {"meta_missing", "meta_short"}:
        proposed = f"{subject} : découvrez notre offre avec {company_name}. Devis gratuit et accompagnement personnalisé."[:158]
        proposals.append(("meta_description", page.meta_description, proposed, "Résumé de 70–160 caractères avec le sujet et une incitation à l'action."))
    if "h1_multiple" in codes:
        proposals.append(("h1", " / ".join(page.h1), page.h1[0], "Un seul H1 (le premier) ; les autres deviennent des H2."))
    if llm is not None and not isinstance(llm, DeterministicLLMClient):
        polished = []
        for field_name, current, proposed, rationale in proposals:
            try:
                text = llm.complete(system_prompt="Reformule ce texte SEO en français, même sens, sans ajouter d'information, même longueur maximale. Réponds uniquement par le texte.", user_prompt=proposed).strip()
                polished.append((field_name, current, text or proposed, rationale))
            except Exception:
                polished.append((field_name, current, proposed, rationale))
        return polished
    return proposals


def _allowed_by_robots(fetcher: Fetcher, base: str) -> bool:
    try:
        robots = fetcher.fetch(urljoin(base, "/robots.txt"))
    except Exception:
        return True
    if robots.status != 200:
        return True
    agent_all, disallow_all = False, False
    for line in robots.html.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            agent_all = value == "*"
        elif key == "disallow" and agent_all and value == "/":
            disallow_all = True
    return not disallow_all


def _step(run: AIRun, label: str, status: str = "done", detail: str | None = None) -> None:
    run.steps = [*run.steps, {"label": label, "status": status, "detail": detail, "at": datetime.now(timezone.utc).isoformat()}]


def audit_website(session: Session, event_bus: EventBus | None, company: Company, *, fetcher: Fetcher | None = None, llm: LLMClient | None = None) -> AIRun:
    mode, base = "simulated", DEMO_BASE
    active: Fetcher = DemoFetcher()
    run = AIRun(company_id=company.id, kind="website_audit", mode="simulated", status="running", started_at=datetime.now(timezone.utc), steps=[], result={}, subject_type="company", subject_id=company.id)
    session.add(run)
    session.flush()
    if company.website_url:
        real = fetcher or HttpFetcher()
        try:
            probe = real.fetch(company.website_url)
            if probe.status < 400 and probe.html:
                mode, base, active = "real", probe.url, real
                _step(run, f"Site joint : {company.website_url}")
            else:
                _step(run, f"Site {company.website_url} injoignable (HTTP {probe.status})", "failed", "Analyse du site de démonstration à la place.")
        except Exception as exc:
            _step(run, f"Site {company.website_url} injoignable", "failed", f"{type(exc).__name__} — analyse du site de démonstration à la place.")
    else:
        _step(run, "Aucun site configuré", "skipped", "Analyse du site de démonstration intégré (simulation).")
    run.mode, run.target = mode, base

    if mode == "real" and not _allowed_by_robots(active, base):
        _step(run, "robots.txt interdit l'exploration", "failed")
        run.status, run.finished_at = "failed", datetime.now(timezone.utc)
        session.commit()
        return run

    host = urlparse(base).netloc
    queue, seen, pages = [base], set(), []
    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0).split("#")[0]
        if url in seen:
            continue
        seen.add(url)
        try:
            result = active.fetch(url)
        except Exception:
            continue
        parser = _PageParser()
        parser.feed(result.html or "")
        pages.append(PageReport(url, result.status, round(result.seconds, 2), result.size, parser.title, parser.meta_description, parser.h1, parser.images, parser.images_without_alt, parser.words, parser.lang, parser.canonical))
        for href in parser.links:
            absolute = urljoin(url, href)
            if urlparse(absolute).netloc == host and absolute not in seen:
                queue.append(absolute)
    _step(run, "Exploration des pages", detail=f"{len(pages)} page(s) analysée(s) (maximum {MAX_PAGES})")

    titles = [p.title for p in pages if p.title]
    duplicates = {t for t in titles if titles.count(t) > 1}
    for page in pages:
        page.issues = _analyse(page, duplicates)
    issues = [i | {"url": p.url} for p in pages for i in p.issues]
    _step(run, "Métadonnées, titres et contenus analysés")
    _step(run, "Performance mesurée", detail=f"temps de réponse moyen {sum(p.seconds for p in pages) / max(len(pages), 1):.2f} s")
    _step(run, f"{len(issues)} problème(s) détecté(s)")

    created = 0
    for page in pages:
        for field_name, current, proposed, rationale in _propose(page, company.name, llm):
            session.add(WebsiteChangeProposal(company_id=company.id, run_id=run.id, page_url=page.url, field=field_name, current_value=current, proposed_value=proposed, rationale=rationale, generated_by="rules+llm" if (llm is not None and not isinstance(llm, DeterministicLLMClient)) else "rules"))
            created += 1
    _step(run, f"{created} modification(s) proposée(s)", detail="Soumises à validation avant toute application.")

    severity = {"high": 0, "medium": 1, "low": 2}
    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in severity}
    top = max({i["code"] for i in issues}, key=lambda c: sum(1 for i in issues if i["code"] == c), default=None)
    run.result = {
        "pages": [p.__dict__ for p in pages],
        "issues": sorted(issues, key=lambda i: severity[i["severity"]]),
        "counts": counts,
        "top_issue": top,
        "score_note": "Pas de score unique : les problèmes sont listés par gravité.",
    }
    run.status, run.finished_at = "done", datetime.now(timezone.utc)
    session.commit()
    if event_bus is not None:
        event_bus.publish(BusinessEvent(event_type=WEBSITE_AUDITED, source="website", payload={"run_id": str(run.id), "mode": mode, "issues": len(issues), "title": f"Audit du site ({mode})"}))
    return run


def submit_proposal(session: Session, event_bus: EventBus, proposal: WebsiteChangeProposal) -> Task:
    if proposal.status not in {"proposed", "rejected"}:
        raise WebsiteError("Proposition déjà soumise ou traitée")
    task = ActionsService(session, event_bus).propose_task(
        company_id=proposal.company_id,
        title=f"Modifier le site — {proposal.field} de {urlparse(proposal.page_url).path or '/'}",
        description=f"Actuel : {proposal.current_value or '(vide)'}\nProposé : {proposal.proposed_value}\n\n{proposal.rationale}",
        related_entity_type=RelatedEntityType.COMPANY,
        related_entity_id=proposal.company_id,
        pending_action=APPLY_ACTION,
        agent="website",
    )
    task.domain = WEBSITE_DOMAIN
    task.category = "website_change"
    task.action_payload = {"proposal_id": str(proposal.id)}
    proposal.status, proposal.task_id = "pending_validation", task.id
    session.commit()
    return task


def finalize_website_change(session: Session, event_bus: EventBus, task: Task) -> Task:
    """ActionExecutor branch after approval: the change is APPROVED and ready
    to apply. No CMS connector exists -- nothing is written to the site."""

    proposal = session.get(WebsiteChangeProposal, uuid.UUID((task.action_payload or {})["proposal_id"]))
    if proposal is None:
        raise WebsiteError("Proposition introuvable")
    proposal.status = "approved"
    task.status = TaskStatus.EXECUTED
    session.commit()
    event_bus.publish(BusinessEvent(event_type=WEBSITE_CHANGE_APPROVED, source="website", payload={"proposal_id": str(proposal.id), "page": proposal.page_url, "field": proposal.field, "title": "Modification du site approuvée (application manuelle)"}))
    return task


def on_change_rejected(session: Session, task: Task) -> None:
    proposal_id = (task.action_payload or {}).get("proposal_id")
    proposal = session.get(WebsiteChangeProposal, uuid.UUID(proposal_id)) if proposal_id else None
    if proposal is not None:
        proposal.status = "rejected"
        session.commit()
