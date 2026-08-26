from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class MLShadowDecisionResponse(BaseModel):
    id: UUID
    recovery_case_id: UUID
    production_decision_id: UUID

    provider_payment_id: str | None
    failure_category: str | None

    model_name: str
    model_version: str
    calibration_method: str
    status: str

    production_action: str | None
    ml_selected_action: str | None

    raw_probability: Decimal | None
    calibrated_probability: Decimal | None

    expected_recovery_rupees: Decimal | None
    estimated_action_cost_rupees: Decimal | None
    expected_net_value_rupees: Decimal | None

    agrees_with_production: bool | None
    alternatives: list[dict[str, Any]]

    latency_ms: int | None
    error_message: str | None
    created_at: datetime


class MLShadowSummaryResponse(BaseModel):
    total_evaluations: int
    completed_count: int
    failed_count: int
    invalid_count: int
    pending_count: int

    agreement_count: int
    disagreement_count: int
    agreement_rate_percent: float

    average_raw_probability: Decimal | None
    average_calibrated_probability: Decimal | None
    average_expected_net_value_rupees: Decimal | None
    average_latency_ms: int | None

    latest_evaluation_at: datetime | None