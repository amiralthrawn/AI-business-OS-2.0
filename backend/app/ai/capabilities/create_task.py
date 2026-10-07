import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.actions.service import ActionsService
from app.ai.capabilities.base import Capability, CapabilityExecutionError
from app.core.entities import Company, RelatedEntityType
from app.core.events.bus import EventBus


class CreateTaskInput(BaseModel):
    """No `status` field exists here on purpose: a Task proposed by the AI can
    only ever come out PENDING_VALIDATION (see ActionsService.propose_task).
    `extra="forbid"` turns an attempt to sneak in a different status into a
    hard validation error instead of a silently dropped field."""

    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    title: str
    description: str | None = None
    related_entity_type: RelatedEntityType | None = None
    related_entity_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    agent: str | None = None
    # Both interface languages of a system-written title/description (app.core.i18n).
    i18n: dict | None = None


class CreateTaskOutput(BaseModel):
    task_id: uuid.UUID
    title: str
    status: str
    requires_human_validation: bool


def _execute(session: Session, event_bus: EventBus | None, data: CreateTaskInput) -> CreateTaskOutput:
    if event_bus is None:
        raise CapabilityExecutionError("create_task requires an Event Bus to record the proposed action")

    company = session.get(Company, data.company_id)
    if company is None:
        raise CapabilityExecutionError(f"Company {data.company_id} not found")

    # This capability only ever PROPOSES the action -- it never creates the
    # real business Task itself. ActionsService.propose_task always sets
    # PENDING_VALIDATION; the row only becomes a real Task later, through
    # ActionExecutor, and only after a human calls POST .../approve. This
    # capability has no reference to ActionExecutor and cannot reach it.
    task = ActionsService(session, event_bus).propose_task(
        company_id=data.company_id,
        title=data.title,
        description=data.description,
        i18n=data.i18n,
        related_entity_type=data.related_entity_type,
        related_entity_id=data.related_entity_id,
        pending_action="create_task",
        correlation_id=data.correlation_id,
        agent=data.agent,
    )

    return CreateTaskOutput(
        task_id=task.id,
        title=task.title,
        status=task.status.value,
        requires_human_validation=True,
    )


create_task_capability = Capability(
    name="create_task",
    description="Proposes a Task for human review from AI-resolved context. Always PENDING_VALIDATION; "
    "the real Task only exists after a human approves it.",
    input_schema=CreateTaskInput,
    output_schema=CreateTaskOutput,
    requires_human_validation=True,
    executor=_execute,
    kind="action",
)
