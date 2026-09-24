"""Executes an action proposal after a human has explicitly approved it.

Lives in the Actions domain, not the AI layer: the AI Orchestrator can create
a proposal (a PENDING_VALIDATION Task with `pending_action` set) but holds no
reference to this class and has no code path that reaches it. Only the
human-approval API endpoint constructs an ActionExecutor and calls it -- that
is the sole boundary between "AI proposes" and "system executes".

Adding a new executable action means adding a branch to `_run` and, if
needed, a matching finalize method on ActionsService -- never routing
execution back through app.ai.
"""

import uuid

from app.actions.service import ACTION_PROPOSED, ActionsError, ActionsService  # noqa: F401  (re-exported for callers)
from app.core.entities import Task
from app.core.events.business_event import BusinessEvent

ACTION_APPROVED = "ActionApproved"
ACTION_REJECTED = "ActionRejected"
ACTION_EXECUTED = "ActionExecuted"


class UnknownActionError(ActionsError):
    pass


class ActionExecutor:
    def __init__(self, actions_service: ActionsService) -> None:
        self.actions_service = actions_service

    def approve(self, task_id: uuid.UUID) -> Task:
        task = self.actions_service.get_pending_proposal(task_id)
        correlation_id = task.correlation_id or uuid.uuid4()

        self.actions_service.event_bus.publish(
            BusinessEvent(
                event_type=ACTION_APPROVED,
                source="human",
                correlation_id=correlation_id,
                payload={"task_id": str(task.id), "pending_action": task.pending_action},
            )
        )

        task = self._run(task)

        self.actions_service.event_bus.publish(
            BusinessEvent(
                event_type=ACTION_EXECUTED,
                source="actions",
                correlation_id=correlation_id,
                payload={"task_id": str(task.id), "pending_action": task.pending_action},
            )
        )
        return task

    def reject(self, task_id: uuid.UUID) -> Task:
        task = self.actions_service.get_pending_proposal(task_id)
        correlation_id = task.correlation_id or uuid.uuid4()

        task = self.actions_service.mark_rejected(task)
        if task.pending_action == "send_email":
            from app.communications.service import on_send_rejected

            on_send_rejected(self.actions_service.session, task)
        if task.pending_action == "apply_website_change":
            from app.website.service import on_change_rejected

            on_change_rejected(self.actions_service.session, task)

        self.actions_service.event_bus.publish(
            BusinessEvent(
                event_type=ACTION_REJECTED,
                source="human",
                correlation_id=correlation_id,
                payload={"task_id": str(task.id), "pending_action": task.pending_action},
            )
        )
        return task

    def _run(self, task: Task) -> Task:
        if task.pending_action == "create_task":
            return self.actions_service.finalize_create_task(task)
        if task.pending_action == "connector_followup_email":
            return self.actions_service.finalize_connector_followup(task, action_type="email")
        if task.pending_action == "connector_followup_meeting":
            return self.actions_service.finalize_connector_followup(task, action_type="meeting")
        if task.pending_action == "send_email":
            # V2: an AI/template-prepared email, sent only now that a human
            # approved it (app.communications, brain/communications.md).
            from app.communications.service import finalize_send_email

            return finalize_send_email(self.actions_service.session, self.actions_service.event_bus, task)
        if task.pending_action == "apply_hr_decision":
            # V2.1: promotion / raise / evolution, applied only after approval.
            from app.people.service import finalize_hr_decision

            return finalize_hr_decision(self.actions_service.session, self.actions_service.event_bus, task)
        if task.pending_action == "apply_website_change":
            from app.website.service import finalize_website_change

            return finalize_website_change(self.actions_service.session, self.actions_service.event_bus, task)
        raise UnknownActionError(f"No executor registered for action '{task.pending_action}'")
