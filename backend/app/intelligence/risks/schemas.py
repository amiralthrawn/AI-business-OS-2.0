import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.entities.base import RelatedEntityType
from app.core.localized_schema import LocalizedTextRead
from app.core.entities.risk import RiskSeverity, RiskStatus


class RiskRead(LocalizedTextRead):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    severity: RiskSeverity
    status: RiskStatus
    related_entity_type: RelatedEntityType | None
    related_entity_id: uuid.UUID | None
    source_event_id: uuid.UUID | None
    created_at: datetime
