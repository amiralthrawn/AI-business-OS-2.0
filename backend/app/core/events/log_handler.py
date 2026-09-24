from typing import Callable

from sqlalchemy.orm import Session

from app.core.entities.event_log import EventLogEntry
from app.core.events.bus import EventHandler
from app.core.events.business_event import BusinessEvent
from app.core.events.subjects import infer_subject


def make_event_log_handler(session_factory: Callable[[], Session]) -> EventHandler:
    """Builds a handler that persists every event it receives into the Event Log.
    Meant to be subscribed to the bus's wildcard event type, so the log is just
    another consumer of the bus rather than logic baked into the bus itself.

    Takes a session factory rather than a live Session: the bus this handler is
    attached to is shared for the whole application lifetime, so the handler
    must open and close its own short-lived session on every call instead of
    depending on whichever request happened to be running when it was wired up.
    """

    def handle(event: BusinessEvent) -> None:
        subject_type, subject_id = infer_subject(event.payload)
        session = session_factory()
        try:
            session.add(
                EventLogEntry(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    source=event.source,
                    correlation_id=event.correlation_id,
                    occurred_at=event.occurred_at,
                    subject_type=subject_type,
                    subject_id=subject_id,
                )
            )
            session.commit()
        finally:
            session.close()

    return handle
