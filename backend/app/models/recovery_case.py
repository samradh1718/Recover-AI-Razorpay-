from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Index,
    Integer,
    Numeric,
    String
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.enums import FailureCategory, RecoveryCaseState
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    __table_args__ = (
        CheckConstraint(
            "provider_payment_id IS NOT NULL "
            "OR provider_subscription_id IS NOT NULL",
            name="recovery_case_provider_reference_required"
        ),

        CheckConstraint(
            "original_amount_rupees >= 0",
            name="recovery_case_original_amount_non_negative"
        ),

        CheckConstraint(
            "recoverable_amount_rupees >= 0",
            name="recovery_case_recoverable_amount_non_negative"
        ),

        CheckConstraint(
            "recoverable_amount_rupees <= original_amount_rupees",
            name="recovery_case_recoverable_within_original"
        ),

        CheckConstraint(
            "recovered_amount_rupees >= 0",
            name="recovery_case_recovered_amount_non_negative"
        ),

        CheckConstraint(
            "recovered_amount_rupees <= original_amount_rupees",
            name="recovery_case_recovered_within_original"
        ),

        CheckConstraint(
            "intervention_cost_rupees >= 0",
            name="recovery_case_intervention_cost_non_negative"
        ),

        Index(
            "recovery_case_state_next_action_index",
            "current_state",
            "next_action_at"
        )
    )

    # Unique ID of the Recovery Case
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # Merchant/company that owns this Recovery Case
    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True
    )

    # Razorpay payment ID
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True
    )

    # Razorpay subscription ID
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True
    )

    # Razorpay customer ID
    provider_customer_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )

    # Currency such as INR
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR"
    )

    # Original failed-payment amount
    original_amount_rupees: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    # Amount that can still be recovered
    recoverable_amount_rupees: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    # Amount successfully recovered
    recovered_amount_rupees: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    # Cost of reminders, discounts or interventions
    intervention_cost_rupees: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    # Normalized reason why the payment failed
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        SqlEnum(
            FailureCategory,
            name="failure_category",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ]
        ),
        nullable=True
    )

    # Current Recovery Case state
    current_state: Mapped[RecoveryCaseState] = mapped_column(
        SqlEnum(
            RecoveryCaseState,
            name="recovery_case_state",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ]
        ),
        nullable=False,
        default=RecoveryCaseState.DETECTED,
        index=True
    )

    # Protects the case from simultaneous conflicting updates
    state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Number of payment recovery attempts
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Number of customer communications
    communication_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Time at which the next action should run
    next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Time after which recovery must stop
    recovery_deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Time at which payment was recovered
    recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Time at which the case was permanently closed
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Time at which the case was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    # Time at which the case was last updated
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now
    )