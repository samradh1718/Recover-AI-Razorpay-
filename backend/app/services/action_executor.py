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
from app.models import RecoveryCase, RecoveryDecision


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
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _execution_result(
    *,
    status: str,
    decision: RecoveryDecision,
    recovery_case: RecoveryCase,
    simulated: bool,
) -> dict[str, Any]:
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
        "case_state": recovery_case.current_state.value,
        "attempt_count": recovery_case.attempt_count,
        "communication_count": recovery_case.communication_count,
        "intervention_cost_rupees": str(
            recovery_case.intervention_cost_rupees
        ),
        "simulated": simulated,
    }


def execute_recovery_action(
    database: Session,
    decision_id: UUID,
    expected_case_id: UUID | None = None,
) -> dict[str, Any]:
    """Execute one policy-approved recovery action exactly once.

    Phase 1 deliberately simulates the provider/customer side effect. Database
    locking, policy validation, idempotency and case transitions are real.
    """

    decision = database.execute(
        select(RecoveryDecision)
        .where(RecoveryDecision.id == decision_id)
        .with_for_update()
    ).scalar_one_or_none()

    if decision is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery decision was not found"
        )

    if (
        expected_case_id is not None
        and decision.recovery_case_id != expected_case_id
    ):
        raise RecoveryDecisionNotFoundError(
            "Decision does not belong to this recovery case"
        )

    recovery_case = database.execute(
        select(RecoveryCase)
        .where(RecoveryCase.id == decision.recovery_case_id)
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise RecoveryDecisionNotFoundError(
            "Recovery case for this decision was not found"
        )

    if decision.status == RecoveryDecisionStatus.EXECUTED:
        return _execution_result(
            status="already_executed",
            decision=decision,
            recovery_case=recovery_case,
            simulated=True,
        )

    if recovery_case.current_state in TERMINAL_STATES:
        if decision.status in {
            RecoveryDecisionStatus.PROPOSED,
            RecoveryDecisionStatus.SCHEDULED,
        }:
            decision.status = RecoveryDecisionStatus.CANCELLED
            decision.scheduled_for = None
            decision.updated_at = utc_now()
            database.commit()

        return _execution_result(
            status="skipped_terminal_case",
            decision=decision,
            recovery_case=recovery_case,
            simulated=True,
        )

    if decision.status != RecoveryDecisionStatus.SCHEDULED:
        raise RecoveryActionNotExecutableError(
            "Only a scheduled recovery decision can be executed"
        )

    if decision.policy_result not in {
        PolicyResult.APPROVED,
        PolicyResult.MODIFIED,
    }:
        raise RecoveryActionNotExecutableError(
            "The decision does not have policy authorization"
        )

    action = decision.final_action

    if action is None:
        raise RecoveryActionNotExecutableError(
            "The decision does not contain a final action"
        )

    if action in {
        RecoveryActionType.HUMAN_REVIEW,
        RecoveryActionType.STOP_RECOVERY,
    }:
        raise RecoveryActionNotExecutableError(
            f"Action {action.value} cannot be executed automatically"
        )

    now = utc_now()

    if (
        decision.scheduled_for is not None
        and _as_utc(decision.scheduled_for) > now
    ):
        raise RecoveryActionNotDueError(
            "The recovery action is scheduled for a future time"
        )

    recovery_case.current_state = RecoveryCaseState.EXECUTING
    recovery_case.state_version += 1

    if action == RecoveryActionType.RETRY_PAYMENT:
        recovery_case.attempt_count += 1
        recovery_case.current_state = (
            RecoveryCaseState.WAITING_FOR_RETRY
        )
    elif action in CUSTOMER_COMMUNICATION_ACTIONS:
        recovery_case.communication_count += 1
        recovery_case.current_state = (
            RecoveryCaseState.WAITING_FOR_CUSTOMER
        )
    else:
        raise RecoveryActionNotExecutableError(
            f"Unsupported recovery action: {action.value}"
        )

    current_cost = Decimal(
        str(recovery_case.intervention_cost_rupees)
    )
    action_cost = Decimal(
        str(decision.estimated_action_cost_rupees)
    )

    recovery_case.intervention_cost_rupees = (
        current_cost + action_cost
    ).quantize(MONEY)
    recovery_case.next_action_at = None
    recovery_case.updated_at = now

    decision.status = RecoveryDecisionStatus.EXECUTED
    decision.executed_at = now
    decision.scheduled_for = None
    decision.updated_at = now

    database.commit()
    database.refresh(decision)
    database.refresh(recovery_case)

    return _execution_result(
        status="executed",
        decision=decision,
        recovery_case=recovery_case,
        simulated=True,
    )