import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.intelligence.risks.kinds import review_task_texts
from app.core.entities import Contact, RelatedEntityType, Risk, Task, TaskStatus
from app.core.events.bus import EventBus
from app.core.events.business_event import BusinessEvent

TASK_CREATED = "TaskCreated"
ACTION_PROPOSED = "ActionProposed"


class ActionsError(Exception):
    """An invalid Actions domain operation (e.g. approving a Task that isn't a
    pending AI action proposal)."""


class TaskNotFoundError(ActionsError):
    pass


class ActionsService:
    """Turns a signal from elsewhere in the system -- Intelligence's Risk
    detection, or the AI layer's action proposals -- into a Task. Holds no data
    of its own beyond the Task it writes to the shared Data Core, and is the
    only place in the codebase that writes a Task row."""

    def __init__(self, session: Session, event_bus: EventBus) -> None:
        self.session = session
        self.event_bus = event_bus

    def propose_task(
        self,
        *,
        company_id: uuid.UUID,
        title: str,
        description: str | None = None,
        related_entity_type: RelatedEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
        pending_action: str = "create_task",
        correlation_id: uuid.UUID | None = None,
        agent: str | None = None,
        i18n: dict | None = None,
    ) -> Task:
        """Creates a Task that represents a proposed action awaiting human
        validation -- e.g. from the AI `create_task` capability. This is the
        SAME row that becomes the real, active Task once approved and
        executed (see `finalize_create_task`): there is no separate
        ActionProposal table, only a status transition on this row.

        Deliberately does not publish TaskCreated: at this point the Task is
        only a proposal, not yet a real business Task, so publishing that
        event here would be misleading. `ActionProposed` is published instead.
        `pending_action` records which ActionExecutor branch should run on
        approval; a Task with `pending_action=None` (e.g. one created by
        `create_task_from_risk_created`) is not eligible for approve/reject.
        """

        correlation_id = correlation_id or uuid.uuid4()
        task = Task(
            company_id=company_id,
            title=title,
            description=description,
            i18n=i18n,
            status=TaskStatus.PENDING_VALIDATION,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            pending_action=pending_action,
            correlation_id=correlation_id,
        )
        self.session.add(task)
        self.session.commit()

        payload: dict = {
            "task_id": str(task.id),
            "pending_action": pending_action,
            "related_entity_type": related_entity_type.value if related_entity_type else None,
            "related_entity_id": str(related_entity_id) if related_entity_id else None,
        }
        if agent is not None:
            payload["agent"] = agent

        self.event_bus.publish(
            BusinessEvent(event_type=ACTION_PROPOSED, source="ai", correlation_id=correlation_id, payload=payload)
        )
        return task

    def create_manual_task(
        self,
        *,
        company_id: uuid.UUID,
        title: str,
        description: str | None = None,
        domain: str | None = None,
        requires_decision: bool = False,
        related_entity_type: RelatedEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
        i18n: dict | None = None,
    ) -> Task:
        """A Task created directly by a human from the frontend (Step 27's
        "Créer une tâche" action, available from a Risk/Opportunity/Supplier/
        Customer view, and Step 29's action library) -- status OPEN
        immediately: nothing here is an AI proposal awaiting approval, it's a
        human's own task, so it is not routed through the
        PENDING_VALIDATION/HITL cycle at all (same `pending_action=None`
        convention as the Risk->Task reactive flow)."""

        task = Task(
            company_id=company_id,
            title=title,
            description=description,
            i18n=i18n,
            domain=domain,
            requires_decision=requires_decision,
            status=TaskStatus.OPEN,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=TASK_CREATED,
                source="human",
                correlation_id=uuid.uuid4(),
                payload={
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "related_entity_type": related_entity_type.value if related_entity_type else None,
                    "related_entity_id": str(related_entity_id) if related_entity_id else None,
                },
            )
        )
        return task

    def get_pending_proposal(self, task_id: uuid.UUID) -> Task:
        """Loads a Task and verifies it is an AI action proposal still
        awaiting a human decision. Raised errors are safe to surface as clean
        API errors (404 for missing, 400 for an invalid state)."""

        task = self.session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if task.pending_action is None:
            raise ActionsError(f"Task {task_id} is not an AI action proposal")
        if task.status != TaskStatus.PENDING_VALIDATION:
            raise ActionsError(
                f"Task {task_id} is not pending validation (current status: {task.status.value})"
            )
        return task

    def mark_rejected(self, task: Task) -> Task:
        task.status = TaskStatus.REJECTED
        self.session.add(task)
        self.session.commit()
        return task

    def finalize_create_task(self, task: Task) -> Task:
        """The business effect of the create_task action: the proposal becomes
        a real, active Task. No new row is created -- the proposal WAS the
        Task all along; only its status changes, which is what distinguishes
        "proposed" from "real" for this MVP without a second table. This is
        the point at which TaskCreated is finally published."""

        task.status = TaskStatus.EXECUTED
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=TASK_CREATED,
                source="actions",
                correlation_id=task.correlation_id or uuid.uuid4(),
                payload={
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "related_entity_type": task.related_entity_type.value if task.related_entity_type else None,
                    "related_entity_id": str(task.related_entity_id) if task.related_entity_id else None,
                },
            )
        )
        return task

    def finalize_connector_followup(self, task: Task, action_type: Literal["email", "meeting"]) -> Task:
        """The business effect of a connector-backed follow-up action (step
        22, external data): after human approval, reuses the EXISTING
        app.connectors Mock Providers to send a follow-up email or propose a
        follow-up meeting -- never a second action system, never anything
        beyond what Decision Intelligence already proposed and a human
        already approved.

        Re-resolves the target Contact's email from the Task's own
        `related_entity_type`/`related_entity_id` (set at proposal time by
        `propose_task`) rather than storing it separately on the Task --
        the same (entity_type, entity_id) pair Decision Intelligence used to
        propose this Task in the first place. If no Contact with an email is
        found for that entity, the Task still finalizes (nothing is left
        PENDING_VALIDATION forever); the connector step is simply a no-op --
        a documented limitation (see brain/external_data_intelligence.md),
        not a silent failure.
        """

        contact = None
        if task.related_entity_type is not None and task.related_entity_id is not None:
            contact = (
                self.session.query(Contact)
                .filter_by(related_entity_type=task.related_entity_type, related_entity_id=task.related_entity_id)
                .filter(Contact.email.isnot(None))
                .first()
            )

        connector_used: str | None = None
        if contact is not None:
            from app.connectors.registry import connector_registry

            if action_type == "email":
                connector_registry.get_connector("email").send_message(
                    recipients=[contact.email], subject=f"Re: {task.title}", body=task.description or ""
                )
                connector_used = "email"
            elif action_type == "meeting":
                start = datetime.now(timezone.utc) + timedelta(days=2)
                connector_registry.get_connector("calendar").create_event(
                    title=task.title,
                    start=start,
                    end=start + timedelta(hours=1),
                    attendees=[contact.email],
                    description=task.description,
                )
                connector_used = "calendar"

        task.status = TaskStatus.EXECUTED
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=TASK_CREATED,
                source="actions",
                correlation_id=task.correlation_id or uuid.uuid4(),
                payload={
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "related_entity_type": task.related_entity_type.value if task.related_entity_type else None,
                    "related_entity_id": str(task.related_entity_id) if task.related_entity_id else None,
                    "connector_action": action_type,
                    "connector_used": connector_used,
                    "contact_email": contact.email if contact is not None else None,
                },
            )
        )
        return task

    def create_task_from_risk_created(self, event: BusinessEvent) -> Task | None:
        # Idempotence at the persistence level, same approach as Risk detection:
        # a given source event must never produce more than one Task, even if
        # this handler is invoked again outside the Event Bus (e.g. a replay).
        already_created = self.session.query(Task).filter_by(source_event_id=event.event_id).first()
        if already_created is not None:
            return None

        risk_id = uuid.UUID(event.payload["risk_id"])
        risk = self.session.get(Risk, risk_id)
        if risk is None:
            # Data inconsistency (the Risk this event points to is gone) --
            # nothing to build a Task from.
            return None

        texts = review_task_texts(risk.i18n, risk.title, risk.description)
        task = Task(
            company_id=risk.company_id,
            # Derived from the actual Risk rather than a hardcoded string:
            # this handler reacts to every RiskCreated regardless of which
            # rule produced it (cost increase, margin, delivery performance,
            # customer decline, ...), so the title must reflect that risk,
            # not assume it was always a supplier cost increase.
            title=texts["fr"]["title"],
            description=texts["fr"]["description"],
            i18n=texts,
            status=TaskStatus.PENDING_VALIDATION,
            related_entity_type=risk.related_entity_type,
            related_entity_id=risk.related_entity_id,
            source_event_id=event.event_id,
        )
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=TASK_CREATED,
                source="actions",
                correlation_id=event.correlation_id,
                payload={
                    "task_id": str(task.id),
                    "risk_id": str(risk.id),
                    "supplier_id": event.payload.get("supplier_id"),
                    "product_id": event.payload.get("product_id"),
                    "status": task.status.value,
                },
            )
        )
        return task

    # A human moving their OWN task along its lifecycle (step 29 point 12) --
    # never used on an AI proposal awaiting validation (`pending_action` set
    # while still `PENDING_VALIDATION`), which must go through approve/reject
    # instead so nothing bypasses HITL.
    _ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.OPEN: {TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.CANCELLED},
        TaskStatus.IN_PROGRESS: {TaskStatus.DONE, TaskStatus.OPEN, TaskStatus.CANCELLED},
    }

    def submit_for_validation(self, task_id: uuid.UUID) -> Task:
        """A human submits their own OPEN task for another human's
        validation (step 29 point 14 -- some actions, e.g. a financing
        request, must be decided on before they can be considered done).
        Reuses the EXISTING "create_task" execution branch: approving it
        simply marks the task EXECUTED (see `finalize_create_task`), which is
        exactly the right effect here too -- "this action is now approved."
        No new ActionExecutor branch, no new architecture."""

        task = self.session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if task.status != TaskStatus.OPEN or task.pending_action is not None:
            raise ActionsError(f"Task {task_id} cannot be submitted for validation from its current state")

        correlation_id = uuid.uuid4()
        task.status = TaskStatus.PENDING_VALIDATION
        task.pending_action = "create_task"
        task.correlation_id = correlation_id
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type=ACTION_PROPOSED,
                source="human",
                correlation_id=correlation_id,
                payload={
                    "task_id": str(task.id),
                    "pending_action": task.pending_action,
                    "related_entity_type": task.related_entity_type.value if task.related_entity_type else None,
                    "related_entity_id": str(task.related_entity_id) if task.related_entity_id else None,
                },
            )
        )
        return task

    def update_status(self, task_id: uuid.UUID, new_status: TaskStatus) -> Task:
        task = self.session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if task.pending_action is not None and task.status == TaskStatus.PENDING_VALIDATION:
            raise ActionsError(f"Task {task_id} is an AI proposal awaiting validation; use approve/reject instead")
        allowed = self._ALLOWED_STATUS_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ActionsError(f"Cannot move Task {task_id} from '{task.status.value}' to '{new_status.value}'")

        task.status = new_status
        self.session.add(task)
        self.session.commit()

        self.event_bus.publish(
            BusinessEvent(
                event_type="TaskStatusChanged",
                source="human",
                correlation_id=uuid.uuid4(),
                payload={"task_id": str(task.id), "status": new_status.value},
            )
        )
        return task
