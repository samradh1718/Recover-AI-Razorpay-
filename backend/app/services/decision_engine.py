from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.enums import (
    FailureCategory,
    PolicyResult,
    RecoveryActionType,
    RecoveryCaseState,
    RecoveryDecisionStatus,
)
from app.core.config import settings
from app.models import RecoveryCase, RecoveryDecision


MONEY = Decimal("0.01")
HIGH_VALUE_REVIEW_LIMIT = Decimal("50000.00")
MAXIMUM_DEMO_ACTION_DELAY_SECONDS = 300

EVALUABLE_STATES = {
    RecoveryCaseState.DETECTED,
    RecoveryCaseState.DIAGNOSED,
    RecoveryCaseState.EVALUATING,
    RecoveryCaseState.READY,
}

CUSTOMER_ACTIONS = {
    RecoveryActionType.SEND_PAYMENT_LINK,
    RecoveryActionType.REQUEST_PAYMENT_METHOD_UPDATE,
    RecoveryActionType.REQUEST_CUSTOMER_AUTHORIZATION,
}


class RecoveryCaseNotFoundError(Exception):
    pass


class RecoveryCaseNotEvaluableError(Exception):
    pass


@dataclass(frozen=True)
class ActionOption:
    action: RecoveryActionType
    probability: Decimal
    cost_rupees: Decimal
    delay_minutes: int | None
    reason_code: str
    explanation: str

    def expected_recovery(
        self,
        amount_rupees: Decimal,
    ) -> Decimal:
        return (
            amount_rupees * self.probability
        ).quantize(
            MONEY,
            rounding=ROUND_HALF_UP,
        )

    def expected_net_value(
        self,
        amount_rupees: Decimal,
    ) -> Decimal:
        return (
            self.expected_recovery(amount_rupees)
            - self.cost_rupees
        ).quantize(
            MONEY,
            rounding=ROUND_HALF_UP,
        )


def _money(
    value: Decimal | int | str,
) -> Decimal:
    return Decimal(str(value)).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def _aware_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _calculate_action_schedule(
    *,
    now: datetime,
    policy_delay_minutes: int | None,
) -> tuple[
    datetime | None,
    int | None,
    str,
]:
    """Calculate the effective execution schedule.

    The rules engine continues recording its original policy
    delay in minutes.

    DEMO_ACTION_DELAY_SECONDS may override only the effective
    Celery execution time. Leaving it unset keeps production
    policy timing unchanged.
    """

    if policy_delay_minutes is None:
        return (
            None,
            None,
            "not_scheduled",
        )

    demo_delay_seconds = (
        settings.demo_action_delay_seconds
    )

    if demo_delay_seconds is not None:
        if not (
            0
            <= demo_delay_seconds
            <= MAXIMUM_DEMO_ACTION_DELAY_SECONDS
        ):
            raise ValueError(
                "DEMO_ACTION_DELAY_SECONDS must be "
                "between 0 and 300"
            )

        return (
            now
            + timedelta(
                seconds=demo_delay_seconds
            ),
            demo_delay_seconds,
            "demo_override",
        )

    policy_delay_seconds = (
        policy_delay_minutes * 60
    )

    return (
        now
        + timedelta(
            seconds=policy_delay_seconds
        ),
        policy_delay_seconds,
        "policy_delay",
    )


def _options_for_failure(
    failure_category: FailureCategory | None,
) -> list[ActionOption]:
    category = (
        failure_category
        or FailureCategory.UNKNOWN
    )

    if (
        category
        == FailureCategory.TEMPORARY_GATEWAY_OR_BANK
    ):
        return [
            ActionOption(
                action=(
                    RecoveryActionType.RETRY_PAYMENT
                ),
                probability=Decimal("0.7200"),
                cost_rupees=Decimal("2.00"),
                delay_minutes=30,
                reason_code=(
                    "temporary_failure_retry"
                ),
                explanation=(
                    "Retry after a short delay because "
                    "the failure appears temporary."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType
                    .SEND_PAYMENT_LINK
                ),
                probability=Decimal("0.4500"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "temporary_failure_payment_link"
                ),
                explanation=(
                    "Offer a payment link as an "
                    "alternate recovery path."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType.HUMAN_REVIEW
                ),
                probability=Decimal("0.3000"),
                cost_rupees=Decimal("50.00"),
                delay_minutes=None,
                reason_code=(
                    "temporary_failure_manual_review"
                ),
                explanation=(
                    "Send the case to an operator "
                    "for manual review."
                ),
            ),
        ]

    if (
        category
        == FailureCategory.INSUFFICIENT_FUNDS
    ):
        return [
            ActionOption(
                action=(
                    RecoveryActionType.RETRY_PAYMENT
                ),
                probability=Decimal("0.5500"),
                cost_rupees=Decimal("2.00"),
                delay_minutes=24 * 60,
                reason_code=(
                    "insufficient_funds_delayed_retry"
                ),
                explanation=(
                    "Retry later to give the customer "
                    "time to restore funds."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType
                    .SEND_PAYMENT_LINK
                ),
                probability=Decimal("0.3500"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "insufficient_funds_payment_link"
                ),
                explanation=(
                    "Offer a payment link so the "
                    "customer can pay when ready."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType.HUMAN_REVIEW
                ),
                probability=Decimal("0.2500"),
                cost_rupees=Decimal("50.00"),
                delay_minutes=None,
                reason_code=(
                    "insufficient_funds_manual_review"
                ),
                explanation=(
                    "Send the case to an operator "
                    "for manual review."
                ),
            ),
        ]

    if (
        category
        == FailureCategory.INVALID_OR_EXPIRED_METHOD
    ):
        return [
            ActionOption(
                action=(
                    RecoveryActionType
                    .REQUEST_PAYMENT_METHOD_UPDATE
                ),
                probability=Decimal("0.6600"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "invalid_method_update_required"
                ),
                explanation=(
                    "Ask the customer to replace the "
                    "invalid or expired payment method."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType
                    .SEND_PAYMENT_LINK
                ),
                probability=Decimal("0.5800"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "invalid_method_payment_link"
                ),
                explanation=(
                    "Offer a payment link using "
                    "another payment method."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType.HUMAN_REVIEW
                ),
                probability=Decimal("0.3000"),
                cost_rupees=Decimal("50.00"),
                delay_minutes=None,
                reason_code=(
                    "invalid_method_manual_review"
                ),
                explanation=(
                    "Send the case to an operator "
                    "for manual review."
                ),
            ),
        ]

    if (
        category
        == FailureCategory.MANDATE_OR_AUTHORIZATION
    ):
        return [
            ActionOption(
                action=(
                    RecoveryActionType
                    .REQUEST_CUSTOMER_AUTHORIZATION
                ),
                probability=Decimal("0.6800"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "customer_authorization_required"
                ),
                explanation=(
                    "Ask the customer to complete "
                    "the required authorization."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType
                    .SEND_PAYMENT_LINK
                ),
                probability=Decimal("0.5800"),
                cost_rupees=Decimal("1.00"),
                delay_minutes=5,
                reason_code=(
                    "authorization_payment_link"
                ),
                explanation=(
                    "Offer a payment link as an "
                    "alternate authorized payment path."
                ),
            ),
            ActionOption(
                action=(
                    RecoveryActionType.RETRY_PAYMENT
                ),
                probability=Decimal("0.1500"),
                cost_rupees=Decimal("2.00"),
                delay_minutes=30,
                reason_code=(
                    "authorization_retry_low_confidence"
                ),
                explanation=(
                    "Retrying may work, but "
                    "authorization failures have low "
                    "retry confidence."
                ),
            ),
        ]

    return [
        ActionOption(
            action=(
                RecoveryActionType.HUMAN_REVIEW
            ),
            probability=Decimal("0.4000"),
            cost_rupees=Decimal("50.00"),
            delay_minutes=None,
            reason_code=(
                "unknown_failure_manual_review"
            ),
            explanation=(
                "The failure is unknown, so an "
                "operator should review the case."
            ),
        ),
        ActionOption(
            action=(
                RecoveryActionType.SEND_PAYMENT_LINK
            ),
            probability=Decimal("0.3500"),
            cost_rupees=Decimal("1.00"),
            delay_minutes=5,
            reason_code=(
                "unknown_failure_payment_link"
            ),
            explanation=(
                "Offer a payment link as a "
                "low-risk fallback."
            ),
        ),
        ActionOption(
            action=(
                RecoveryActionType.STOP_RECOVERY
            ),
            probability=Decimal("0.0000"),
            cost_rupees=Decimal("0.00"),
            delay_minutes=None,
            reason_code=(
                "unknown_failure_stop"
            ),
            explanation=(
                "Stop recovery when no safe "
                "positive-value action exists."
            ),
        ),
    ]


def _find_or_create_policy_option(
    options: list[ActionOption],
    action: RecoveryActionType,
) -> ActionOption:
    for option in options:
        if option.action == action:
            return option

    if (
        action
        == RecoveryActionType.HUMAN_REVIEW
    ):
        return ActionOption(
            action=action,
            probability=Decimal("0.4000"),
            cost_rupees=Decimal("50.00"),
            delay_minutes=None,
            reason_code=(
                "policy_manual_review"
            ),
            explanation=(
                "Policy requires an operator "
                "to review this case."
            ),
        )

    return ActionOption(
        action=(
            RecoveryActionType.STOP_RECOVERY
        ),
        probability=Decimal("0.0000"),
        cost_rupees=Decimal("0.00"),
        delay_minutes=None,
        reason_code=(
            "policy_stop_recovery"
        ),
        explanation=(
            "Policy does not allow another "
            "automated recovery action."
        ),
    )


def _apply_policy(
    recovery_case: RecoveryCase,
    recommended: ActionOption,
    options: list[ActionOption],
    now: datetime,
) -> tuple[
    ActionOption,
    PolicyResult,
    list[str],
    bool,
]:
    amount = _money(
        recovery_case.recoverable_amount_rupees
    )

    deadline_expired = (
        _aware_utc(
            recovery_case.recovery_deadline_at
        )
        <= now
    )

    if deadline_expired:
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.STOP_RECOVERY,
            ),
            PolicyResult.REJECTED,
            ["recovery_deadline_expired"],
            True,
        )

    if recovery_case.attempt_count >= 3:
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.HUMAN_REVIEW,
            ),
            PolicyResult.ESCALATED,
            [
                "maximum_automatic_attempts_reached"
            ],
            False,
        )

    if amount >= HIGH_VALUE_REVIEW_LIMIT:
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.HUMAN_REVIEW,
            ),
            PolicyResult.ESCALATED,
            [
                "high_value_case_requires_review"
            ],
            False,
        )

    category = (
        recovery_case.failure_category
        or FailureCategory.UNKNOWN
    )

    if category == FailureCategory.UNKNOWN:
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.HUMAN_REVIEW,
            ),
            PolicyResult.ESCALATED,
            [
                "unknown_failure_requires_review"
            ],
            False,
        )

    if (
        recovery_case.communication_count >= 3
        and recommended.action
        in CUSTOMER_ACTIONS
    ):
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.HUMAN_REVIEW,
            ),
            PolicyResult.ESCALATED,
            [
                "customer_contact_limit_reached"
            ],
            False,
        )

    if (
        recommended.expected_net_value(amount)
        <= Decimal("0.00")
    ):
        return (
            _find_or_create_policy_option(
                options,
                RecoveryActionType.STOP_RECOVERY,
            ),
            PolicyResult.REJECTED,
            [
                "no_positive_expected_net_value"
            ],
            False,
        )

    return (
        recommended,
        PolicyResult.APPROVED,
        [
            recommended.reason_code,
            "positive_expected_net_value",
        ],
        False,
    )


def _decision_status(
    action: RecoveryActionType,
) -> RecoveryDecisionStatus:
    if (
        action
        == RecoveryActionType.HUMAN_REVIEW
    ):
        return (
            RecoveryDecisionStatus.PROPOSED
        )

    if (
        action
        == RecoveryActionType.STOP_RECOVERY
    ):
        return (
            RecoveryDecisionStatus.CANCELLED
        )

    return RecoveryDecisionStatus.SCHEDULED


def _case_state(
    action: RecoveryActionType,
    deadline_expired: bool,
) -> RecoveryCaseState:
    if deadline_expired:
        return RecoveryCaseState.EXPIRED

    if (
        action
        == RecoveryActionType.RETRY_PAYMENT
    ):
        return RecoveryCaseState.SCHEDULED

    if action in CUSTOMER_ACTIONS:
        return (
            RecoveryCaseState
            .WAITING_FOR_CUSTOMER
        )

    if (
        action
        == RecoveryActionType.HUMAN_REVIEW
    ):
        return RecoveryCaseState.HUMAN_REVIEW

    return RecoveryCaseState.STOPPED


def _option_payload(
    option: ActionOption,
    amount_rupees: Decimal,
) -> dict[
    str,
    str | int | None,
]:
    return {
        "action": option.action.value,
        "probability": str(
            option.probability
        ),
        "expected_recovery_rupees": str(
            option.expected_recovery(
                amount_rupees
            )
        ),
        "estimated_action_cost_rupees": str(
            option.cost_rupees
        ),
        "expected_net_value_rupees": str(
            option.expected_net_value(
                amount_rupees
            )
        ),
        "delay_minutes": (
            option.delay_minutes
        ),
        "reason_code": option.reason_code,
    }


def evaluate_recovery_case(
    database: Session,
    case_id: UUID,
) -> RecoveryDecision:
    recovery_case = database.execute(
        select(RecoveryCase)
        .where(
            RecoveryCase.id == case_id
        )
        .with_for_update()
    ).scalar_one_or_none()

    if recovery_case is None:
        raise RecoveryCaseNotFoundError(
            "Recovery case was not found"
        )

    latest_decision = database.execute(
        select(RecoveryDecision)
        .where(
            RecoveryDecision
            .recovery_case_id
            == case_id
        )
        .order_by(
            RecoveryDecision
            .created_at
            .desc()
        )
        .limit(1)
    ).scalar_one_or_none()

    if (
        recovery_case.current_state
        not in EVALUABLE_STATES
    ):
        if latest_decision is not None:
            return latest_decision

        raise RecoveryCaseNotEvaluableError(
            "Case in state "
            f"{recovery_case.current_state.value} "
            "cannot be evaluated"
        )

    existing_version_decision = (
        database.execute(
            select(
                RecoveryDecision
            ).where(
                RecoveryDecision
                .recovery_case_id
                == case_id,
                RecoveryDecision
                .case_state_version
                == recovery_case.state_version,
            )
        ).scalar_one_or_none()
    )

    if (
        existing_version_decision
        is not None
    ):
        return existing_version_decision

    now = datetime.now(timezone.utc)

    amount = _money(
        recovery_case.recoverable_amount_rupees
    )

    options = _options_for_failure(
        recovery_case.failure_category
    )

    recommended = max(
        options,
        key=lambda option: (
            option.expected_net_value(
                amount
            )
        ),
    )

    (
        final_option,
        policy_result,
        reason_codes,
        deadline_expired,
    ) = _apply_policy(
        recovery_case=recovery_case,
        recommended=recommended,
        options=options,
        now=now,
    )

    (
        scheduled_for,
        effective_delay_seconds,
        schedule_mode,
    ) = _calculate_action_schedule(
        now=now,
        policy_delay_minutes=(
            final_option.delay_minutes
        ),
    )

    decision = RecoveryDecision(
        tenant_id=(
            recovery_case.tenant_id
        ),
        recovery_case_id=(
            recovery_case.id
        ),
        case_state_version=(
            recovery_case.state_version
        ),
        recommended_action=(
            recommended.action
        ),
        final_action=(
            final_option.action
        ),
        policy_result=policy_result,
        status=_decision_status(
            final_option.action
        ),
        recovery_probability=(
            final_option.probability
        ),
        expected_recovery_rupees=(
            final_option.expected_recovery(
                amount
            )
        ),
        estimated_action_cost_rupees=(
            final_option.cost_rupees
        ),
        expected_net_value_rupees=(
            final_option.expected_net_value(
                amount
            )
        ),
        explanation=(
            final_option.explanation
        ),
        reason_codes=reason_codes,
        decision_inputs={
            "failure_category": (
                recovery_case
                .failure_category
                .value
                if recovery_case
                .failure_category
                else (
                    FailureCategory
                    .UNKNOWN
                    .value
                )
            ),
            "recoverable_amount_rupees": (
                str(amount)
            ),
            "attempt_count": (
                recovery_case.attempt_count
            ),
            "communication_count": (
                recovery_case
                .communication_count
            ),
            "recommended_option": (
                _option_payload(
                    recommended,
                    amount,
                )
            ),
            "policy_delay_minutes": (
                final_option.delay_minutes
            ),
            "effective_delay_seconds": (
                effective_delay_seconds
            ),
            "schedule_mode": (
                schedule_mode
            ),
        },
        alternatives=[
            _option_payload(
                option,
                amount,
            )
            for option in options
            if (
                option.action
                != recommended.action
            )
        ],
        model_source="rules_v1",
        scheduled_for=scheduled_for,
    )

    recovery_case.current_state = (
        _case_state(
            final_option.action,
            deadline_expired,
        )
    )

    recovery_case.state_version += 1

    recovery_case.next_action_at = (
        scheduled_for
    )

    recovery_case.updated_at = now

    if (
        final_option.action
        == RecoveryActionType.STOP_RECOVERY
    ):
        recovery_case.closed_at = now

    database.add(decision)
    database.commit()
    database.refresh(decision)

    return decision


def list_recovery_case_decisions(
    database: Session,
    case_id: UUID,
) -> list[RecoveryDecision]:
    case_exists = database.execute(
        select(
            RecoveryCase.id
        ).where(
            RecoveryCase.id == case_id
        )
    ).scalar_one_or_none()

    if case_exists is None:
        raise RecoveryCaseNotFoundError(
            "Recovery case was not found"
        )

    return list(
        database.execute(
            select(
                RecoveryDecision
            )
            .where(
                RecoveryDecision
                .recovery_case_id
                == case_id
            )
            .order_by(
                RecoveryDecision
                .created_at
                .desc()
            )
        ).scalars()
    )