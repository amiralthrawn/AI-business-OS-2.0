import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, LinkableMixin, TimestampMixin


class TaskStatus(str, enum.Enum):
    PENDING_VALIDATION = "pending_validation"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"
    # Human-in-the-loop cycle for AI-proposed actions (step 11):
    # PENDING_VALIDATION -> REJECTED, or PENDING_VALIDATION -> EXECUTED.
    REJECTED = "rejected"
    EXECUTED = "executed"


class Task(Base, IdMixin, TimestampMixin, LinkableMixin):
    __tablename__ = "tasks"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), nullable=False, default=TaskStatus.OPEN, index=True)
    # Traces which Business Event (Event Log entry) produced this task, for audit.
    # Not a foreign key: the polymorphic event source isn't a single target table.
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)

    # Human-in-the-loop fields (step 11). A Task proposed by the AI layer is
    # the SAME row throughout its lifecycle -- there is no separate
    # ActionProposal table. `pending_action` names which ActionExecutor branch
    # runs on approval (e.g. "create_task"); it is None for Tasks created
    # directly by the Risk->Task flow, which are not eligible for
    # approve/reject since they were never a "proposal" needing execution.
    pending_action: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # Carries the originating AI request's correlation_id across the whole
    # propose -> approve/reject -> execute chain, since each step is a
    # separate API call with only the task_id to go on.
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # Which business sector this Task belongs to (step 29's Tasks-as-action-
    # center redesign): "finance" | "procurement" | "sales" | "marketing" |
    # "hr" | "direction" | "operations". A free string, not an Enum, since
    # HR/Marketing/Direction/Operations have no Intelligence Engine of their
    # own to constrain it (see brain/decisions.md) -- `None` for a Task
    # whose domain isn't known, never guessed at.
    domain: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # Set at creation time from the action library (step 29 point 14) when a
    # task's action is sensitive enough that it must be analyzed and decided
    # on before it can be prepared/executed (e.g. a financing request) --
    # real, persisted, never inferred at render time from the title text.
    requires_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # V2.1 -- reused rather than new "HR task" / "compliance request" tables:
    # who it is assigned to (an Employee), when it is due, what kind of
    # request it is (e.g. "contract_review", "nda", "promotion"), and the
    # structured parameters an ActionExecutor branch needs on approval
    # (e.g. the proposed new job title) -- a HITL proposal carries its own
    # payload instead of hiding it in free text.
    assignee_employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
