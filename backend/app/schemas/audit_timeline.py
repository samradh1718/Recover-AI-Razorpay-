from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditTimelineEventResponse(BaseModel):
    id: str
    event_type: str
    title: str
    description: str
    source: str
    status: str
    occurred_at: datetime
    details: dict[str, Any]


class CaseAuditTimelineResponse(BaseModel):
    case_id: UUID
    tenant_id: UUID
    provider_payment_id: str | None
    current_state: str
    total_events: int
    events: list[AuditTimelineEventResponse]