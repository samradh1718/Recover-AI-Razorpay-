import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


PHONE_LIKE_PATTERN = re.compile(
    r"^\+?[0-9][0-9\s-]{7,14}$"
)


class CreateRazorpayTestCheckoutRequest(BaseModel):
    tenant_id: UUID

    amount_rupees: Decimal = Field(
        gt=Decimal("0.00"),
        max_digits=18,
        decimal_places=2,
    )

    currency: Literal["INR"] = "INR"

    customer_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Opaque demo identifier only. Do not send email, "
            "phone number or other raw customer PII."
        ),
    )

    @field_validator("customer_reference")
    @classmethod
    def validate_customer_reference(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        clean_value = value.strip()

        if not clean_value:
            return None

        if (
            "@" in clean_value
            or PHONE_LIKE_PATTERN.fullmatch(
                clean_value
            )
            is not None
        ):
            raise ValueError(
                "customer_reference must be an opaque ID, "
                "not an email address or phone number"
            )

        return clean_value


class RazorpayTestCheckoutResponse(BaseModel):
    checkout_session_id: UUID
    provider_order_id: str
    provider_order_status: str
    razorpay_key_id: str
    amount_rupees: str
    amount_paise: int
    currency: Literal["INR"]
    receipt: str
    data_source: Literal[
        "razorpay_test_checkout"
    ]
    provider_generated: bool
    real_money: bool
    created_at: datetime


class RazorpayTestOrderRecordResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    tenant_id: UUID
    provider_order_id: str
    receipt: str
    amount_rupees: Decimal
    currency: str
    provider_order_status: str
    data_source: str
    provider_generated: bool
    real_money: bool
    customer_reference: str | None
    provider_payment_id: str | None
    latest_payment_event_id: UUID | None
    outcome_status: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime