from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AIShadowSummaryResponse(BaseModel):
    total_evaluations: int
    completed_count: int
    failed_count: int
    invalid_count: int
    pending_count: int
    agreement_count: int
    disagreement_count: int
    agreement_rate_percent: float
    average_latency_ms: float | None
    latest_evaluation_at: datetime | None


class AIShadowDecisionResponse(BaseModel):
    id: UUID
    recovery_case_id: UUID
    production_decision_id: UUID

    provider_payment_id: str | None
    failure_category: str | None

    model_name: str
    prompt_version: str
    status: str

    production_action: str | None
    ai_recommended_action: str | None
    agrees_with_production: bool | None

    recovery_probability: Decimal | None
    expected_recovery_rupees: Decimal | None
    estimated_action_cost_rupees: Decimal | None
    expected_net_value_rupees: Decimal | None

    explanation: str | None
    reason_codes: list[str]
    latency_ms: int | None
    error_message: str | None

    created_at: datetime