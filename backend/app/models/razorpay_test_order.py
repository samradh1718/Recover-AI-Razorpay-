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
    Numeric,
    String,
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


class RazorpayTestOrder(Base):
    """Provider-generated Test Mode checkout attempt.

    This table keeps Test Checkout telemetry separate from
    synthetic webhook fixtures and from future Live Mode data.
    """

    __tablename__ = "razorpay_test_orders"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_order_id",
            name=(
                "uq_razorpay_test_orders_provider_order"
            ),
        ),
        UniqueConstraint(
            "provider",
            "receipt",
            name=(
                "uq_razorpay_test_orders_provider_receipt"
            ),
        ),
        CheckConstraint(
            "amount_rupees > 0",
            name=(
                "ck_razorpay_test_orders_positive_amount"
            ),
        ),
        CheckConstraint(
            "data_source = 'razorpay_test_checkout'",
            name=(
                "ck_razorpay_test_orders_data_source"
            ),
        ),
        CheckConstraint(
            "provider_generated = true",
            name=(
                "ck_razorpay_test_orders_provider_generated"
            ),
        ),
        CheckConstraint(
            "real_money = false",
            name=(
                "ck_razorpay_test_orders_not_real_money"
            ),
        ),
        Index(
            "razorpay_test_order_tenant_created_index",
            "tenant_id",
            "created_at",
        ),
        Index(
            "razorpay_test_order_outcome_created_index",
            "outcome_status",
            "created_at",
        ),
        Index(
            "razorpay_test_order_payment_index",
            "provider_payment_id",
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

    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="razorpay",
    )

    provider_order_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    receipt: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    amount_rupees: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )

    provider_order_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="created",
    )

    data_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="razorpay_test_checkout",
    )

    provider_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    real_money: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # This must be an opaque demo identifier, not an email,
    # phone number or other raw customer PII.
    customer_reference: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # The latest provider payment attempt for this order.
    # One Razorpay order may have more than one failed attempt.
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    latest_payment_event_id: Mapped[
        UUID | None
    ] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "payment_events.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    outcome_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )

    provider_response: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    completed_at: Mapped[
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