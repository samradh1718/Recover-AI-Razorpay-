from typing import Literal

from pydantic import BaseModel, Field


AllowedShadowAction = Literal[
    "retry_payment",
    "send_payment_link",
    "request_payment_method_update",
    "request_customer_authorization",
    "human_review",
    "stop_recovery",
]


class AIShadowRecommendation(BaseModel):
    recommended_action: AllowedShadowAction

    recovery_probability: float = Field(
        ge=0,
        le=1,
    )

    explanation: str = Field(
        min_length=10,
        max_length=1000,
    )

    reason_codes: list[str] = Field(
        min_length=1,
        max_length=8,
    )

    class Config:
        extra = "forbid"