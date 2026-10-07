import uuid
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import text_of, tx
from app.access.deps import CurrentUser, get_current_user, require
from app.access.policy import VIEW_EMPLOYEE_COSTS, WRITE_PEOPLE
from app.actions.service import ActionsService
from app.ai.llm import LLMClient, get_llm_client
from app.core.entities import Candidate, Communication, CommunicationDirection, Company, Employee, RelatedEntityType, SkillNeed, Task, ValueBasis
from app.core.events.bus import EventBus
from app.core.tenancy import current_company
from app.database import get_db
from app.dependencies import get_event_bus
from app.people import service

router = APIRouter(prefix="/people", tags=["people"])


class EmployeeIn(BaseModel):
    full_name: str
    email: str | None = None
    job_title: str | None = None
    department: str | None = None
    status: str = "active"
    hired_at: datetime | None = None
    weekly_hours: float | None = None
    leave_days_remaining: float | None = None
    skills: list[str] = []
    responsibilities: list[str] = []
    user_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    data_basis: ValueBasis = ValueBasis.DECLARED


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    job_title: str | None = None
    department: str | None = None
    status: str | None = None
    weekly_hours: float | None = None
    leave_days_remaining: float | None = None
    skills: list[str] | None = None
    responsibilities: list[str] | None = None
    user_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


class CostIn(BaseModel):
    kind: str
    annual_min: float
    annual_max: float | None = None
    basis: ValueBasis
    label: str | None = None
    confidence: str = "medium"
    source: str | None = None


class TaskIn(BaseModel):
    title: str
    description: str | None = None
    due_at: datetime | None = None
    requires_decision: bool = False


class DecisionIn(BaseModel):
    kind: str
    rationale: str
    new_job_title: str | None = None
    new_salary: float | None = None


class SkillNeedIn(BaseModel):
    skill: str
    keywords: list[str] = []
    level: str = "confirmé"
    reason: str | None = None
    expected_impact: str | None = None
    priority: str = "medium"


class CandidateUpdate(BaseModel):
    status: str


def _employee(db: Session, company: Company, employee_id: uuid.UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Employé introuvable", "Employee not found"))
    return employee


def _employee_out(employee: Employee) -> dict:
    return {
        "id": employee.id, "full_name": employee.full_name, "email": employee.email, "job_title": employee.job_title,
        "department": employee.department, "status": employee.status, "hired_at": employee.hired_at,
        "weekly_hours": employee.weekly_hours, "leave_days_remaining": employee.leave_days_remaining,
        "skills": employee.skills, "responsibilities": employee.responsibilities, "user_id": employee.user_id,
        "manager_id": employee.manager_id, "data_basis": employee.data_basis.value,
    }  # fmt: skip


def _guard(fn, db: Session):
    try:
        return fn()
    except service.PeopleError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/employees")
def list_employees(db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    show_costs = user.can(VIEW_EMPLOYEE_COSTS)
    rows = []
    for e in db.query(Employee).filter_by(company_id=company.id).order_by(Employee.full_name).all():
        row = _employee_out(e) | {"tasks": service.task_summary(db, e)}
        if show_costs:
            cost = service.employee_cost(db, e)
            row["cost"] = {"total_min": cost.total_min, "total_max": cost.total_max, "basis": cost.basis, "confidence": cost.confidence}
        rows.append(row)
    return rows


@router.post("/employees")
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    employee = Employee(company_id=company.id, **payload.model_dump())
    db.add(employee)
    db.commit()
    return _employee_out(employee)


@router.get("/employees/{employee_id}")
def get_employee(employee_id: uuid.UUID, db: Session = Depends(get_db), company: Company = Depends(current_company), user: CurrentUser = Depends(get_current_user)) -> dict:
    employee = _employee(db, company, employee_id)
    include_costs = user.can(VIEW_EMPLOYEE_COSTS)
    tasks = db.query(Task).filter(Task.assignee_employee_id == employee.id).order_by(Task.created_at.desc()).limit(50).all()
    return _employee_out(employee) | service.employee_view(db, employee, include_costs=include_costs) | {
        "can_view_costs": include_costs,
        "task_list": [{"id": t.id, "title": text_of(t, "title"), "status": t.status.value, "due_at": t.due_at, "requires_decision": t.requires_decision} for t in tasks],
        "decisions": [
            {"id": t.id, "title": text_of(t, "title"), "status": t.status.value, "category": t.category, "created_at": t.created_at}
            for t in db.query(Task).filter(Task.related_entity_type == RelatedEntityType.EMPLOYEE, Task.related_entity_id == employee.id, Task.pending_action == service.HR_DECISION_ACTION).order_by(Task.created_at.desc()).all()
        ],
    }


@router.patch("/employees/{employee_id}")
def update_employee(employee_id: uuid.UUID, payload: EmployeeUpdate, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    employee = _employee(db, company, employee_id)
    changes = payload.model_dump(exclude_unset=True)
    if "job_title" in changes:
        # A title change is a promotion: it goes through a validated decision.
        raise HTTPException(status_code=400, detail=tx("Le poste change via une décision de promotion validée.", "The job title changes through an approved promotion decision."))
    for key, value in changes.items():
        setattr(employee, key, value)
    db.commit()
    return _employee_out(employee)


@router.post("/employees/{employee_id}/costs")
def add_cost(
    employee_id: uuid.UUID, payload: CostIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus),
    company: Company = Depends(current_company), _w: CurrentUser = Depends(require(WRITE_PEOPLE)), _c: CurrentUser = Depends(require(VIEW_EMPLOYEE_COSTS)),
) -> dict:  # fmt: skip
    employee = _employee(db, company, employee_id)
    _guard(lambda: service.add_cost_item(db, event_bus, employee, **payload.model_dump()), db)
    return asdict(service.employee_cost(db, employee))


@router.post("/employees/{employee_id}/tasks")
def assign_task(employee_id: uuid.UUID, payload: TaskIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    """"Créer / envoyer une tâche" to an employee: a real, immediate Task
    (a human assigning work is not an AI proposal)."""

    employee = _employee(db, company, employee_id)
    task = ActionsService(db, event_bus).create_manual_task(
        company_id=company.id, title=payload.title, description=payload.description, domain="people",
        requires_decision=payload.requires_decision, related_entity_type=RelatedEntityType.EMPLOYEE, related_entity_id=employee.id,
    )  # fmt: skip
    task.assignee_employee_id = employee.id
    task.due_at = payload.due_at
    db.commit()
    return {"id": task.id, "title": task.title, "status": task.status.value}


@router.post("/employees/{employee_id}/decisions")
def propose_decision(employee_id: uuid.UUID, payload: DecisionIn, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), user: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    employee = _employee(db, company, employee_id)
    if payload.kind == "raise" and not user.can(VIEW_EMPLOYEE_COSTS):
        raise HTTPException(status_code=403, detail=tx("Proposer une augmentation nécessite l'accès aux rémunérations.", "Proposing a raise requires access to compensation."))
    task = _guard(lambda: service.propose_decision(db, event_bus, employee, **payload.model_dump()), db)
    return {"task_id": task.id, "status": task.status.value, "note": tx("Proposition en attente de validation par la direction — rien n'est appliqué avant.", "Proposal awaiting approval by management — nothing is applied before then.")}


@router.get("/skill-needs")
def list_needs(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    return [
        {"id": n.id, "skill": n.skill, "keywords": n.keywords, "level": n.level, "reason": n.reason, "expected_impact": n.expected_impact, "priority": n.priority, "basis": n.basis.value}
        for n in db.query(SkillNeed).filter_by(company_id=company.id).order_by(SkillNeed.created_at).all()
    ]


@router.post("/skill-needs")
def add_need(payload: SkillNeedIn, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    need = SkillNeed(company_id=company.id, **payload.model_dump())
    db.add(need)
    db.commit()
    return {"id": need.id}


@router.get("/skills-gap")
def get_skills_gap(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> dict:
    return service.skills_gap(db, company.id)


@router.post("/skills-gap/publish")
def publish_gaps(db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    return {"opportunities_created": service.publish_skill_gaps(db, event_bus, company.id)}


def _candidate_out(db: Session, c: Candidate) -> dict:
    return {
        "id": c.id, "full_name": c.full_name, "email": c.email, "applied_for": c.applied_for, "skills": c.skills,
        "years_experience": c.years_experience, "status": c.status, "basis": c.basis.value, "extracted_by": c.extracted_by,
        "communication_id": c.communication_id, "created_at": c.created_at, "matches": service.match_candidate(db, c),
    }  # fmt: skip


@router.get("/candidates")
def list_candidates(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    return [_candidate_out(db, c) for c in db.query(Candidate).filter_by(company_id=company.id).order_by(Candidate.created_at.desc()).all()]


@router.get("/applications")
def pending_applications(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[dict]:
    """Inbound messages that look like applications and have no candidate yet."""

    done = {c.communication_id for c in db.query(Candidate.communication_id).filter_by(company_id=company.id).all()}
    rows = db.query(Communication).filter(Communication.company_id == company.id, Communication.direction == CommunicationDirection.INBOUND).all()
    return [{"id": c.id, "subject": c.subject, "from_address": c.from_address, "occurred_at": c.occurred_at} for c in rows if c.id not in done and service.looks_like_application(c)]


@router.post("/candidates/from-communication/{communication_id}")
def candidate_from_email(
    communication_id: uuid.UUID, db: Session = Depends(get_db), event_bus: EventBus = Depends(get_event_bus), company: Company = Depends(current_company),
    llm: LLMClient = Depends(get_llm_client), _: CurrentUser = Depends(require(WRITE_PEOPLE)),
) -> dict:  # fmt: skip
    communication = db.get(Communication, communication_id)
    if communication is None or communication.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Message introuvable", "Message not found"))
    return _candidate_out(db, service.extract_candidate(db, event_bus, communication, llm))


@router.patch("/candidates/{candidate_id}")
def update_candidate(candidate_id: uuid.UUID, payload: CandidateUpdate, db: Session = Depends(get_db), company: Company = Depends(current_company), _: CurrentUser = Depends(require(WRITE_PEOPLE))) -> dict:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.company_id != company.id:
        raise HTTPException(status_code=404, detail=tx("Candidat introuvable", "Candidate not found"))
    if payload.status not in {"new", "shortlisted", "interview_proposed", "rejected", "hired"}:
        raise HTTPException(status_code=400, detail=tx("Statut inconnu", "Unknown status"))
    candidate.status = payload.status
    db.commit()
    return _candidate_out(db, candidate)
