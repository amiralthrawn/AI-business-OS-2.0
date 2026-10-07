"""People (V2.1, brain/people.md): a small employee layer connecting

    EMPLOYEE -> COST -> TASKS -> CONTRIBUTION -> BUSINESS IMPACT

plus skills gaps, hiring needs and candidates from inbound emails. Not an
HR system, not payroll, not an ATS. Every number keeps its basis; a
contribution is always "estimated and partial", never a verdict on a person,
and there is no ranking of employees. Sensitive changes (promotion, raise)
are only ever *proposed* -- a director applies them through the V1 HITL.
"""

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.i18n import use_locale
from app.core.i18n import both, colon, money, num, tx
from app.actions.service import ActionsService
from app.ai.llm import DeterministicLLMClient, LLMClient
from app.core.analytics import _as_aware_utc
from app.core.entities import (
    BusinessContext,
    Candidate,
    CommercialDocument,
    Communication,
    DocumentKind,
    Employee,
    EmployeeCostItem,
    Opportunity,
    OpportunityStatus,
    RelatedEntityType,
    SkillNeed,
    Task,
    TaskStatus,
    ValueBasis,
)
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent
from app.objects.links import create_link

HR_DECISION_ACTION = "apply_hr_decision"
PEOPLE_DOMAIN = "people"  # approval domain: director only (app.access.policy)

EMPLOYEE_DECISION_APPLIED = "EmployeeDecisionApplied"
EMPLOYEE_COST_CHANGED = "EmployeeCostChanged"
SKILL_GAP_DETECTED = "SkillGapDetected"
CANDIDATE_CREATED = "CandidateCreated"

# Employer charges as a share of gross salary when none is recorded --
# BENCHMARK ranges by country, never presented as the company's real figure.
EMPLOYER_CHARGE_BENCHMARKS: dict[str, tuple[float, float]] = {
    "FR": (0.40, 0.47),
    "BE": (0.25, 0.32),
    "DE": (0.19, 0.22),
    "CH": (0.13, 0.17),
}
GENERIC_EMPLOYER_CHARGES = (0.20, 0.47)

_RANK = {"unknown": 0, "simulated": 1, "benchmark": 1, "estimated": 2, "declared": 3, "observed": 4}
_CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
COST_KINDS: dict[str, tuple[str, str]] = {  # (French, English)
    "salary": ("Salaire brut annuel", "Annual gross salary"),
    "employer_charges": ("Charges patronales", "Employer charges"),
    "software": ("Logiciels & licences", "Software & licences"),
    "equipment": ("Matériel", "Equipment"),
    "benefits": ("Avantages", "Benefits"),
    "other": ("Autres coûts", "Other costs"),
}
COST_KIND_LABELS = {kind: labels[0] for kind, labels in COST_KINDS.items()}  # French, as stored


def cost_kind_label(kind: str) -> str:
    return tx(*COST_KINDS[kind]) if kind in COST_KINDS else kind


def _cost_line_label(kind: str, stored: str | None) -> str:
    """A label someone typed is shown as written; the default one of its kind
    (stored in French) follows the interface language."""

    return stored if stored and stored != COST_KIND_LABELS.get(kind) else cost_kind_label(kind)


def _cost_source(source: str | None) -> str | None:
    m = re.match(r"^Décision validée \((?P<id>[^)]+)\)$", source or "")
    return tx(source, f"Approved decision ({m['id']})") if m else source


class PeopleError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context(session: Session, company_id: uuid.UUID) -> BusinessContext | None:
    return session.query(BusinessContext).filter_by(company_id=company_id).first()


# --- Cost ------------------------------------------------------------------------------


@dataclass
class CostLine:
    kind: str
    label: str
    annual_min: float
    annual_max: float
    basis: str
    confidence: str
    source: str | None
    computed: bool = False  # True for a benchmark line the system added


@dataclass
class EmployeeCost:
    lines: list[CostLine]
    total_min: float
    total_max: float
    basis: str  # the weakest basis among the components
    confidence: str
    explanation: str
    missing: list[str] = field(default_factory=list)


def employee_cost(session: Session, employee: Employee) -> EmployeeCost:
    lines = [
        CostLine(i.kind, _cost_line_label(i.kind, i.label), i.annual_min, i.annual_max, i.basis.value, i.confidence, _cost_source(i.source))
        for i in employee.cost_items
    ]
    missing: list[str] = []
    salary = next((line for line in lines if line.kind == "salary"), None)
    if salary is None:
        missing.append(tx("Salaire non renseigné : coût total non calculable.", "Salary not provided: total cost cannot be computed."))
    elif not any(line.kind == "employer_charges" for line in lines):
        ctx = _context(session, employee.company_id)
        country = (ctx.country if ctx else None) or ""
        lo, hi = EMPLOYER_CHARGE_BENCHMARKS.get(country.upper(), GENERIC_EMPLOYER_CHARGES)
        lines.append(
            CostLine(
                "employer_charges", tx("Charges patronales (référence)", "Employer charges (reference)"), round(salary.annual_min * lo), round(salary.annual_max * hi),
                ValueBasis.BENCHMARK.value, "medium" if country.upper() in EMPLOYER_CHARGE_BENCHMARKS else "low",
                tx(f"Référence {country or 'générique'} {lo:.0%}–{hi:.0%} du brut", f"{country or 'Generic'} reference {lo:.0%}–{hi:.0%} of gross"), computed=True,
            )
        )  # fmt: skip
    for kind in ("software", "equipment"):
        if not any(line.kind == kind for line in lines):
            missing.append(tx(f"{cost_kind_label(kind)} non renseigné(s).", f"{cost_kind_label(kind)} not provided."))

    if not lines or salary is None:
        return EmployeeCost(lines, 0.0, 0.0, "unknown", "none", tx("Données insuffisantes pour estimer le coût.", "Insufficient data to estimate the cost."), missing)
    weakest = min(lines, key=lambda line: _RANK.get(line.basis, 0)).basis
    confidence = min((line.confidence for line in lines), key=lambda c: _CONF_RANK.get(c, 0))
    if missing and confidence == "high":
        confidence = "medium"
    total_min, total_max = sum(line.annual_min for line in lines), sum(line.annual_max for line in lines)
    explanation = (
        tx("Coût complet calculé à partir de montants tous réels.", "Full cost computed from actual amounts only.")
        if weakest == "observed"
        else tx("Estimation : au moins une composante est déclarée, estimée, issue d'une référence ou simulée.", "Estimate: at least one component is declared, estimated, from a reference or simulated.")
    )
    return EmployeeCost(lines, round(total_min), round(total_max), weakest, confidence, explanation, missing)


def add_cost_item(session: Session, event_bus: EventBus | None, employee: Employee, *, kind: str, annual_min: float, annual_max: float | None, basis: ValueBasis, label: str | None = None, confidence: str = "medium", source: str | None = None) -> EmployeeCostItem:
    if kind not in COST_KIND_LABELS:
        raise PeopleError(tx(f"Type de coût inconnu : {kind}", f"Unknown cost type: {kind}"))
    annual_max = annual_min if annual_max is None else annual_max
    if annual_max < annual_min:
        raise PeopleError(tx("Le maximum doit être supérieur ou égal au minimum", "The maximum must be greater than or equal to the minimum"))
    before = employee_cost(session, employee)
    item = EmployeeCostItem(kind=kind, label=label, annual_min=annual_min, annual_max=annual_max, basis=basis, confidence=confidence, source=source)
    employee.cost_items.append(item)
    session.commit()
    _publish_cost_change(session, event_bus, employee, before)
    return item


def _publish_cost_change(session: Session, event_bus: EventBus | None, employee: Employee, before: EmployeeCost) -> None:
    """Employee cost increase -> Business Event (subject: the employee), the
    same Event Log the Snapshot/timeline/Activity already read."""

    if event_bus is None:
        return
    after = employee_cost(session, employee)
    if (after.total_min, after.total_max) != (before.total_min, before.total_max):
        event_bus.publish(
            BusinessEvent(
                event_type=EMPLOYEE_COST_CHANGED,
                source="people",
                payload={
                    "subject_type": "employee", "subject_id": str(employee.id),
                    "before": [before.total_min, before.total_max], "after": [after.total_min, after.total_max], "basis": after.basis,
                },
            )
        )  # fmt: skip


# --- Tasks & contribution --------------------------------------------------------------


@dataclass
class ContributionComponent:
    label: str
    value: str
    basis: str
    detail: str | None = None


@dataclass
class Contribution:
    components: list[ContributionComponent]
    attributable_margin_min: float | None
    attributable_margin_max: float | None
    cost_coverage: str | None  # "attributable margin covers ~X-Y % of the cost", when both are known
    confidence: str
    sufficient: bool
    statement: str


def task_summary(session: Session, employee: Employee, days: int = 90) -> dict:
    since = _now() - timedelta(days=days)
    tasks = session.query(Task).filter(Task.assignee_employee_id == employee.id).all()
    done = [t for t in tasks if t.status in {TaskStatus.DONE, TaskStatus.EXECUTED} and _as_aware_utc(t.updated_at) >= since]
    open_ = [t for t in tasks if t.status in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}]
    overdue = [t for t in open_ if t.due_at is not None and _as_aware_utc(t.due_at) < _now()]
    critical = [t for t in done if t.requires_decision]
    return {"done_recent": len(done), "open": len(open_), "overdue": len(overdue), "critical_done": len(critical), "window_days": days, "total": len(tasks)}


def _eur(v: float) -> str:
    return money(v, 0)


def _span_eur(lo: float, hi: float) -> str:
    return _eur(lo) if abs(hi - lo) < 0.5 else f"{_eur(lo)}–{_eur(hi)}"


def _span_pct(lo: float, hi: float) -> str:
    return f"{lo:.0%}" if round(lo, 2) == round(hi, 2) else f"{lo:.0%}–{hi:.0%}"


def estimate_contribution(session: Session, employee: Employee, cost: EmployeeCost | None = None) -> Contribution:
    """An *estimated, partial* business contribution from what is really
    measurable: work done (tasks) and the margin of the deals this person
    owns. Never a score, never a ranking; says "insufficient" when it is."""

    from app.transactions.margin import compute_document_margin

    tasks = task_summary(session, employee)
    components = [
        ContributionComponent(tx("Tâches terminées (90 j)", "Tasks completed (90 d)"), str(tasks["done_recent"]), "observed", tx(f"dont {tasks['critical_done']} à décision", f"of which {tasks['critical_done']} requiring a decision")),
        ContributionComponent(tx("Tâches ouvertes / en retard", "Open / overdue tasks"), f"{tasks['open']} / {tasks['overdue']}", "observed"),
    ]
    margin_min = margin_max = None
    if employee.user_id:
        orders = (
            session.query(CommercialDocument)
            .filter(CommercialDocument.owner_user_id == employee.user_id, CommercialDocument.kind == DocumentKind.CUSTOMER_ORDER, CommercialDocument.status != "cancelled")
            .all()
        )
        won = session.query(CommercialDocument).filter(CommercialDocument.owner_user_id == employee.user_id, CommercialDocument.kind == DocumentKind.CUSTOMER_REQUEST, CommercialDocument.status == "won").count()
        if orders:
            views = [compute_document_margin(session, o).current for o in orders]
            margin_min, margin_max = sum(v.margin_min for v in views), sum(v.margin_max for v in views)
            bases = {v.cost_basis for v in views}
            basis = "observed" if bases == {"actual"} else "estimated"
            components.append(ContributionComponent(tx("Marge des commandes portées", "Margin of owned orders"), _span_eur(margin_min, margin_max), basis, tx(f"{len(orders)} commande(s), {won} affaire(s) gagnée(s)", f"{len(orders)} order(s), {won} deal(s) won")))
        else:
            components.append(ContributionComponent(tx("Affaires portées", "Owned deals"), tx("aucune commande", "no order"), "observed"))
    else:
        components.append(ContributionComponent(tx("Affaires portées", "Owned deals"), tx("non rattachable", "not attributable"), "unknown", tx("Aucun profil utilisateur lié à cet employé.", "No user profile linked to this employee.")))

    cost_coverage = None
    if margin_min is not None and cost and cost.total_max > 0 and cost.basis != "unknown":
        cost_coverage = _span_pct(margin_min / cost.total_max, margin_max / cost.total_min) if cost.total_min > 0 else None

    sufficient = margin_min is not None or tasks["done_recent"] >= 5
    if margin_min is not None:
        confidence = "medium" if tasks["done_recent"] >= 3 else "low"
        statement = (
            tx(f"Contribution estimée (partielle) : les affaires portées dégagent {_span_eur(margin_min, margin_max)} de marge", f"Estimated (partial) contribution: the owned deals generate {_span_eur(margin_min, margin_max)} of margin")
            + (tx(f", soit environ {cost_coverage} du coût employeur estimé", f", i.e. about {cost_coverage} of the estimated employer cost") if cost_coverage else "")
            + tx(". Le travail non commercial (support, organisation, qualité) n'est pas mesuré ici.", ". Non-sales work (support, organisation, quality) is not measured here.")
        )
    elif sufficient:
        confidence = "low"
        statement = tx("Contribution estimée à partir du travail réalisé uniquement : aucun revenu n'est rattachable à ce poste. Estimation partielle.", "Contribution estimated from the work done only: no revenue can be attributed to this position. Partial estimate.")
    else:
        confidence = "none"
        statement = tx("Données insuffisantes → estimation non fiable. Les données disponibles permettent seulement une vue partielle de la contribution.", "Insufficient data → unreliable estimate. The available data only gives a partial view of the contribution.")
    return Contribution(components, margin_min, margin_max, cost_coverage, confidence, sufficient, statement)


# --- Evolution suggestions & HITL decisions -------------------------------------------


def _norm(values: list[str]) -> set[str]:
    return {v.strip().lower() for v in values if v and v.strip()}


def _covers(skills: set[str], need: SkillNeed) -> bool:
    keys = _norm([need.skill, *need.keywords])
    return any(k in s or s in k for k in keys for s in skills)


def evolution_suggestions(session: Session, employee: Employee) -> list[dict]:
    """Deterministic: an employee whose skills cover an uncovered declared
    need and who has shown sustained work is *suggested* for that scope.
    A suggestion to review -- never a decision."""

    if employee.status != "active":
        return []
    skills = _norm(employee.skills)
    tasks = task_summary(session, employee)
    tenure_years = ((_now() - _as_aware_utc(employee.hired_at)).days / 365) if employee.hired_at else 0
    suggestions = []
    for need in session.query(SkillNeed).filter_by(company_id=employee.company_id).all():
        if not _covers(skills, need):
            continue
        others = [e for e in _active(session, employee.company_id) if e.id != employee.id and _covers(_norm(e.skills), need)]
        if others:
            continue
        reasons = [tx(f"compétence « {need.skill} » déclarée comme besoin ({need.priority})", f'skill "{need.skill}" declared as a need ({need.priority})')]
        if tenure_years >= 1:
            reasons.append(tx(f"{tenure_years:.1f} an(s) d'ancienneté", f"{tenure_years:.1f} year(s) of seniority"))
        if tasks["done_recent"] >= 3:
            reasons.append(tx(f"{tasks['done_recent']} tâches terminées sur 90 jours", f"{tasks['done_recent']} tasks completed over 90 days"))
        suggestions.append(
            {
                "kind": "evolution",
                "title": tx(f"Évolution possible vers un rôle « {need.skill} »", f'Possible move to a "{need.skill}" role'),
                "reasons": reasons,
                "confidence": "medium" if len(reasons) >= 3 else "low",
                "note": tx("Suggestion à examiner par un responsable — aucune décision automatique.", "Suggestion for a manager to review — no automatic decision."),
            }
        )
    return suggestions


def propose_decision(session: Session, event_bus: EventBus, employee: Employee, *, kind: str, rationale: str, new_job_title: str | None = None, new_salary: float | None = None) -> Task:
    """Promotion / raise / evolution / any recorded decision: a
    PENDING_VALIDATION Task in the "people" domain (director approval only),
    carrying its parameters. Nothing changes until it is approved."""

    if kind not in {"promotion", "raise", "evolution", "decision"}:
        raise PeopleError(tx("Type de décision inconnu", "Unknown decision type"))
    if kind == "promotion" and not new_job_title:
        raise PeopleError(tx("Une promotion précise le nouveau poste", "A promotion specifies the new position"))
    if kind == "raise" and not new_salary:
        raise PeopleError(tx("Une augmentation précise le nouveau salaire annuel brut", "A raise specifies the new annual gross salary"))
    labels = {"promotion": ("Promotion", "Promotion"), "raise": ("Augmentation", "Raise"), "evolution": ("Évolution", "Career move"), "decision": ("Décision", "Decision")}

    def title() -> str:
        detail = new_job_title or (tx(f"{money(new_salary, 0)} brut / an", f"{money(new_salary, 0)} gross / year") if new_salary else "")
        return f"{tx(*labels[kind])} — {employee.full_name}" + (f"{colon()} {detail}" if detail else "")

    texts = both(lambda: {"title": title(), "description": rationale})
    task = ActionsService(session, event_bus).propose_task(
        company_id=employee.company_id,
        title=texts["fr"]["title"],
        i18n=texts,
        description=rationale,
        related_entity_type=RelatedEntityType.EMPLOYEE,
        related_entity_id=employee.id,
        pending_action=HR_DECISION_ACTION,
        agent="people",
    )
    task.domain = PEOPLE_DOMAIN
    task.category = kind
    task.requires_decision = True
    task.action_payload = {"kind": kind, "new_job_title": new_job_title, "new_salary": new_salary}
    session.commit()
    return task


def finalize_hr_decision(session: Session, event_bus: EventBus, task: Task) -> Task:
    """ActionExecutor branch, run only after a director approved the Task."""

    employee = session.get(Employee, task.related_entity_id) if task.related_entity_id else None
    if employee is None:
        raise PeopleError(tx("Employé introuvable", "Employee not found"))
    payload = task.action_payload or {}
    before = employee_cost(session, employee)
    if payload.get("kind") == "promotion" and payload.get("new_job_title"):
        employee.job_title = payload["new_job_title"]
    if payload.get("kind") == "raise" and payload.get("new_salary"):
        for item in [i for i in employee.cost_items if i.kind == "salary"]:
            employee.cost_items.remove(item)
        amount = float(payload["new_salary"])
        employee.cost_items.append(EmployeeCostItem(kind="salary", label="Salaire brut annuel", annual_min=amount, annual_max=amount, basis=ValueBasis.DECLARED, confidence="high", source=f"Décision validée ({task.id})"))
        # Recomputed charges follow the new salary (benchmark lines are computed, not stored).
    task.status = TaskStatus.EXECUTED
    session.commit()
    event_bus.publish(
        BusinessEvent(
            event_type=EMPLOYEE_DECISION_APPLIED,
            source="people",
            payload={"subject_type": "employee", "subject_id": str(employee.id), "task_id": str(task.id), "kind": payload.get("kind"), "title": task.title},
        )
    )
    _publish_cost_change(session, event_bus, employee, before)
    return task


# --- Skills gap & hiring needs ---------------------------------------------------------


def _active(session: Session, company_id: uuid.UUID) -> list[Employee]:
    return session.query(Employee).filter_by(company_id=company_id, status="active").all()


def skills_gap(session: Session, company_id: uuid.UUID) -> dict:
    """Company needs (DECLARED) vs the team's skills and workload (OBSERVED
    from tasks) -> uncovered or thin needs -> hiring recommendations."""

    team = _active(session, company_id)
    open_tasks = session.query(Task).filter(Task.company_id == company_id, Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS])).count()
    load = open_tasks / len(team) if team else None
    gaps, covered = [], []
    for need in session.query(SkillNeed).filter_by(company_id=company_id).order_by(SkillNeed.created_at).all():
        holders = [e.full_name for e in team if _covers(_norm(e.skills), need)]
        entry = {
            "need_id": need.id, "skill": need.skill, "level": need.level, "priority": need.priority, "reason": need.reason,
            "expected_impact": need.expected_impact, "holders": holders, "basis": need.basis.value,
        }  # fmt: skip
        if holders and not (len(holders) == 1 and load is not None and load > 8):
            covered.append(entry)
            continue
        entry["coverage"] = tx("aucune", "none") if not holders else tx("une seule personne, déjà très chargée", "a single person, already very busy")
        # The skill and the reason are what the company declared: quoted as written.
        reason = (need.reason or "").strip().rstrip(".")
        entry["recommendation"] = {
            "profile": f"{need.skill} ({need.level})",
            "skills": [need.skill, *need.keywords][:6],
            "justification": (
                tx(f"Besoin déclaré « {need.skill} »", f'Declared need "{need.skill}"')
                + (f"{colon()} {reason}" if reason else "")
                + tx(f". Couverture actuelle : {entry['coverage']}.", f". Current coverage: {entry['coverage']}.")
                + (tx(f" Charge observée : {num(load)} tâches ouvertes par personne.", f" Observed load: {num(load)} open tasks per person.") if load is not None else "")
            ),
            "impact": need.expected_impact or tx("Non précisé", "Not specified"),
            "priority": need.priority,
            "confidence": "medium" if need.basis == ValueBasis.DECLARED else "low",
        }
        gaps.append(entry)
    return {"team_size": len(team), "open_tasks_per_person": round(load, 1) if load is not None else None, "gaps": gaps, "covered": covered}


def publish_skill_gaps(session: Session, event_bus: EventBus, company_id: uuid.UUID) -> int:
    """Missing skill -> Business Event + an Opportunity in V1 Intelligence
    ("Recruter : X"), idempotent -- the same Opportunity list, Snapshot and
    Home already show; no parallel intelligence system."""

    created = 0
    for gap in skills_gap(session, company_id)["gaps"]:
        title = f"Recruter ou former : {gap['skill']}"  # French column, also the de-duplication key
        if session.query(Opportunity.id).filter_by(company_id=company_id, title=title).first() is not None:
            continue
        texts = {}
        for locale in ("fr", "en"):
            with use_locale(locale):
                localized_gap = next(g for g in skills_gap(session, company_id)["gaps"] if g["need_id"] == gap["need_id"])
                texts[locale] = {"title": tx(title, f"Hire or train: {gap['skill']}"), "description": localized_gap["recommendation"]["justification"]}
        opportunity = Opportunity(
            company_id=company_id, title=title, description=texts["fr"]["description"], i18n=texts,
            status=OpportunityStatus.OPEN, related_entity_type=RelatedEntityType.COMPANY, related_entity_id=company_id,
        )  # fmt: skip
        session.add(opportunity)
        session.commit()
        event_bus.publish(
            BusinessEvent(
                event_type=SKILL_GAP_DETECTED,
                source="people",
                payload={"opportunity_id": str(opportunity.id), "skill": gap["skill"], "priority": gap["priority"], "title": title},
            )
        )
        created += 1
    return created


# --- Candidates --------------------------------------------------------------------------

_APPLICATION_WORDS = ("candidature", "curriculum", " cv", "postuler", "poste de", "job application", "resume")
_BASE_SKILLS = (
    "python", "sql", "excel", "power bi", "tableau", "automatisation", "automation", "data", "analyse", "comptabilité",
    "gestion de projet", "vente", "négociation", "achats", "logistique", "seo", "marketing", "anglais", "espagnol", "crm",
)  # fmt: skip


def looks_like_application(communication: Communication) -> bool:
    text = f" {communication.subject or ''} {communication.body or ''}".lower()
    return any(w in text for w in _APPLICATION_WORDS)


def extract_candidate(session: Session, event_bus: EventBus | None, communication: Communication, llm: LLMClient | None = None) -> Candidate:
    """Candidate from an application email -- by explainable rules (skills
    vocabulary = declared needs + team skills + a base list; years of
    experience; position). What the applicant wrote is DECLARED, never
    verified. Idempotent per message."""

    existing = session.query(Candidate).filter_by(communication_id=communication.id).first()
    if existing is not None:
        return existing
    text = f"{communication.subject or ''}\n{communication.body or ''}"
    lowered = text.lower()
    vocabulary = set(_BASE_SKILLS)
    for need in session.query(SkillNeed).filter_by(company_id=communication.company_id).all():
        vocabulary |= _norm([need.skill, *need.keywords])
    for employee in _active(session, communication.company_id):
        vocabulary |= _norm(employee.skills)
    skills = sorted(s for s in vocabulary if re.search(rf"(?<![\w]){re.escape(s)}(?![\w])", lowered))
    years = re.search(r"(\d{1,2})\s*(?:ans|années|years)\s*(?:d['’]\s*)?(?:expérience|experience)", lowered)
    position = re.search(r"(?:poste de|poste d['’]|candidature (?:au poste de |pour le poste de |pour |à )?|position of )\s*([^\n.,;]{3,60})", text, re.IGNORECASE)
    name = None
    if communication.contact_id:
        from app.core.entities import Contact

        contact = session.get(Contact, communication.contact_id)
        name = contact.name if contact and contact.name and "@" not in contact.name else None
    candidate = Candidate(
        company_id=communication.company_id,
        communication_id=communication.id,
        full_name=name or (communication.from_address or "Candidat").split("@")[0].replace(".", " ").title(),
        email=communication.from_address,
        applied_for=position.group(1).strip() if position else None,
        skills=skills,
        years_experience=float(years.group(1)) if years else None,
        basis=ValueBasis.SIMULATED if (communication.source or "").startswith("simulated") else ValueBasis.DECLARED,
        extracted_by="rules+llm" if (llm is not None and not isinstance(llm, DeterministicLLMClient)) else "rules",
    )
    session.add(candidate)
    session.commit()
    create_link(session, company_id=communication.company_id, source_type="communication", source_id=communication.id, target_type="candidate", target_id=candidate.id, relation="concerns", origin="system")
    if event_bus is not None:
        event_bus.publish(BusinessEvent(event_type=CANDIDATE_CREATED, source="people", payload={"subject_type": "candidate", "subject_id": str(candidate.id), "title": candidate.full_name}))
    return candidate


def match_candidate(session: Session, candidate: Candidate) -> list[dict]:
    """How a candidate's declared skills cover each declared need (skill
    overlap). A reading aid for a human, never an automatic decision."""

    skills = _norm(candidate.skills)
    gaps = {g["need_id"]: g for g in skills_gap(session, candidate.company_id)["gaps"]}
    results = []
    for need in session.query(SkillNeed).filter_by(company_id=candidate.company_id).all():
        keys = _norm([need.skill, *need.keywords])
        hits = sorted({k for k in keys for s in skills if k in s or s in k})
        ratio = len(hits) / len(keys) if keys else 0
        level = "élevée" if ratio >= 0.5 else "moyenne" if ratio >= 0.25 else "faible"
        results.append(
            {
                "need_id": need.id, "need": need.skill, "need_is_gap": need.id in gaps, "need_priority": need.priority,
                "match": level, "match_label": tx(level, {"élevée": "high", "moyenne": "medium", "faible": "low"}[level]),
                "matched_skills": hits, "basis": "declared",
                "note": tx("Correspondance calculée sur les compétences déclarées par le candidat (non vérifiées).", "Match computed on the skills declared by the candidate (not verified)."),
            }
        )  # fmt: skip
    order = {"élevée": 0, "moyenne": 1, "faible": 2}
    return sorted(results, key=lambda r: (not r["need_is_gap"], order[r["match"]]))


def employee_view(session: Session, employee: Employee, *, include_costs: bool) -> dict:
    cost = employee_cost(session, employee) if include_costs else None
    contribution = estimate_contribution(session, employee, cost)
    if not include_costs:
        contribution.cost_coverage = None  # never leak a cost ratio to someone without cost access
    return {
        "cost": asdict(cost) if cost else None,
        "tasks": task_summary(session, employee),
        "contribution": asdict(contribution),
        "suggestions": evolution_suggestions(session, employee),
    }
