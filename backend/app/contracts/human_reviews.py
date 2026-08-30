from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.contracts.decisions import (
    RecoveryDecisionResponse,
)
from app.contracts.enums import (
    HumanReviewOutcome,
    RecoveryActionType,
    RecoveryCaseState,
)


HUMAN_EXECUTABLE_ACTIONS = {
    RecoveryActionType.RETRY_PAYMENT,
    RecoveryActionType.SEND_PAYMENT_LINK,
    RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE,
    RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION,
}


class HumanReviewResolutionRequest(BaseModel):
    tenant_id: UUID
    source_decision_id: UUID

    expected_state_version: int = Field(
        ge=0,
    )

    outcome: HumanReviewOutcome

    selected_action: RecoveryActionType | None = None

    reviewer_id: str = Field(
        min_length=1,
        max_length=128,
    )

    reviewer_name: str = Field(
        min_length=1,
        max_length=128,
    )

    reason: str = Field(
        min_length=8,
        max_length=2000,
    )

    @field_validator(
        "reviewer_id",
        "reviewer_name",
        "reason",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Value must not be blank"
            )

        return normalized

    @model_validator(mode="after")
    def validate_review_action(
        self,
    ) -> "HumanReviewResolutionRequest":
        if (
            self.outcome
            == HumanReviewOutcome.APPROVED
        ):
            if self.selected_action is None:
                raise ValueError(
                    "selected_action is required "
                    "when a review is approved"
                )

            if (
                self.selected_action
                not in HUMAN_EXECUTABLE_ACTIONS
            ):
                raise ValueError(
                    "Approved Human Review action "
                    "must be executable"
                )

            return self

        if self.selected_action is not None:
            raise ValueError(
                "selected_action must be omitted "
                "when a review is rejected"
            )

        return self


class HumanReviewRecordResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID
    tenant_id: UUID
    recovery_case_id: UUID

    source_decision_id: UUID
    resulting_decision_id: UUID

    case_state_version_before: int
    case_state_version_after: int

    outcome: HumanReviewOutcome
    selected_action: RecoveryActionType

    reviewer_id: str
    reviewer_name: str
    reason: str

    created_at: datetime


class HumanReviewResolutionResponse(BaseModel):
    review: HumanReviewRecordResponse
    decision: RecoveryDecisionResponse

    case_state: RecoveryCaseState
    action_queued: bool