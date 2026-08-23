from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.contracts.enums import (
    PolicyResult,
    RecoveryActionType,
    RecoveryDecisionStatus,
)


class RecoveryDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    recovery_case_id: UUID
    case_state_version: int

    recommended_action: RecoveryActionType
    final_action: RecoveryActionType | None
    policy_result: PolicyResult
    status: RecoveryDecisionStatus

    recovery_probability: Decimal
    expected_recovery_rupees: Decimal
    estimated_action_cost_rupees: Decimal
    expected_net_value_rupees: Decimal

    explanation: str
    reason_codes: list[str]
    decision_inputs: dict[str, Any]
    alternatives: list[dict[str, Any]]
    model_source: str

    scheduled_for: datetime | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime