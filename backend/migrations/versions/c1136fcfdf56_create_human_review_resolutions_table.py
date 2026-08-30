"""Create human review resolutions table.

Revision ID: c1136fcfdf56
Revises: 139d8a2e0a15
Create Date: 2026-08-30 07:51:56.986881
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1136fcfdf56"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "139d8a2e0a15"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


human_review_outcome_enum = postgresql.ENUM(
    "approved",
    "rejected",
    name="human_review_outcome",
    create_type=False,
)


recovery_action_type_enum = postgresql.ENUM(
    "retry_payment",
    "send_payment_link",
    "request_payment_method_update",
    "request_customer_authorization",
    "human_review",
    "stop_recovery",
    name="recovery_action_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    human_review_outcome_enum.create(
        bind,
        checkfirst=True,
    )

    op.create_table(
        "human_review_resolutions",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "recovery_case_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "source_decision_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "resulting_decision_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "case_state_version_before",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "case_state_version_after",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            human_review_outcome_enum,
            nullable=False,
        ),
        sa.Column(
            "selected_action",
            recovery_action_type_enum,
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "reviewer_name",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "case_state_version_after = "
            "case_state_version_before + 1",
            name=(
                "human_review_resolution_"
                "version_transition"
            ),
        ),
        sa.CheckConstraint(
            "case_state_version_before >= 0",
            name=(
                "human_review_resolution_"
                "version_before_non_negative"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["recovery_case_id"],
            ["recovery_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_decision_id"],
            ["recovery_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_decision_id"],
            ["recovery_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resulting_decision_id",
            name=(
                "uq_human_review_resolution_"
                "resulting_decision"
            ),
        ),
        sa.UniqueConstraint(
            "source_decision_id",
            name=(
                "uq_human_review_resolution_"
                "source_decision"
            ),
        ),
    )

    op.create_index(
        "human_review_resolution_case_created_index",
        "human_review_resolutions",
        [
            "recovery_case_id",
            "created_at",
        ],
        unique=False,
    )

    op.create_index(
        "human_review_resolution_tenant_created_index",
        "human_review_resolutions",
        [
            "tenant_id",
            "created_at",
        ],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_human_review_resolutions_"
            "recovery_case_id"
        ),
        "human_review_resolutions",
        ["recovery_case_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_human_review_resolutions_"
            "tenant_id"
        ),
        "human_review_resolutions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_human_review_resolutions_"
            "tenant_id"
        ),
        table_name="human_review_resolutions",
    )

    op.drop_index(
        op.f(
            "ix_human_review_resolutions_"
            "recovery_case_id"
        ),
        table_name="human_review_resolutions",
    )

    op.drop_index(
        "human_review_resolution_tenant_created_index",
        table_name="human_review_resolutions",
    )

    op.drop_index(
        "human_review_resolution_case_created_index",
        table_name="human_review_resolutions",
    )

    op.drop_table(
        "human_review_resolutions"
    )

    human_review_outcome_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )