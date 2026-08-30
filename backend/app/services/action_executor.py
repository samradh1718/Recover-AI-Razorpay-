from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    PolicyResult,
    RecoveryActionType,
    RecoveryCaseState,
    RecoveryDecisionStatus,
)
from app.core.config import settings
from app.models import (
    RecoveryCase,
    RecoveryDecision,
)
from app.models.payment_event import PaymentEvent
from app.services.razorpay_payment_link_service import (
    RazorpayPaymentLinkError,
    create_standard_payment_link,
)


MONEY = Decimal("0.01")

TERMINAL_STATES = {
    RecoveryCaseState.RECOVERED,
    RecoveryCaseState.EXHAUSTED,
    RecoveryCaseState.STOPPED,
    RecoveryCaseState.EXPIRED,
}

CUSTOMER_COMMUNICATION_ACTIONS = {
    RecoveryActionType.SEND_PAYMENT_LINK,
    RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE,
    RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION,
}


class RecoveryDecisionNotFoundError(Exception):
    pass


class RecoveryActionNotExecutableError(Exception):
    pass


class RecoveryActionNotDueError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)

def _optional_string(
    value: Any,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()

    return cleaned_value or None


def _is_true_marker(value: Any) -> bool:
    if value is True:
        return True

    if not isinstance(value, str):
        return False

    return value.strip().lower() == "true"


def _is_false_marker(value: Any) -> bool:
    if value is False:
        return True

    if not isinstance(value, str):
        return False

    return value.strip().lower() == "false"


def _is_verified_test_checkout_payment(
    payment_entity: dict[str, Any],
) -> bool:
    if settings.razorpay_mode != "test":
        return False

    if not (
        settings.razorpay_test_checkout_enabled
    ):
        return False

    notes = payment_entity.get("notes")

    if not isinstance(notes, dict):
        return False

    data_source = _optional_string(
        notes.get(
            "recoverai_data_source"
        )
    )

    provider_order_id = _optional_string(
        notes.get(
            "recoverai_provider_order_id"
        )
    )

    test_order_id = _optional_string(
        notes.get(
            "recoverai_test_order_id"
        )
    )

    return (
        data_source == "razorpay_server_api"
        and _is_true_marker(
            notes.get(
                "recoverai_provider_generated"
            )
        )
        and _is_false_marker(
            notes.get(
                "recoverai_real_money"
            )
        )
        and provider_order_id is not None
        and provider_order_id.startswith(
            "order_"
        )
        and test_order_id is not None
    )


def _resolve_customer_recipient(
    database: Session,
    recovery_case: RecoveryCase,
) -> tuple[str | None, str | None]:
    provider_payment_id = (
        recovery_case.provider_payment_id
    )

    if provider_payment_id is None:
        return None, None

    payment_event = database.execute(
        select(PaymentEvent)
        .where(
            PaymentEvent.tenant_id
            == recovery_case.tenant_id,
            PaymentEvent.provider_payment_id
            == provider_payment_id,
            PaymentEvent.event_type
            == "payment.failed",
        )
        .order_by(
            PaymentEvent.received_at.desc()
        )
        .limit(1)
    ).scalar_one_or_none()

    if payment_event is None:
        return None, None

    event_payload = payment_event.payload

    if not isinstance(event_payload, dict):
        return None, None

    provider_payload = event_payload.get(
        "payload"
    )

    if not isinstance(provider_payload, dict):
        return None, None

    payment_container = provider_payload.get(
        "payment"
    )

    if not isinstance(payment_container, dict):
        return None, None

    payment_entity = payment_container.get(
        "entity"
    )

    if not isinstance(payment_entity, dict):
        return None, None

    customer_email = _optional_string(
        payment_entity.get("email")
    )

    customer_contact = _optional_string(
        payment_entity.get("contact")
    )

    if not _is_verified_test_checkout_payment(
        payment_entity
    ):
        return (
            customer_email,
            customer_contact,
        )

    # Server-reconciled Test Checkout evidence is
    # intentionally PII-safe and therefore does not
    # retain the Checkout email/contact. Only for a
    # cryptographically authenticated Razorpay Test Mode
    # order carrying RecoverAI provenance markers may the
    # configured demo recipient be used.
    demo_email = _optional_string(
        settings.demo_customer_email
    )

    demo_contact = _optional_string(
        settings.demo_customer_contact
    )

    return (
        customer_email or demo_email,
        customer_contact or demo_contact,
    )

def _execution_result(
    *,
    status: str,
    decision: RecoveryDecision,
    recovery_case: RecoveryCase,
) -> dict[str, Any]:
    simulated = (
        decision.execution_mode != "razorpay_test"
    )

    return {
        "status": status,
        "decision_id": str(decision.id),
        "case_id": str(recovery_case.id),
        "action": (
            decision.final_action.value
            if decision.final_action is not None
            else None
        ),
        "decision_status": decision.status.value,
        "case_state": (
            recovery_case.current_state.value
        ),
        "attempt_count": (
            recovery_case.attempt_count
        ),
        "communication_count": (
            recovery_case.communication_count
        ),
        "intervention_cost_rupees": str(
            recovery_case
            .intervention_cost_rupees
        ),
        "execution_mode": (
            decision.execution_mode
        ),
        "provider_action_id": (
            decision.provider_action_id
        ),
        "provider_reference_id": (
            decision.provider_reference_id
        ),
        "provider_action_url": (
            decision.provider_action_url
        ),
        "provider_action_status": (
            decision.provider_action_status
        ),
        "simulated": simulated,
    }


def _store_provider_result(
    *,
    decision: RecoveryDecision,
    provider_result: dict[str, Any],
) -> None:
    decision.execution_mode = "razorpay_test"

    decision.provider_action_id = str(
        provider_result[
            "provider_action_id"
        ]
    )

    decision.provider_reference_id = str(
        provider_result[
            "provider_reference_id"
        ]
    )

    decision.provider_action_url = str(
        provider_result[
            "provider_action_url"
        ]
    )

    decision.provider_action_status = str(
        provider_result[
            "provider_action_status"
        ]
    )

    provider_response = provider_result.get(
        "provider_response"
    )

    notification_requested = bool(
        provider_result.get(
            "notification_requested",
            False,
        )
    )

    notification_channel = (
        provider_result.get(
            "notification_channel"
        )
    )

    if not isinstance(
        notification_channel,
        str,
    ):
        notification_channel = None

    if isinstance(provider_response, dict):
        safe_provider_response = dict(
            provider_response
        )

        # This records provider request acceptance,
        # not end-device delivery.
        safe_provider_response[
            "recoverai_notification"
        ] = {
            "requested": (
                notification_requested
            ),
            "channel": notification_channel,
            "status": (
                "request_accepted"
                if notification_requested
                else "disabled"
            ),
        }

        decision.provider_response = (
            safe_provider_response
        )
    else:
        decision.provider_response = {
            "recoverai_notification": {
                "requested": (
                    notification_requested
                ),
                "channel": notification_channel,
                "status": (
                    "request_accepted"
                    if notification_requested
                    else "disabled"
                ),
            }
        }


def execute_recovery_action(
    database: Session,
    decision_id: UUID,
    expected_case_id: UUID | None = None,
) -> dict[str, Any]:
    """Execute one policy-approved action exactly once.

    The production rules and policy engine retain execution
    authority.

    When Razorpay actions are disabled, action execution is
    simulated.

    When Razorpay actions are enabled, eligible customer-facing
    actions create a Standard Payment Link using Razorpay Test
    Mode.
    """

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

    if (
        expected_case_id is not None
        and decision.recovery_case_id
        != expected_case_id
    ):
        raise RecoveryDecisionNotFoundError(
            "Decision does not belong to this "
            "recovery case"
        )

    recovery_case = database.execute(
        select(RecoveryCase)
        .where(
            RecoveryCase.id
            == decision.recovery_case_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery case for this decision "
            "was not found"
        )

    # Idempotency: a completed decision cannot execute again.
    if (
        decision.status
        == RecoveryDecisionStatus.EXECUTED
    ):
        return _execution_result(
            status="already_executed",
            decision=decision,
            recovery_case=recovery_case,
        )

    # Never act on a recovered, stopped or expired case.
    if (
        recovery_case.current_state
        in TERMINAL_STATES
    ):
        if decision.status in {
            RecoveryDecisionStatus.PROPOSED,
            RecoveryDecisionStatus.SCHEDULED,
        }:
            decision.status = (
                RecoveryDecisionStatus.CANCELLED
            )

            decision.updated_at = utc_now()

            database.commit()

        return _execution_result(
            status="skipped_terminal_case",
            decision=decision,
            recovery_case=recovery_case,
        )

    if (
        decision.status
        != RecoveryDecisionStatus.SCHEDULED
    ):
        raise RecoveryActionNotExecutableError(
            "Only a scheduled recovery decision "
            "can be executed"
        )

    if decision.policy_result not in {
        PolicyResult.APPROVED,
        PolicyResult.MODIFIED,
    }:
        raise RecoveryActionNotExecutableError(
            "The decision does not have "
            "policy authorization"
        )

    action = decision.final_action

    if action is None:
        raise RecoveryActionNotExecutableError(
            "The decision does not contain "
            "a final action"
        )

    # Human review requires an operator.
    # Stop recovery is a state transition, not a payment action.
    if action in {
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    }:
        raise RecoveryActionNotExecutableError(
            f"Action {action.value} cannot "
            "be executed automatically"
        )

    now = utc_now()

    if (
        decision.scheduled_for is not None
        and _as_utc(
            decision.scheduled_for
        ) > now
    ):
        raise RecoveryActionNotDueError(
            "The recovery action is scheduled "
            "for a future time"
        )

    # Real provider execution is permitted only for
    # customer-facing recovery actions and only when
    # the explicit environment switch is enabled.
    notification_requested = False

    should_create_payment_link = (
        settings.razorpay_actions_enabled
        and action
        in CUSTOMER_COMMUNICATION_ACTIONS
    )

    if should_create_payment_link:
        customer_email, customer_contact = (
            _resolve_customer_recipient(
                database=database,
                recovery_case=recovery_case,
            )
        )

        try:
            provider_result = (
                create_standard_payment_link(
                    recovery_case=recovery_case,
                    decision=decision,
                    customer_email=customer_email,
                    customer_contact=(
                        customer_contact
                    ),
                )
            )
        except RazorpayPaymentLinkError:
            # Release database locks and preserve the
            # scheduled decision for a controlled retry.
            database.rollback()
            raise

        notification_requested = bool(
            provider_result.get(
                "notification_requested",
                False,
            )
        )

        _store_provider_result(
            decision=decision,
            provider_result=provider_result,
        )
    else:
        # Provider execution and customer notification
        # are simulated when actions are disabled. A real
        # retry requires a provider token or mandate.
        decision.execution_mode = "simulated"

    recovery_case.current_state = (
        RecoveryCaseState.EXECUTING
    )
    recovery_case.state_version += 1

    if (
        action
        == RecoveryActionType.RETRY_PAYMENT
    ):
        recovery_case.attempt_count += 1
        recovery_case.current_state = (
            RecoveryCaseState.WAITING_FOR_RETRY
        )

    elif action in CUSTOMER_COMMUNICATION_ACTIONS:
        # Increment only after Razorpay accepts a configured
        # notification request. Link creation by itself is not
        # counted as customer communication.
        if notification_requested:
            recovery_case.communication_count += 1

        recovery_case.current_state = (
            RecoveryCaseState.WAITING_FOR_CUSTOMER
        )

    else:
        database.rollback()

        raise RecoveryActionNotExecutableError(
            f"Unsupported recovery action: "
            f"{action.value}"
        )

    current_cost = Decimal(
        str(
            recovery_case
            .intervention_cost_rupees
        )
    )

    action_cost = Decimal(
        str(
            decision
            .estimated_action_cost_rupees
        )
    )

    recovery_case.intervention_cost_rupees = (
        current_cost + action_cost
    ).quantize(MONEY)

    recovery_case.next_action_at = None
    recovery_case.updated_at = now

    decision.status = (
        RecoveryDecisionStatus.EXECUTED
    )
    decision.executed_at = now
    decision.updated_at = now

    database.commit()
    database.refresh(decision)
    database.refresh(recovery_case)

    return _execution_result(
        status="executed",
        decision=decision,
        recovery_case=recovery_case,
    )