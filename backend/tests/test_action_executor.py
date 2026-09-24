import uuid

import pytest

from app.actions.executor import (
    ACTION_APPROVED,
    ACTION_EXECUTED,
    ACTION_REJECTED,
    ActionExecutor,
    UnknownActionError,
)
from app.actions.service import ACTION_PROPOSED, TASK_CREATED, ActionsError, ActionsService, TaskNotFoundError
from app.core.entities import Company, EventLogEntry, RelatedEntityType, Task, TaskStatus
from app.core.events.bus import InProcessEventBus
from app.core.events.log_handler import make_event_log_handler


def _make_company(db_session) -> Company:
    company = Company(name="Acme")
    db_session.add(company)
    db_session.commit()
    return company


def _propose(db_session, event_bus, company) -> Task:
    return ActionsService(db_session, event_bus).propose_task(
        company_id=company.id,
        title="Review supplier Pacific Components",
        related_entity_type=RelatedEntityType.SUPPLIER,
        related_entity_id=uuid.uuid4(),
    )


# --- 1. Proposal --------------------------------------------------------------


def test_propose_task_creates_no_real_task_created_event(db_session, session_factory):
    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    company = _make_company(db_session)

    task = _propose(db_session, bus, company)

    assert task.status == TaskStatus.PENDING_VALIDATION
    assert task.pending_action == "create_task"
    event_types = {e.event_type for e in db_session.query(EventLogEntry).all()}
    assert ACTION_PROPOSED in event_types
    assert TASK_CREATED not in event_types


# --- 2. Approval ---------------------------------------------------------------


def test_approve_executes_the_action_and_creates_the_real_task(db_session, session_factory):
    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    company = _make_company(db_session)
    task = _propose(db_session, bus, company)
    correlation_id = task.correlation_id

    service = ActionsService(db_session, bus)
    executed = ActionExecutor(service).approve(task.id)

    assert executed.status == TaskStatus.EXECUTED

    event_types_and_corr = {
        (e.event_type, e.correlation_id) for e in db_session.query(EventLogEntry).all()
    }
    assert (ACTION_APPROVED, correlation_id) in event_types_and_corr
    assert (ACTION_EXECUTED, correlation_id) in event_types_and_corr
    assert (TASK_CREATED, correlation_id) in event_types_and_corr


# --- 3. Rejection ---------------------------------------------------------------


def test_reject_marks_rejected_and_never_executes(db_session, session_factory):
    bus = InProcessEventBus()
    bus.subscribe("*", make_event_log_handler(session_factory))
    company = _make_company(db_session)
    task = _propose(db_session, bus, company)

    service = ActionsService(db_session, bus)
    rejected = ActionExecutor(service).reject(task.id)

    assert rejected.status == TaskStatus.REJECTED

    event_types = {e.event_type for e in db_session.query(EventLogEntry).all()}
    assert ACTION_REJECTED in event_types
    assert ACTION_EXECUTED not in event_types
    assert TASK_CREATED not in event_types


# --- 4. Double approval ----------------------------------------------------------


def test_approving_twice_does_not_duplicate_execution(db_session, event_bus):
    company = _make_company(db_session)
    task = _propose(db_session, event_bus, company)
    service = ActionsService(db_session, event_bus)
    executor = ActionExecutor(service)

    executor.approve(task.id)

    with pytest.raises(ActionsError):
        executor.approve(task.id)

    assert db_session.query(Task).filter_by(pending_action="create_task").count() == 1
    assert db_session.get(Task, task.id).status == TaskStatus.EXECUTED


# --- 5. Approve after reject -----------------------------------------------------


def test_cannot_approve_a_rejected_action(db_session, event_bus):
    company = _make_company(db_session)
    task = _propose(db_session, event_bus, company)
    executor = ActionExecutor(ActionsService(db_session, event_bus))

    executor.reject(task.id)

    with pytest.raises(ActionsError):
        executor.approve(task.id)

    assert db_session.get(Task, task.id).status == TaskStatus.REJECTED


def test_cannot_reject_an_already_approved_action(db_session, event_bus):
    company = _make_company(db_session)
    task = _propose(db_session, event_bus, company)
    executor = ActionExecutor(ActionsService(db_session, event_bus))

    executor.approve(task.id)

    with pytest.raises(ActionsError):
        executor.reject(task.id)

    assert db_session.get(Task, task.id).status == TaskStatus.EXECUTED


# --- Not found / not a proposal ---------------------------------------------------


def test_approve_unknown_task_raises_not_found(db_session, event_bus):
    executor = ActionExecutor(ActionsService(db_session, event_bus))

    with pytest.raises(TaskNotFoundError):
        executor.approve(uuid.uuid4())


def test_a_task_without_pending_action_cannot_be_approved(db_session, event_bus):
    # This is exactly the shape of a Task created by the Risk->Task flow:
    # PENDING_VALIDATION, but pending_action is None, so it is not an AI
    # action proposal and must not be routed through the executor.
    company = _make_company(db_session)
    task = Task(company_id=company.id, title="Review supplier cost increase", status=TaskStatus.PENDING_VALIDATION)
    db_session.add(task)
    db_session.commit()

    executor = ActionExecutor(ActionsService(db_session, event_bus))

    with pytest.raises(ActionsError):
        executor.approve(task.id)


def test_unknown_pending_action_raises_a_clean_error(db_session, event_bus):
    company = _make_company(db_session)
    task = Task(
        company_id=company.id,
        title="Some future action",
        status=TaskStatus.PENDING_VALIDATION,
        pending_action="some_future_action",  # V2 implemented "send_email", the previous example
        correlation_id=uuid.uuid4(),
    )
    db_session.add(task)
    db_session.commit()

    executor = ActionExecutor(ActionsService(db_session, event_bus))

    with pytest.raises(UnknownActionError):
        executor.approve(task.id)
