from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    RecoveryCaseState,
    RecoveryDecisionStatus,
)
from app.models import (
    RecoveryCase,
    RecoveryDecision,
)
from app.services.razorpay_payment_link_service import (
    fetch_payment_link,
)


PAISE_PER_RUPEE = Decimal("100")
MONEY_PRECISION = Decimal("0.01")


class PaymentLinkReconciliationError(Exception):
    """Base exception for reconciliation failures."""


class RecoveryDecisionNotFoundError(
    PaymentLinkReconciliationError
):
    """Raised when the recovery decision does not exist."""


class PaymentLinkNotAvailableError(
    PaymentLinkReconciliationError
):
    """Raised when the decision has no provider Payment Link."""


class PaymentLinkReferenceMismatchError(
    PaymentLinkReconciliationError
):
    """Raised when Razorpay returns an unexpected reference."""


class PaymentLinkAmountMismatchError(
    PaymentLinkReconciliationError
):
    """Raised when the provider paid amount is unexpected."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def paise_to_rupees(
    amount_paise: int,
) -> Decimal:
    if (
        isinstance(amount_paise, bool)
        or not isinstance(amount_paise, int)
    ):
        raise PaymentLinkAmountMismatchError(
            "Provider paid amount must be an integer"
        )

    if amount_paise < 0:
        raise PaymentLinkAmountMismatchError(
            "Provider paid amount cannot be negative"
        )

    return (
        Decimal(amount_paise)
        / PAISE_PER_RUPEE
    ).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


def cancel_pending_decisions(
    database: Session,
    recovery_case_id: UUID,
    current_decision_id: UUID,
    now: datetime,
) -> None:
    pending_decisions = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.recovery_case_id
            == recovery_case_id,
            RecoveryDecision.id
            != current_decision_id,
            RecoveryDecision.status.in_(
                [
                    RecoveryDecisionStatus.PROPOSED,
                    RecoveryDecisionStatus.SCHEDULED,
                ]
            ),
        )
        .with_for_update()
    ).scalars().all()

    for pending_decision in pending_decisions:
        pending_decision.status = (
            RecoveryDecisionStatus.CANCELLED
        )
        pending_decision.scheduled_for = None
        pending_decision.updated_at = now


def reconciliation_result(
    *,
    status: str,
    decision: RecoveryDecision,
    recovery_case: RecoveryCase,
) -> dict[str, Any]:
    return {
        "status": status,
        "decision_id": str(decision.id),
        "case_id": str(recovery_case.id),
        "provider_payment_id": (
            recovery_case.provider_payment_id
        ),
        "provider_action_status": (
            decision.provider_action_status
        ),
        "case_state": (
            recovery_case.current_state.value
        ),
        "recoverable_amount_rupees": str(
            recovery_case.recoverable_amount_rupees
        ),
        "recovered_amount_rupees": str(
            recovery_case.recovered_amount_rupees
        ),
        "execution_mode": (
            decision.execution_mode
        ),
    }


def reconcile_payment_link(
    database: Session,
    decision_id: UUID,
) -> dict[str, Any]:
    """Reconcile one recovery decision with Razorpay.

    Razorpay is queried before database rows are locked so an
    external network request does not hold a PostgreSQL row lock.
    """

    initial_decision = database.execute(
        select(RecoveryDecision).where(
            RecoveryDecision.id == decision_id
        )
    ).scalar_one_or_none()

    if initial_decision is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery decision was not found"
        )

    provider_action_id = (
        initial_decision.provider_action_id
    )

    expected_reference_id = (
        initial_decision.provider_reference_id
    )

    recovery_case_id = (
        initial_decision.recovery_case_id
    )

    if not provider_action_id:
        raise PaymentLinkNotAvailableError(
            "Recovery decision does not have "
            "a Razorpay Payment Link"
        )

    # End the initial read transaction before calling Razorpay.
    database.rollback()

    provider_result = fetch_payment_link(
        provider_action_id=provider_action_id
    )

    returned_reference_id = provider_result[
        "provider_reference_id"
    ]

    if (
        expected_reference_id is not None
        and returned_reference_id
        != expected_reference_id
    ):
        raise PaymentLinkReferenceMismatchError(
            "Razorpay Payment Link reference "
            "does not match the recovery decision"
        )

    decision = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision.id == decision_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if decision is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery decision was not found"
        )

    recovery_case = database.execute(
        select(RecoveryCase)
        .where(
            RecoveryCase.id == recovery_case_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery case was not found"
        )

    if (
        decision.provider_action_id
        != provider_result["provider_action_id"]
    ):
        database.rollback()

        raise PaymentLinkReferenceMismatchError(
            "Provider action changed during reconciliation"
        )

    if (
        decision.provider_reference_id is not None
        and decision.provider_reference_id
        != returned_reference_id
    ):
        database.rollback()

        raise PaymentLinkReferenceMismatchError(
            "Provider reference changed during reconciliation"
        )

    decision.execution_mode = "razorpay_test"
    decision.provider_reference_id = (
        returned_reference_id
    )
    decision.provider_action_url = provider_result[
        "provider_action_url"
    ]
    decision.provider_action_status = provider_result[
        "provider_action_status"
    ]
    existing_provider_response = (
        decision.provider_response
    )

    new_provider_response = (
        provider_result.get(
            "provider_response"
        )
    )

    if isinstance(
        new_provider_response,
        dict,
    ):
        merged_provider_response = dict(
            new_provider_response
        )
    else:
        merged_provider_response = {}

    # Preserve RecoverAI-owned audit metadata when a fresh
    # Razorpay status snapshot replaces provider fields.
    if isinstance(
        existing_provider_response,
        dict,
    ):
        notification_metadata = (
            existing_provider_response.get(
                "recoverai_notification"
            )
        )

        if isinstance(
            notification_metadata,
            dict,
        ):
            merged_provider_response[
                "recoverai_notification"
            ] = dict(
                notification_metadata
            )

    decision.provider_response = (
        merged_provider_response
    )
    decision.updated_at = utc_now()

    provider_status = str(
        provider_result["provider_action_status"]
    ).lower()

    if provider_status != "paid":
        database.commit()
        database.refresh(decision)
        database.refresh(recovery_case)

        return reconciliation_result(
            status="provider_not_paid",
            decision=decision,
            recovery_case=recovery_case,
        )

    provider_currency = str(
        provider_result["currency"]
    ).upper()

    case_currency = str(
        recovery_case.currency
    ).upper()

    if provider_currency != case_currency:
        database.rollback()

        raise PaymentLinkAmountMismatchError(
            "Provider currency does not match "
            "the recovery case currency"
        )

    paid_amount_rupees = paise_to_rupees(
        int(
            provider_result[
                "amount_paid_paise"
            ]
        )
    )

    recoverable_amount = Decimal(
        str(
            recovery_case
            .recoverable_amount_rupees
        )
    ).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )

    if paid_amount_rupees != recoverable_amount:
        database.rollback()

        raise PaymentLinkAmountMismatchError(
            "Provider paid amount does not match "
            "the recoverable amount"
        )

    if (
        recovery_case.current_state
        == RecoveryCaseState.RECOVERED
        and Decimal(
            str(
                recovery_case
                .recovered_amount_rupees
            )
        )
        == recoverable_amount
    ):
        database.commit()
        database.refresh(decision)
        database.refresh(recovery_case)

        return reconciliation_result(
            status="already_recovered",
            decision=decision,
            recovery_case=recovery_case,
        )

    now = utc_now()

    recovery_case.current_state = (
        RecoveryCaseState.RECOVERED
    )
    recovery_case.recovered_amount_rupees = (
        recoverable_amount
    )
    recovery_case.recovered_at = now
    recovery_case.closed_at = now
    recovery_case.next_action_at = None
    recovery_case.state_version += 1
    recovery_case.updated_at = now

    cancel_pending_decisions(
        database=database,
        recovery_case_id=recovery_case.id,
        current_decision_id=decision.id,
        now=now,
    )

    database.commit()
    database.refresh(decision)
    database.refresh(recovery_case)

    return reconciliation_result(
        status="recovered",
        decision=decision,
        recovery_case=recovery_case,
    )