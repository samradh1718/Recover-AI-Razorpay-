from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    FailureCategory,
    RecoveryCaseState,
    RecoveryDecisionStatus,
)
from app.models.payment_event import PaymentEvent
from app.models.recovery_case import RecoveryCase
from app.models.recovery_decision import RecoveryDecision


PAISE_PER_RUPEE = Decimal("100")
MONEY_PRECISION = Decimal("0.01")

EVALUABLE_STATES = {
    RecoveryCaseState.DETECTED,
    RecoveryCaseState.DIAGNOSED,
    RecoveryCaseState.EVALUATING,
    RecoveryCaseState.READY,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def convert_paise_to_rupees(
    amount_paise: int,
) -> Decimal:
    if isinstance(amount_paise, bool):
        raise ValueError(
            "Payment amount must be an integer"
        )

    if not isinstance(amount_paise, int):
        raise ValueError(
            "Payment amount must be an integer"
        )

    if amount_paise < 0:
        raise ValueError(
            "Payment amount cannot be negative"
        )

    return (
        Decimal(amount_paise)
        / PAISE_PER_RUPEE
    ).quantize(MONEY_PRECISION)


def get_payment_entity(
    payload: dict[str, Any],
) -> dict[str, Any]:
    payment_entity = (
        payload
        .get("payload", {})
        .get("payment", {})
        .get("entity")
    )

    if not isinstance(payment_entity, dict):
        raise ValueError(
            "Payment entity is missing from "
            "webhook payload"
        )

    return payment_entity


def get_payment_link_entity(
    payload: dict[str, Any],
) -> dict[str, Any]:
    payment_link_entity = (
        payload
        .get("payload", {})
        .get("payment_link", {})
        .get("entity")
    )

    if not isinstance(
        payment_link_entity,
        dict,
    ):
        raise ValueError(
            "Payment Link entity is missing "
            "from webhook payload"
        )

    return payment_link_entity


def classify_payment_failure(
    payment_entity: dict[str, Any],
) -> FailureCategory:
    error_reason = str(
        payment_entity.get("error_reason") or ""
    ).lower()

    error_code = str(
        payment_entity.get("error_code") or ""
    ).lower()

    combined_error = (
        f"{error_reason} {error_code}"
    )

    if "insufficient" in combined_error:
        return (
            FailureCategory.INSUFFICIENT_FUNDS
        )

    invalid_method_terms = (
        "expired_card",
        "card_expired",
        "invalid_card",
        "invalid_payment_method",
    )

    if any(
        term in combined_error
        for term in invalid_method_terms
    ):
        return (
            FailureCategory
            .INVALID_OR_EXPIRED_METHOD
        )

    authorization_terms = (
        "incorrect_otp",
        "authentication",
        "authorization",
        "mandate",
    )

    if any(
        term in combined_error
        for term in authorization_terms
    ):
        return (
            FailureCategory
            .MANDATE_OR_AUTHORIZATION
        )

    temporary_terms = (
        "timeout",
        "timed_out",
        "gateway",
        "bank",
        "server",
        "technical",
    )

    if any(
        term in combined_error
        for term in temporary_terms
    ):
        return (
            FailureCategory
            .TEMPORARY_GATEWAY_OR_BANK
        )

    return FailureCategory.UNKNOWN


def find_payment_link_decision(
    database: Session,
    tenant_id: UUID,
    payment_link_entity: dict[str, Any],
    *,
    lock: bool = False,
) -> RecoveryDecision | None:
    provider_action_id = (
        payment_link_entity.get("id")
    )

    provider_reference_id = (
        payment_link_entity.get(
            "reference_id"
        )
    )

    if isinstance(provider_action_id, str):
        statement = select(
            RecoveryDecision
        ).where(
            RecoveryDecision.tenant_id
            == tenant_id,
            RecoveryDecision.provider_action_id
            == provider_action_id,
        )

        if lock:
            statement = (
                statement.with_for_update()
            )

        decision = database.execute(
            statement
        ).scalar_one_or_none()

        if decision is not None:
            return decision

    if isinstance(
        provider_reference_id,
        str,
    ):
        statement = select(
            RecoveryDecision
        ).where(
            RecoveryDecision.tenant_id
            == tenant_id,
            RecoveryDecision
            .provider_reference_id
            == provider_reference_id,
        )

        if lock:
            statement = (
                statement.with_for_update()
            )

        return database.execute(
            statement
        ).scalar_one_or_none()

    return None


def find_recovery_case_for_event(
    database: Session,
    event: PaymentEvent,
) -> RecoveryCase | None:
    if event.event_type == "payment_link.paid":
        try:
            payment_link_entity = (
                get_payment_link_entity(
                    event.payload
                )
            )
        except ValueError:
            return None

        decision = find_payment_link_decision(
            database=database,
            tenant_id=event.tenant_id,
            payment_link_entity=(
                payment_link_entity
            ),
        )

        if decision is None:
            return None

        return database.execute(
            select(RecoveryCase).where(
                RecoveryCase.id
                == decision.recovery_case_id
            )
        ).scalar_one_or_none()

    if event.event_type not in {
        "payment.failed",
        "payment.captured",
    }:
        return None

    try:
        payment_entity = get_payment_entity(
            event.payload
        )
    except ValueError:
        return None

    provider_payment_id = (
        payment_entity.get("id")
    )

    if not isinstance(
        provider_payment_id,
        str,
    ):
        return None

    return database.execute(
        select(RecoveryCase).where(
            RecoveryCase.tenant_id
            == event.tenant_id,
            RecoveryCase.provider_payment_id
            == provider_payment_id,
        )
    ).scalar_one_or_none()


def captured_event_exists(
    database: Session,
    tenant_id: UUID,
    provider_payment_id: str,
    current_event_id: UUID,
) -> bool:
    captured_event_id = database.execute(
        select(PaymentEvent.id)
        .where(
            PaymentEvent.tenant_id
            == tenant_id,
            PaymentEvent.provider_payment_id
            == provider_payment_id,
            PaymentEvent.event_type
            == "payment.captured",
            PaymentEvent.id
            != current_event_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    return captured_event_id is not None


def cancel_pending_decisions(
    database: Session,
    recovery_case: RecoveryCase,
    now: datetime,
) -> int:
    pending_decisions = list(
        database.execute(
            select(RecoveryDecision).where(
                RecoveryDecision.recovery_case_id
                == recovery_case.id,
                RecoveryDecision.status.in_(
                    [
                        RecoveryDecisionStatus
                        .PROPOSED,
                        RecoveryDecisionStatus
                        .SCHEDULED,
                    ]
                ),
            )
        ).scalars()
    )

    for pending_decision in pending_decisions:
        pending_decision.status = (
            RecoveryDecisionStatus.CANCELLED
        )
        pending_decision.scheduled_for = None
        pending_decision.updated_at = now

    return len(pending_decisions)


def process_payment_link_paid(
    database: Session,
    event: PaymentEvent,
) -> dict[str, str]:
    payment_link_entity = (
        get_payment_link_entity(
            event.payload
        )
    )

    decision = find_payment_link_decision(
        database=database,
        tenant_id=event.tenant_id,
        payment_link_entity=(
            payment_link_entity
        ),
        lock=True,
    )

    now = utc_now()

    if decision is None:
        event.processing_status = "ignored"
        event.processing_error = None
        event.processed_at = now

        database.commit()

        return {
            "status": "ignored",
            "reason": (
                "no_matching_provider_action"
            ),
            "event_id": str(event.id),
        }

    recovery_case = database.execute(
        select(RecoveryCase)
        .where(
            RecoveryCase.id
            == decision.recovery_case_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise ValueError(
            "Recovery case for Payment Link "
            "was not found"
        )

    provider_action_id = (
        payment_link_entity.get("id")
    )

    provider_reference_id = (
        payment_link_entity.get(
            "reference_id"
        )
    )

    provider_action_url = (
        payment_link_entity.get(
            "short_url"
        )
    )

    provider_status = str(
        payment_link_entity.get("status")
        or "paid"
    ).lower()

    if provider_status != "paid":
        raise ValueError(
            "payment_link.paid webhook does "
            "not contain paid status"
        )

    if isinstance(provider_action_id, str):
        decision.provider_action_id = (
            provider_action_id
        )

    if isinstance(
        provider_reference_id,
        str,
    ):
        decision.provider_reference_id = (
            provider_reference_id
        )

    if isinstance(
        provider_action_url,
        str,
    ):
        decision.provider_action_url = (
            provider_action_url
        )

    decision.provider_action_status = "paid"
    decision.execution_mode = "razorpay_test"
    decision.updated_at = now

    amount_paid_paise = (
        payment_link_entity.get(
            "amount_paid"
        )
    )

    payment_entity: dict[str, Any] | None

    try:
        payment_entity = get_payment_entity(
            event.payload
        )
    except ValueError:
        payment_entity = None

    if (
        not isinstance(
            amount_paid_paise,
            int,
        )
        or isinstance(
            amount_paid_paise,
            bool,
        )
    ):
        if payment_entity is None:
            raise ValueError(
                "Paid amount is missing from "
                "Payment Link webhook"
            )

        amount_paid_paise = (
            payment_entity.get("amount")
        )

    recovered_amount_rupees = (
        convert_paise_to_rupees(
            amount_paid_paise
        )
    )

    recoverable_amount_rupees = Decimal(
        str(
            recovery_case
            .recoverable_amount_rupees
        )
    )

    recovered_amount_rupees = min(
        recovered_amount_rupees,
        recoverable_amount_rupees,
    )

    provider_snapshot: dict[str, Any] = {}

    if isinstance(
        decision.provider_response,
        dict,
    ):
        provider_snapshot.update(
            decision.provider_response
        )

    provider_snapshot.update(
        {
            "id": decision.provider_action_id,
            "reference_id": (
                decision.provider_reference_id
            ),
            "short_url": (
                decision.provider_action_url
            ),
            "status": "paid",
            "amount_paid": amount_paid_paise,
        }
    )

    if payment_entity is not None:
        paid_payment_id = (
            payment_entity.get("id")
        )

        if isinstance(paid_payment_id, str):
            provider_snapshot[
                "paid_payment_id"
            ] = paid_payment_id

    decision.provider_response = (
        provider_snapshot
    )

    if (
        recovery_case.current_state
        == RecoveryCaseState.RECOVERED
    ):
        event.processing_status = "processed"
        event.processing_error = None
        event.processed_at = now

        database.commit()

        return {
            "status": "already_recovered",
            "event_id": str(event.id),
            "case_id": str(recovery_case.id),
            "decision_id": str(decision.id),
            "case_state": (
                RecoveryCaseState
                .RECOVERED
                .value
            ),
        }

    recovery_case.recovered_amount_rupees = (
        recovered_amount_rupees
    )
    recovery_case.current_state = (
        RecoveryCaseState.RECOVERED
    )
    recovery_case.recovered_at = now
    recovery_case.closed_at = now
    recovery_case.next_action_at = None
    recovery_case.state_version += 1
    recovery_case.updated_at = now

    cancelled_decisions = (
        cancel_pending_decisions(
            database=database,
            recovery_case=recovery_case,
            now=now,
        )
    )

    event.processing_status = "processed"
    event.processing_error = None
    event.processed_at = now

    database.commit()

    return {
        "status": "recovered",
        "event_id": str(event.id),
        "case_id": str(recovery_case.id),
        "decision_id": str(decision.id),
        "case_state": (
            RecoveryCaseState.RECOVERED.value
        ),
        "provider_action_status": "paid",
        "recovered_amount_rupees": str(
            recovered_amount_rupees
        ),
        "cancelled_decisions": str(
            cancelled_decisions
        ),
    }


def process_captured_payment(
    database: Session,
    event: PaymentEvent,
    payment_entity: dict[str, Any],
) -> dict[str, str]:
    recovery_case = (
        find_recovery_case_for_event(
            database=database,
            event=event,
        )
    )

    now = utc_now()

    if recovery_case is None:
        event.processing_status = "ignored"
        event.processing_error = None
        event.processed_at = now

        database.commit()

        return {
            "status": "ignored",
            "reason": "no_recovery_case",
            "event_id": str(event.id),
        }

    if (
        recovery_case.current_state
        == RecoveryCaseState.RECOVERED
    ):
        event.processing_status = "processed"
        event.processing_error = None
        event.processed_at = now

        database.commit()

        return {
            "status": "already_recovered",
            "event_id": str(event.id),
            "case_id": str(recovery_case.id),
            "case_state": (
                RecoveryCaseState
                .RECOVERED
                .value
            ),
        }

    captured_amount_rupees = (
        convert_paise_to_rupees(
            payment_entity.get("amount")
        )
    )

    recovery_case.recovered_amount_rupees = (
        min(
            captured_amount_rupees,
            recovery_case
            .recoverable_amount_rupees,
        )
    )
    recovery_case.current_state = (
        RecoveryCaseState.RECOVERED
    )
    recovery_case.recovered_at = now
    recovery_case.closed_at = now
    recovery_case.next_action_at = None
    recovery_case.state_version += 1
    recovery_case.updated_at = now

    cancelled_decisions = (
        cancel_pending_decisions(
            database=database,
            recovery_case=recovery_case,
            now=now,
        )
    )

    event.processing_status = "processed"
    event.processing_error = None
    event.processed_at = now

    database.commit()

    return {
        "status": "recovered",
        "event_id": str(event.id),
        "case_id": str(recovery_case.id),
        "case_state": (
            RecoveryCaseState.RECOVERED.value
        ),
        "recovered_amount_rupees": str(
            recovery_case
            .recovered_amount_rupees
        ),
        "cancelled_decisions": str(
            cancelled_decisions
        ),
    }


def process_payment_event(
    database: Session,
    event_id: UUID,
) -> dict[str, str]:
    try:
        event = database.execute(
            select(PaymentEvent)
            .where(
                PaymentEvent.id == event_id
            )
            .with_for_update()
        ).scalar_one_or_none()

        if event is None:
            raise ValueError(
                f"Payment event {event_id} "
                "was not found"
            )

        if event.processing_status in {
            "processed",
            "ignored",
        }:
            result = {
                "status": (
                    event.processing_status
                ),
                "event_id": str(event.id),
            }

            existing_case = (
                find_recovery_case_for_event(
                    database=database,
                    event=event,
                )
            )

            if existing_case is not None:
                result["case_id"] = str(
                    existing_case.id
                )

                if (
                    event.event_type
                    == "payment.failed"
                    and existing_case
                    .current_state
                    in EVALUABLE_STATES
                ):
                    result[
                        "should_evaluate"
                    ] = "true"

            return result

        event.processing_status = "processing"
        event.processing_error = None
        database.flush()

        if (
            event.event_type
            == "payment_link.paid"
        ):
            return process_payment_link_paid(
                database=database,
                event=event,
            )

        if (
            event.event_type
            == "payment.captured"
        ):
            payment_entity = (
                get_payment_entity(
                    event.payload
                )
            )

            return process_captured_payment(
                database=database,
                event=event,
                payment_entity=payment_entity,
            )

        if event.event_type != "payment.failed":
            event.processing_status = "ignored"
            event.processing_error = None
            event.processed_at = utc_now()

            database.commit()

            return {
                "status": "ignored",
                "event_id": str(event.id),
            }

        payment_entity = get_payment_entity(
            event.payload
        )

        provider_payment_id = (
            payment_entity.get("id")
        )

        if not isinstance(
            provider_payment_id,
            str,
        ):
            raise ValueError(
                "Payment ID is missing "
                "from the event"
            )

        amount_paise = payment_entity.get(
            "amount"
        )

        amount_rupees = (
            convert_paise_to_rupees(
                amount_paise
            )
        )

        currency = str(
            payment_entity.get("currency")
            or "INR"
        ).upper()

        if captured_event_exists(
            database=database,
            tenant_id=event.tenant_id,
            provider_payment_id=(
                provider_payment_id
            ),
            current_event_id=event.id,
        ):
            event.processing_status = "ignored"
            event.processing_error = None
            event.processed_at = utc_now()

            database.commit()

            return {
                "status": "ignored",
                "reason": (
                    "payment_already_captured"
                ),
                "event_id": str(event.id),
            }

        existing_case = database.execute(
            select(RecoveryCase).where(
                RecoveryCase.tenant_id
                == event.tenant_id,
                RecoveryCase.provider_payment_id
                == provider_payment_id,
            )
        ).scalar_one_or_none()

        if existing_case is not None:
            event.processing_status = "processed"
            event.processing_error = None
            event.processed_at = utc_now()

            database.commit()

            result = {
                "status": "already_exists",
                "event_id": str(event.id),
                "case_id": str(
                    existing_case.id
                ),
            }

            if (
                existing_case.current_state
                in EVALUABLE_STATES
            ):
                result[
                    "should_evaluate"
                ] = "true"

            return result

        failure_category = (
            classify_payment_failure(
                payment_entity
            )
        )

        recovery_case = RecoveryCase(
            tenant_id=event.tenant_id,
            provider_payment_id=(
                provider_payment_id
            ),
            provider_subscription_id=(
                payment_entity.get(
                    "subscription_id"
                )
            ),
            provider_customer_id=(
                payment_entity.get(
                    "customer_id"
                )
            ),
            currency=currency,
            original_amount_rupees=(
                amount_rupees
            ),
            recoverable_amount_rupees=(
                amount_rupees
            ),
            recovered_amount_rupees=(
                Decimal("0.00")
            ),
            intervention_cost_rupees=(
                Decimal("0.00")
            ),
            failure_category=(
                failure_category
            ),
            current_state=(
                RecoveryCaseState.DETECTED
            ),
            state_version=0,
            attempt_count=0,
            communication_count=0,
            recovery_deadline_at=(
                utc_now()
                + timedelta(days=7)
            ),
        )

        database.add(recovery_case)

        event.processing_status = "processed"
        event.processing_error = None
        event.processed_at = utc_now()

        database.commit()
        database.refresh(recovery_case)

        return {
            "status": "processed",
            "event_id": str(event.id),
            "case_id": str(recovery_case.id),
            "should_evaluate": "true",
        }

    except Exception as error:
        database.rollback()

        failed_event = database.get(
            PaymentEvent,
            event_id,
        )

        if failed_event is not None:
            failed_event.processing_status = (
                "failed"
            )
            failed_event.processing_error = str(
                error
            )[:1000]
            failed_event.processed_at = utc_now()

            database.commit()

        raise