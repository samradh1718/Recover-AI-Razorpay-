from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator
)

from app.contracts.enums import (
    FailureCategory,
    RecoveryCaseState
)


class RecoveryCaseCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    tenant_id: UUID

    provider_payment_id: str | None = Field(
        default=None,
        max_length=128
    )

    provider_subscription_id: str | None = Field(
        default=None,
        max_length=128
    )

    provider_customer_id: str | None = Field(
        default=None,
        max_length=128
    )

    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3
    )

    original_amount_rupees: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2
    )

    recoverable_amount_rupees: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2
    )

    recovery_deadline_at: datetime

    @model_validator(mode="after")
    def validate_recovery_case(self):
        if (
            self.provider_payment_id is None
            and self.provider_subscription_id is None
        ):
            raise ValueError(
                "Payment ID or subscription ID is required"
            )

        if (
            self.recoverable_amount_rupees
            > self.original_amount_rupees
        ):
            raise ValueError(
                "Recoverable amount cannot exceed original amount"
            )

        return self


class RecoveryCaseResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    tenant_id: UUID

    provider_payment_id: str | None
    provider_subscription_id: str | None
    provider_customer_id: str | None

    currency: str

    original_amount_rupees: Decimal
    recoverable_amount_rupees: Decimal
    recovered_amount_rupees: Decimal
    intervention_cost_rupees: Decimal

    failure_category: FailureCategory | None
    current_state: RecoveryCaseState

    state_version: int
    attempt_count: int
    communication_count: int

    next_action_at: datetime | None
    recovery_deadline_at: datetime
    recovered_at: datetime | None
    closed_at: datetime | None

    created_at: datetime
    updated_at: datetime