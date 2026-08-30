from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PostgreSQLUUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.contracts.enums import (
    HumanReviewOutcome,
    RecoveryActionType,
)
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HumanReviewResolution(Base):
    __tablename__ = "human_review_resolutions"

    __table_args__ = (
        UniqueConstraint(
            "source_decision_id",
            name=(
                "uq_human_review_resolution_"
                "source_decision"
            ),
        ),
        UniqueConstraint(
            "resulting_decision_id",
            name=(
                "uq_human_review_resolution_"
                "resulting_decision"
            ),
        ),
        CheckConstraint(
            "case_state_version_before >= 0",
            name=(
                "human_review_resolution_"
                "version_before_non_negative"
            ),
        ),
        CheckConstraint(
            "case_state_version_after = "
            "case_state_version_before + 1",
            name=(
                "human_review_resolution_"
                "version_transition"
            ),
        ),
        CheckConstraint(
            "("
            "outcome = 'approved' "
            "AND selected_action IN ("
            "'retry_payment', "
            "'send_payment_link', "
            "'request_payment_method_update', "
            "'request_customer_authorization'"
            ")"
            ") OR ("
            "outcome = 'rejected' "
            "AND selected_action = 'stop_recovery'"
            ")",
            name=(
                "human_review_resolution_"
                "outcome_action_consistent"
            ),
        ),
        Index(
            "human_review_resolution_case_created_index",
            "recovery_case_id",
            "created_at",
        ),
        Index(
            "human_review_resolution_tenant_created_index",
            "tenant_id",
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

    source_decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "recovery_decisions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    resulting_decision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "recovery_decisions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    case_state_version_before: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )

    case_state_version_after: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )

    outcome: Mapped[
        HumanReviewOutcome
    ] = mapped_column(
        SqlEnum(
            HumanReviewOutcome,
            name="human_review_outcome",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=False,
    )

    selected_action: Mapped[
        RecoveryActionType
    ] = mapped_column(
        SqlEnum(
            RecoveryActionType,
            name="recovery_action_type",
            values_callable=lambda enum_class: [
                item.value for item in enum_class
            ],
        ),
        nullable=False,
    )

    reviewer_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    reviewer_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )