import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.entities.base import RelatedEntityType
from app.core.localized_schema import LocalizedTextRead
from app.core.entities.task import TaskStatus


class TaskRead(LocalizedTextRead):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    status: TaskStatus
    domain: str | None
    requires_decision: bool
    related_entity_type: RelatedEntityType | None
    related_entity_id: uuid.UUID | None
    source_event_id: uuid.UUID | None
    pending_action: str | None
    correlation_id: uuid.UUID | None
    created_at: datetime


class TaskCreate(BaseModel):
    """A Task created directly by a human (Step 27's "Créer une tâche"
    action) -- never an AI proposal, so there is no `pending_action` here.
    `domain` is the free-form sector tag from Step 29's action library
    (e.g. "finance", "hr") -- optional, since not every task belongs to one."""

    title: str
    description: str | None = None
    domain: str | None = None
    requires_decision: bool = False
    related_entity_type: RelatedEntityType | None = None
    related_entity_id: uuid.UUID | None = None


class TaskStatusUpdate(BaseModel):
    """A human moving their OWN task along (open -> in_progress -> done, or
    cancelled) -- step 29 point 12. Deliberately separate from approve/reject:
    those govern an AI action PROPOSAL (`pending_action` set); this is a
    person managing a task they already own, never used to force an AI
    proposal into `executed` without going through HITL."""

    status: TaskStatus
