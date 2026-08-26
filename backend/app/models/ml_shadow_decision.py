from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MLShadowDecision(Base):
    __tablename__ = "ml_shadow_decisions"

    __table_args__ = (
        UniqueConstraint(
            "production_decision_id",
            "model_name",
            "model_version",
            name=(
                "uq_ml_shadow_production_model_version"
            ),
        ),
        CheckConstraint(
            "status IN "
            "('pending', 'completed', 'failed', 'invalid')",
            name="ml_shadow_status_allowed",
        ),
        CheckConstraint(
            "selected_action IS NULL OR "
            "selected_action IN ("
            "'retry_payment', "
            "'send_payment_link', "
            "'request_payment_method_update', "
            "'request_customer_authorization', "
            "'human_review', "
            "'stop_recovery'"
            ")",
            name="ml_shadow_action_allowed",
        ),
        CheckConstraint(
            "raw_probability IS NULL OR "
            "(raw_probability >= 0 "
            "AND raw_probability <= 1)",
            name="ml_shadow_raw_probability_range",
        ),
        CheckConstraint(
            "calibrated_probability IS NULL OR "
            "(calibrated_probability >= 0 "
            "AND calibrated_probability <= 1)",
            name=(
                "ml_shadow_calibrated_probability_range"
            ),
        ),
        CheckConstraint(
            "expected_recovery_rupees IS NULL OR "
            "expected_recovery_rupees >= 0",
            name="ml_shadow_expected_recovery_non_negative",
        ),
        CheckConstraint(
            "estimated_action_cost_rupees IS NULL OR "
            "estimated_action_cost_rupees >= 0",
            name="ml_shadow_action_cost_non_negative",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ml_shadow_latency_non_negative",
        ),
        Index(
            "ml_shadow_case_created_index",
            "recovery_case_id",
            "created_at",
        ),
        Index(
            "ml_shadow_agreement_created_index",
            "agrees_with_production",
            "created_at",
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

    production_decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "recovery_decisions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    case_state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="catboost",
    )

    model_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="catboost_v1_synthetic",
    )

    calibration_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="platt",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )

    selected_action: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    raw_probability: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    calibrated_probability: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    expected_recovery_rupees: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    estimated_action_cost_rupees: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    expected_net_value_rupees: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    alternatives: Mapped[
        list[dict[str, Any]]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    input_snapshot: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    agrees_with_production: Mapped[
        bool | None
    ] = mapped_column(
        Boolean,
        nullable=True,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
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