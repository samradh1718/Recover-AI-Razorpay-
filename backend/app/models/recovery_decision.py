from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import (
    UUID as PostgreSQLUUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.enums import (
    PolicyResult,
    RecoveryActionType,
    RecoveryDecisionStatus,
)
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


recovery_action_enum = SqlEnum(
    RecoveryActionType,
    name="recovery_action_type",
    values_callable=lambda enum_class: [
        item.value for item in enum_class
    ],
)


class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"

    __table_args__ = (
        UniqueConstraint(
            "recovery_case_id",
            "case_state_version",
            name=(
                "uq_recovery_decision_"
                "case_state_version"
            ),
        ),
        UniqueConstraint(
            "provider_action_id",
            name=(
                "uq_recovery_decision_"
                "provider_action_id"
            ),
        ),
        UniqueConstraint(
            "provider_reference_id",
            name=(
                "uq_recovery_decision_"
                "provider_reference_id"
            ),
        ),
        CheckConstraint(
            "execution_mode IS NULL "
            "OR execution_mode IN "
            "('simulated', 'razorpay_test')",
            name=(
                "recovery_decision_"
                "execution_mode_allowed"
            ),
        ),
        CheckConstraint(
            "recovery_probability >= 0 "
            "AND recovery_probability <= 1",
            name=(
                "recovery_decision_"
                "probability_range"
            ),
        ),
        CheckConstraint(
            "expected_recovery_rupees >= 0",
            name=(
                "recovery_decision_"
                "expected_recovery_non_negative"
            ),
        ),
        CheckConstraint(
            "estimated_action_cost_rupees >= 0",
            name=(
                "recovery_decision_"
                "action_cost_non_negative"
            ),
        ),
        Index(
            "recovery_decision_case_created_index",
            "recovery_case_id",
            "created_at",
        ),
        Index(
            "recovery_decision_status_schedule_index",
            "status",
            "scheduled_for",
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

    recovery_case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "recovery_cases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    case_state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    recommended_action: Mapped[
        RecoveryActionType
    ] = mapped_column(
        recovery_action_enum,
        nullable=False,
    )

    final_action: Mapped[
        RecoveryActionType | None
    ] = mapped_column(
        recovery_action_enum,
        nullable=True,
    )

    policy_result: Mapped[
        PolicyResult
    ] = mapped_column(
        SqlEnum(
            PolicyResult,
            name="policy_result",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=False,
        default=PolicyResult.PENDING,
    )

    status: Mapped[
        RecoveryDecisionStatus
    ] = mapped_column(
        SqlEnum(
            RecoveryDecisionStatus,
            name="recovery_decision_status",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=False,
        default=RecoveryDecisionStatus.PROPOSED,
        index=True,
    )

    recovery_probability: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    expected_recovery_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    estimated_action_cost_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    expected_net_value_rupees: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    reason_codes: Mapped[
        list[str]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    decision_inputs: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    alternatives: Mapped[
        list[dict[str, Any]]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    model_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="rules_v1",
    )

    # Records whether the action was simulated or
    # executed through Razorpay Test Mode.
    execution_mode: Mapped[
        str | None
    ] = mapped_column(
        String(32),
        nullable=True,
    )

    # Razorpay Payment Link ID, such as:
    # plink_Abc123...
    provider_action_id: Mapped[
        str | None
    ] = mapped_column(
        String(128),
        nullable=True,
    )

    # Our deterministic reference sent to Razorpay.
    # Razorpay permits a maximum of 40 characters.
    provider_reference_id: Mapped[
        str | None
    ] = mapped_column(
        String(40),
        nullable=True,
    )

    # Hosted Razorpay Payment Link URL.
    provider_action_url: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    # Provider status, for example:
    # created, paid, cancelled or expired.
    provider_action_status: Mapped[
        str | None
    ] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    # Auditable copy of the provider response.
    # No API secret is stored here.
    provider_response: Mapped[
        dict[str, Any] | None
    ] = mapped_column(
        JSONB,
        nullable=True,
    )

    scheduled_for: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    executed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )