import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.access.deps import CurrentUser, get_current_user
from app.actions.executor import ActionExecutor
from app.actions.schemas import TaskCreate, TaskRead, TaskStatusUpdate
from app.actions.service import ActionsError, ActionsService, TaskNotFoundError
from app.core.entities import Company, Task
from app.core.events.bus import EventBus
from app.database import get_db
from app.dependencies import get_event_bus

router = APIRouter(prefix="/actions/tasks", tags=["actions"])


def _ensure_can_decide(db: Session, user: CurrentUser, task_id: uuid.UUID) -> None:
    """V2 permissions: approving/rejecting a proposal is scoped by the Task's
    domain (a buyer validates procurement emails, not sales ones; the
    director validates everything). See app.access.policy.can_approve."""

    task = db.get(Task, task_id)
    if task is not None and not user.can_approve(task.domain):
        raise HTTPException(status_code=403, detail="Votre rôle ne permet pas de valider cette action.")


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    return list(db.query(Task).order_by(Task.created_at.desc()).all())


@router.post("", response_model=TaskRead)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
) -> Task:
    company = db.query(Company).first()
    if company is None:
        raise HTTPException(status_code=404, detail="No company configured yet")

    return ActionsService(db, event_bus).create_manual_task(
        company_id=company.id,
        title=payload.title,
        description=payload.description,
        domain=payload.domain,
        requires_decision=payload.requires_decision,
        related_entity_type=payload.related_entity_type,
        related_entity_id=payload.related_entity_id,
    )


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.post("/{task_id}/status", response_model=TaskRead)
def update_task_status(
    task_id: uuid.UUID,
    payload: TaskStatusUpdate,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
) -> Task:
    try:
        return ActionsService(db, event_bus).update_status(task_id, payload.status)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/submit", response_model=TaskRead)
def submit_task_for_validation(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
) -> Task:
    try:
        return ActionsService(db, event_bus).submit_for_validation(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/approve", response_model=TaskRead)
def approve_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    user: CurrentUser = Depends(get_current_user),
) -> Task:
    _ensure_can_decide(db, user, task_id)
    executor = ActionExecutor(ActionsService(db, event_bus))
    try:
        return executor.approve(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/reject", response_model=TaskRead)
def reject_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus),
    user: CurrentUser = Depends(get_current_user),
) -> Task:
    _ensure_can_decide(db, user, task_id)
    executor = ActionExecutor(ActionsService(db, event_bus))
    try:
        return executor.reject(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
