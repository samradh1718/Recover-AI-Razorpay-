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
    String,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PostgreSQLUUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.enums import (
    FailureCategory,
    RecoveryCaseState,
)
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    __table_args__ = (
        CheckConstraint(
            "provider_payment_id IS NOT NULL "
            "OR provider_subscription_id IS NOT NULL",
            name=(
                "recovery_case_"
                "provider_reference_required"
            ),
        ),
        CheckConstraint(
            "original_amount_rupees >= 0",
            name=(
                "recovery_case_"
                "original_amount_non_negative"
            ),
        ),
        CheckConstraint(
            "recoverable_amount_rupees >= 0",
            name=(
                "recovery_case_"
                "recoverable_amount_non_negative"
            ),
        ),
        CheckConstraint(
            "recoverable_amount_rupees "
            "<= original_amount_rupees",
            name=(
                "recovery_case_"
                "recoverable_within_original"
            ),
        ),
        CheckConstraint(
            "recovered_amount_rupees >= 0",
            name=(
                "recovery_case_"
                "recovered_amount_non_negative"
            ),
        ),
        CheckConstraint(
            "recovered_amount_rupees "
            "<= original_amount_rupees",
            name=(
                "recovery_case_"
                "recovered_within_original"
            ),
        ),
        CheckConstraint(
            "intervention_cost_rupees >= 0",
            name=(
                "recovery_case_"
                "intervention_cost_non_negative"
            ),
        ),
        Index(
            "recovery_case_state_next_action_index",
            "current_state",
            "next_action_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Original failed Razorpay payment.
    provider_payment_id: Mapped[
        str | None
    ] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # New captured Razorpay payment that recovered
    # the failed amount. The original failed payment
    # ID is never overwritten.
    recovered_provider_payment_id: Mapped[
        str | None
    ] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )

    provider_subscription_id: Mapped[
        str | None
    ] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    provider_customer_id: Mapped[
        str | None
    ] = mapped_column(
        String(128),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )

    original_amount_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    recoverable_amount_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    recovered_amount_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    intervention_cost_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    failure_category: Mapped[
        FailureCategory | None
    ] = mapped_column(
        SqlEnum(
            FailureCategory,
            name="failure_category",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=True,
    )

    current_state: Mapped[
        RecoveryCaseState
    ] = mapped_column(
        SqlEnum(
            RecoveryCaseState,
            name="recovery_case_state",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=False,
        default=RecoveryCaseState.DETECTED,
        index=True,
    )

    state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    communication_count: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    next_action_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    recovery_deadline_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    recovered_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    closed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )